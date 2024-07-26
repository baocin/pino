import caldav
from caldav.elements import dav, cdav
from datetime import datetime, timedelta
import os
import logging
from embedding import EmbeddingService
import json
import requests

# Configure logging
logging.basicConfig(filename='calendar.log', level=logging.INFO, 
                    format='%(asctime)s - calendars - %(levelname)s - %(message)s')
    
class CalendarInjest:
    def __init__(self, DB):
        db_instance = DB(
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD")
        )
        self.db = db_instance.connection
        self.embedding_service = EmbeddingService()
        all_accounts = [
            {"url": os.getenv("CALDAV_URL_1"), "username": os.getenv("CALDAV_USERNAME_1"), "password": os.getenv("CALDAV_PASSWORD_1"), "disabled": os.getenv("CALDAV_DISABLED_1")},
            {"url": os.getenv("CALDAV_URL_2"), "username": os.getenv("CALDAV_USERNAME_2"), "password": os.getenv("CALDAV_PASSWORD_2"), "disabled": os.getenv("CALDAV_DISABLED_2")},
            {"url": os.getenv("CALDAV_URL_3"), "username": os.getenv("CALDAV_USERNAME_3"), "password": os.getenv("CALDAV_PASSWORD_3"), "disabled": os.getenv("CALDAV_DISABLED_3")},
        ]
        self.accounts = [account for account in all_accounts if account["disabled"] != "true"]

    def fetch_all_calendar_events(self):
        for account in self.accounts:
            self.fetch_calendar_events(account)

    def fetch_calendar_events(self, account):
        try:
            client = caldav.DAVClient(url=account["url"], username=account["username"], password=account["password"])
            principal = client.principal()
            calendars = principal.calendars()

            logging.debug(f"Fetching calendar events for {account['username']}")
            logging.debug(f"Calendars: {([calendar.url for calendar in calendars])}")
            logging.debug(f"Calendars: {([calendar.name for calendar in calendars])}")

            pull_id = self.get_last_pull_id() + 1

            for calendar in calendars:
                logging.info(f"Fetching events for calendar {calendar.name}")
                events = calendar.search(
                    # start=datetime.now() - timedelta(year=1),
                    # end=datetime.now() + timedelta(year=1),
                    event=True
                )
                for event in events:
                    # logging.info(f"Processing event {event.vobject_instance.vevent.summary.value}")
                    event_id = f"{calendar.url}_{event.vobject_instance.vevent.uid.value}"
                    if self.event_exists(event_id, f"{account['username']} - {calendar.name}"):
                        # logging.info(f"Event {event_id} already exists in the database. Skipping download.")
                        continue

                    try:
                        # logging.info(f"Processing event {event_id} for {account['username']} - {json.dumps(event.vobject_instance.vevent, ensure_ascii=False)}")
                        calendar_data = {
                            "event_id": event_id,
                            "source_calendar": f"{account['username']} - {calendar.name}",
                            "summary": event.vobject_instance.vevent.summary.value,
                            "start": event.vobject_instance.vevent.dtstart.value,
                            "end": event.vobject_instance.vevent.dtend.value if hasattr(event.vobject_instance.vevent, 'dtend') else None,
                            "description": event.vobject_instance.vevent.description.value if hasattr(event.vobject_instance.vevent, 'description') else '',
                            "location": event.vobject_instance.vevent.location.value if hasattr(event.vobject_instance.vevent, 'location') else '',
                            "pull_id": pull_id,
                            "gps_point": None,  # Assuming you have a way to get this data
                            "embedding": None,  # Placeholder for embedding
                        }
                        logging.debug(f"Calendar data: {calendar_data}")
                        logging.debug(f"Event: {event}")

                        # If there is a location, attempt to search Nominatim for the address to populate the gps point
                        if calendar_data["location"]:
                            try:
                                base_url = "http://localhost:8080"
                                endpoint = "/search"
                                params = {
                                    'q': calendar_data["location"],
                                    'format': 'json'
                                }
                                response = requests.get(base_url + endpoint, params=params)
                                if response.status_code == 200:
                                    data = response.json()
                                    if data:
                                        lat = data[0]['lat']
                                        lon = data[0]['lon']
                                        calendar_data["gps_point"] = f'POINT({lon} {lat})'
                                        logging.info(f"GPS point for location '{calendar_data['location']}': {calendar_data['gps_point']}")
                                else:
                                    logging.error(f"Failed to fetch GPS point for location '{calendar_data['location']}' with status code: {response.status_code}")
                            except Exception as e:
                                logging.error(f"Error fetching GPS point for location '{calendar_data['location']}': {e}")

                        # Generate embedding for the event summary
                        calendar_data["embedding"] = self.embedding_service.embed_text([calendar_data["summary"] + " " + calendar_data["description"] + " " + calendar_data["location"]])[0]
                    except Exception as e:
                        logging.error(f"Error processing event {event_id} for {account['username']}: {e}")
                        continue

                    logging.debug(f"Inserting calendar data for {event_id}")
                    logging.debug(f"Pull ID: {pull_id}")
                    logging.debug(f"Account: {account}")

                    self.insert_calendar_data(calendar_data)
        except Exception as e:
            logging.error(f"Error fetching calendar events for {account['username']}: {e}")

    def get_last_pull_id(self):
        sql = "SELECT COALESCE(MAX(pull_id), 0) FROM calendar_events"
        cursor = self.db.cursor()
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else 0
    
    def insert_calendar_data(self, calendar_data):
        if self.event_exists(calendar_data['event_id'], calendar_data['source_calendar']):
            sql = """
            UPDATE calendar_events
            SET summary = %s,
                start_time = %s,
                end_time = %s,
                description = %s,
                location = %s,
                gps_point = %s,
                embedding = %s,
                source_calendar = %s
            WHERE event_id = %s AND source_calendar = %s
            """
            values = (
                calendar_data['summary'],
                calendar_data['start'],
                calendar_data['end'],
                calendar_data['description'],
                calendar_data['location'],
                calendar_data['gps_point'],
                calendar_data['embedding'],
                calendar_data['source_calendar'],
                calendar_data['event_id'],
                calendar_data['source_calendar']
            )
        else:
            sql = """
            INSERT INTO calendar_events (event_id, summary, start_time, end_time, description, location, pull_id, gps_point, embedding, source_calendar)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                calendar_data['event_id'],
                calendar_data['summary'],
                calendar_data['start'],
                calendar_data['end'],
                calendar_data['description'],
                calendar_data['location'],
                calendar_data['pull_id'],
                calendar_data['gps_point'],
                calendar_data['embedding'],
                calendar_data['source_calendar']
            )
        
        cursor = self.db.cursor()
        cursor.execute(sql, values)
        self.db.commit()
        cursor.close()

    def event_exists(self, event_id, source_calendar):
        sql = "SELECT 1 FROM calendar_events WHERE event_id = %s AND source_calendar = %s"
        cursor = self.db.cursor()
        cursor.execute(sql, (event_id, source_calendar))
        result = cursor.fetchone()
        cursor.close()
        return result is not None

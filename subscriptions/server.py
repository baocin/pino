import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from libraries.db import DB

import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
import re
from collections import defaultdict
from handlers.sensor.main import handle_phone_stationary, handle_phone_screen_up
from handlers.gps.main import handle_gps_data
from handlers.email.main import handle_email_check
from handlers.connection import handle_check_connection
from handlers.archiver import handle_device_log

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from libraries.gotify.gotify import send_gotify_message

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(filename='subscription_handler.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Global dictionary to track notifications
notification_tracker = defaultdict(list)

class DBSubscription:
    def __init__(self, label, query, interval, handler, max_notifications_per_minute, trigger_on_all_queries=False):
        self.db = DB()
        self.label = label
        self.query = query
        self.table_name = DBSubscription.extract_table_name(self.query)
        self.interval = interval
        self.handler = handler
        self.max_notifications_per_minute = max_notifications_per_minute
        self.previous_result = None
        self.trigger_on_all_queries = trigger_on_all_queries

    @staticmethod
    def extract_table_name(query):
        match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def handle_polling(self, differences):
        # logging.info(f"New data detected for {self.label}: {differences}")
        result = self.handler(self, differences)
        self.previous_result = result

    def start_polling(self):
        self.db.poll_query(self.query, self.interval, self.handle_polling, self.trigger_on_all_queries)

    def send_notification(self, title, message, priority):
        current_time = datetime.now()
        notification_tracker[title] = [timestamp for timestamp in notification_tracker[title] if timestamp > current_time - timedelta(minutes=1)]
        
        if len(notification_tracker[title]) < self.max_notifications_per_minute:
            send_gotify_message(title, message, priority)
            notification_tracker[title].append(current_time)
        else:
            if self.max_notifications_per_minute >0:
                logging.warning(f"Notification limit reached for {title}. Skipping notification.")


subscriptions = [
    {
        "label": "gps_data",
        "query": "SELECT latitude, longitude, time, device_id FROM gps_data ORDER BY created_at DESC LIMIT 100", 
        "interval": 5, 
        "handler": handle_gps_data, 
        "trigger_on_all_queries": True,
        "max_notifications_per_minute": 5
    },
    {
        "label": "phone_screen_up",
        "query": "SELECT sensor_type,x,y,z,created_at,device_id FROM sensor_data WHERE sensor_type = 'gravity' ORDER BY created_at DESC LIMIT 1",
        "interval": 1,
        "handler": handle_phone_screen_up,
        "trigger_on_all_queries": True,
        "max_notifications_per_minute": 0
    },
    {
        "label": "phone_stationary",
        "query": "SELECT sensor_type,x,y,z,created_at,device_id FROM sensor_data WHERE sensor_type = 'accelerometer' ORDER BY created_at DESC LIMIT 1",
        "interval": 1,
        "handler": handle_phone_stationary,
        "trigger_on_all_queries": True,
        "max_notifications_per_minute": 0
    },
    {
        "label": "email_check",
        "query": "SELECT email_id, subject, sender, date_received FROM emails ORDER BY date_received DESC LIMIT 10",
        "interval": 4,
        "handler": handle_email_check,
        "max_notifications_per_minute": 2
    },
    {
        "label": "no_gps_added",
        "query": """
            SELECT device_id, MAX(time) as time
            FROM gps_data
            GROUP BY device_id
            ORDER BY time DESC
        """,
        "interval": 1,
        "handler": handle_check_connection,
        "trigger_on_all_queries": True,
        "max_notifications_per_minute": 0
    },
    {
        "label": "device_status_log",
        "query": """
            SELECT id, last_movement, screen_up, speed, online, location
            FROM devices
            WHERE id = '1'
            ORDER BY updated_at DESC
        """,
        "interval": 1,
        "handler": handle_device_log,
        "trigger_on_all_queries": True,
        "max_notifications_per_minute": 0
    }


]

if __name__ == "__main__":
    subscribers = [DBSubscription(sub["label"], sub["query"], sub["interval"], sub["handler"], sub["max_notifications_per_minute"], sub.get("trigger_on_all_queries", False)) for sub in subscriptions]
    for subscriber in subscribers:
        subscriber.start_polling()

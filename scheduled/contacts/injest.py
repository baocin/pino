import requests
import os
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from embedding import EmbeddingService

# Configure logging
logging.basicConfig(filename='contacts.log', level=logging.INFO, 
                    format='%(asctime)s - contacts - %(levelname)s - %(message)s')

class ContactsInjest:
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
            {"url": os.getenv("CARDDAV_URL_1"), "username": os.getenv("CARDDAV_USERNAME_1"), "password": os.getenv("CARDDAV_PASSWORD_1"), "disabled": os.getenv("CARDDAV_DISABLED_1")},
            {"url": os.getenv("CARDDAV_URL_2"), "username": os.getenv("CARDDAV_USERNAME_2"), "password": os.getenv("CARDDAV_PASSWORD_2"), "disabled": os.getenv("CARDDAV_DISABLED_2")},
            {"url": os.getenv("CARDDAV_URL_3"), "username": os.getenv("CARDDAV_USERNAME_3"), "password": os.getenv("CARDDAV_PASSWORD_3"), "disabled": os.getenv("CARDDAV_DISABLED_3")},
        ]
        self.accounts = [account for account in all_accounts if account["disabled"] != "true"]

    def fetch_all_contacts(self):
        for account in self.accounts:
            if account["url"] is not None:
                self.fetch_contacts(account)

    def fetch_contacts(self, account):
        try:
            cursor = self.db.cursor()
            # Wipe the contacts table
            cursor.execute("DELETE FROM contacts WHERE vcard_id IS NOT NULL")

            response = requests.request(
                'PROPFIND',
                account["url"],
                auth=(account["username"], account["password"]),
                headers={'Depth': '1'}
            )
            if response.status_code == 207:
                root = ET.fromstring(response.content)
                for response in root.findall('{DAV:}response'):
                    href = response.find('{DAV:}href').text
                    vcard_id = href.split('/')[-1]
                    vcard_url = account["url"] + '/' + vcard_id
                    vcard_response = requests.get(vcard_url, auth=(account["username"], account["password"]))
                    if vcard_response.status_code == 200:
                        vcards = vcard_response.text.split("END:VCARD")
                        for vcard in vcards:
                            vcard = vcard.strip()
                            if vcard:
                                self.process_vcard(vcard, cursor)
                    else:
                        logging.error(f"Failed to fetch vCard for href: {vcard_url} with status code: {vcard_response.status_code}")
                self.db.commit()  # Commit all inserts once the account is done
            else:
                logging.error(f"Failed to fetch contacts for {account['username']}: {response.status_code}")
        except Exception as e:
            logging.error(f"Error fetching contacts for {account['username']}: {e}")
            # self.db.rollback()  # Rollback the transaction on error
        finally:
            logging.info(f"Finished fetching contacts for {account['url']}")
            cursor.close()

    def process_vcard(self, vcard, cursor):
        try:
            lines = vcard.splitlines()
            contact_data = {"raw_vcard": vcard}
            for line in lines:
                if line.startswith("FN:"):
                    contact_data["full_name"] = line[3:]
                elif "EMAIL" in line:
                    email_parts = line.split(":")
                    contact_data["email"] = email_parts[1] if len(email_parts) > 1 else ""
                elif line.startswith("TEL:"):
                    contact_data["phone"] = line[4:]
                elif line.startswith("UID:"):
                    contact_data["vcard_id"] = line[4:]
                elif line.startswith("REV:"):
                    contact_data["created_at"] = datetime.strptime(line[4:], "%Y%m%dT%H%M%SZ")

            if contact_data:
                contact_data["last_contacted"] = datetime.now()
                contact_data["last_seen_timestamp"] = datetime.now()
                contact_data["embedding"] = self.embedding_service.embed_text([contact_data["raw_vcard"]])[0] if "raw_vcard" in contact_data else None
                contact_data["face_images"] = None  # Assuming face images are not available at this point
                contact_data["last_seen_location"] = None  # Assuming last seen location is not available at this point
                self.insert_contact_data(contact_data, cursor)
        except Exception as e:
            logging.error(f"Error processing vCard: {e}")

    def insert_contact_data(self, contact_data, cursor):
        try:
            # Check if the contact already exists
            check_sql = "SELECT 1 FROM contacts WHERE email = %s"
            cursor.execute(check_sql, (contact_data.get('email', ''),))
            exists = cursor.fetchone()

            if exists:
                # Update existing contact
                update_sql = """
                UPDATE contacts SET
                    full_name = %s,
                    phone = %s,
                    last_contacted = %s,
                    last_seen_timestamp = %s,
                    embedding = %s,
                    face_images = %s,
                    last_seen_location = %s,
                    raw_vcard = %s,
                    created_at = %s
                WHERE email = %s
                """
                update_values = (
                    contact_data.get('full_name', ''),
                    contact_data.get('phone', ''),
                    None, # contact_data.get('last_contacted'),
                    None, # contact_data.get('last_seen_timestamp'),
                    contact_data.get('embedding'),
                    contact_data.get('face_images'),
                    contact_data.get('last_seen_location'),
                    contact_data.get('raw_vcard', ''),
                    contact_data.get('created_at'),
                    contact_data.get('email', '')
                )
                cursor.execute(update_sql, update_values)
            else:
                # Insert new contact
                insert_sql = """
                INSERT INTO contacts (full_name, email, phone, last_contacted, last_seen_timestamp, embedding, face_images, last_seen_location, raw_vcard, vcard_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                insert_values = (
                    contact_data.get('full_name', ''),
                    contact_data.get('email', ''),
                    contact_data.get('phone', ''),
                    None, # contact_data.get('last_contacted'),
                    None, # contact_data.get('last_seen_timestamp'),
                    contact_data.get('embedding'),
                    contact_data.get('face_images'),
                    contact_data.get('last_seen_location'),
                    contact_data.get('raw_vcard', ''),
                    contact_data.get('vcard_id', ''),
                    contact_data.get('created_at')
                )
                cursor.execute(insert_sql, insert_values)
        except Exception as e:
            logging.error(f"Error inserting or updating contact data: {e}")
            self.db.rollback()  # Rollback the transaction on error

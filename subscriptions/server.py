import os
import json
import logging
from dotenv import load_dotenv
from db import DB
from datetime import datetime, timedelta
import re
from collections import defaultdict
from handlers.sensor.main import handle_phone_up_stationary
from handlers.gps.main import handle_gps_data
from tools.gotify import send_gotify_message

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(filename='subscription_handler.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Global dictionary to track notifications
notification_tracker = defaultdict(list)

class DBSubscription:
    def __init__(self, label, query, interval, handler, max_notifications_per_minute):
        self.db = DB()
        self.label = label
        self.query = query
        self.table_name = DBSubscription.extract_table_name(self.query)
        self.interval = interval
        self.handler = handler
        self.max_notifications_per_minute = max_notifications_per_minute
        self.previous_result = None

    @staticmethod
    def extract_table_name(query):
        match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def handle_polling(self, differences):
        logging.info(f"New data detected for {self.label}: {differences}")
        result = self.handler(self, differences)
        self.previous_result = result

    def start_polling(self):
        self.db.poll_query(self.query, self.interval, self.handle_polling)

    def send_notification(self, title, message, priority):
        current_time = datetime.now()
        notification_tracker[title] = [timestamp for timestamp in notification_tracker[title] if timestamp > current_time - timedelta(minutes=1)]
        
        if len(notification_tracker[title]) < self.max_notifications_per_minute:
            send_gotify_message(title, message, priority)
            notification_tracker[title].append(current_time)
        else:
            logging.warning(f"Notification limit reached for {title}. Skipping notification.")

subscriptions = [
    {
        "label": "gps_data",
        "query": "SELECT latitude, longitude, created_at FROM gps_data ORDER BY created_at DESC LIMIT 10", 
        "interval": 5, 
        "handler": handle_gps_data, 
        "max_notifications_per_minute": 5
    },
    {
        "label": "phone_up_stationary",
        "query": "SELECT sensor_type,x,y,z,created_at FROM sensor_data WHERE sensor_type = 'gravity' ORDER BY created_at DESC LIMIT 100",
        "interval": 5,
        "handler": handle_phone_up_stationary,
        "max_notifications_per_minute": 3
    },

]

if __name__ == "__main__":
    subscribers = [DBSubscription(sub["label"], sub["query"], sub["interval"], sub["handler"], sub["max_notifications_per_minute"]) for sub in subscriptions]
    for subscriber in subscribers:
        subscriber.start_polling()

import os
import json
import logging
from dotenv import load_dotenv

import sys
import os

# Add the directory containing the libraries folder to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from libraries.gotify.gotify import send_gotify_message
from datetime import datetime, timedelta
import time
import re
import math
from collections import defaultdict

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(filename='subscription_handler.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def extract_table_name(query):
    match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def handle_email_check(subscription, differences):
    new_emails = []

    for row in differences:
        email_id, subject, sender, date_received = row['email_id'], row['subject'], row['sender'], row['date_received']
        new_emails.append({
            "email_id": email_id,
            "subject": subject,
            "sender": sender,
            "date_received": date_received
        })
    
    if differences:
        for email in differences:
            notification_title = f"New Email from {email['sender']}"
            notification_message = f"Subject: {email['subject']}\nReceived: {email['date_received']}"
            subscription.send_notification(notification_title, notification_message, 10)
        return new_emails
    
    return differences


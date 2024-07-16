import os
import json
import logging
from dotenv import load_dotenv
from tools.gotify.gotify import send_gotify_message
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

def handle_phone_up_stationary(subscription, differences):
    phone_up_statuses = []

    for i in range(1, len(differences)):
        current_row = differences[i]
        previous_row = differences[i - 1]
        current_time = current_row[4]
        previous_time = previous_row[4]
        
        time_difference = current_time - previous_time
        time_difference_in_seconds = time_difference.days * 86400 + time_difference.seconds
        
        if time_difference_in_seconds > 60:
            return None
        
    for row in differences:
        sensor_type, x, y, z = row[0], row[1], row[2], row[3]
        is_phone_up = None
        if sensor_type == 'gravity' and x is not None and y is not None and z is not None:
            if abs(z - 9.8) < 0.5 and abs(x) < 2.1 and abs(y) < 0.5:
                is_phone_up = True
            if abs(z + 9.8) < 0.5 and abs(x) < 2.1 and abs(y) < 0.5:
                is_phone_up = False
                
        phone_up_statuses.append(is_phone_up)
    
    # print(phone_up_statuses)
    # print("prev", subscription.previous_result, "now", phone_up_statuses[0])
    if all(status == phone_up_statuses[0] for status in phone_up_statuses):
        is_phone_up = phone_up_statuses[0]
        if is_phone_up != None and subscription.previous_result != is_phone_up:
            if is_phone_up:
                subscription.send_notification("Phone Status", "The phone is up and stationary", 10)
            else:
                subscription.send_notification("Phone Status", "The phone is down", 10)
        return is_phone_up
    
    return None

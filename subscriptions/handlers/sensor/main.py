import os
import json
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time
import re
import math
from collections import defaultdict

import sys
import os

# Add the directory containing the libraries folder to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from libraries.gotify.gotify import send_gotify_message


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

def is_list_continuous(list_of_timestamps, max_time_difference=60):
    for current_time, previous_time in zip(list_of_timestamps[1:], list_of_timestamps[:-1]):
        time_difference = current_time - previous_time
        time_difference_in_seconds = time_difference.total_seconds()
        
        if time_difference_in_seconds > max_time_difference:
            return False
    return True

def is_screen_up(x, y, z):
    if x is None or y is None or z is None:
        return None
    if abs(z - 9.8) < 0.5 and abs(x) < 2.1 and abs(y) < 0.5:
        return True
    if abs(z + 9.8) < 0.5 and abs(x) < 2.1 and abs(y) < 0.5:
        return False
    return None

def is_moving(x, y, z, threshold=2):
    magnitude = math.sqrt(x**2 + y**2)
    return magnitude > threshold

def handle_phone_screen_up(subscription, rows):
    if not rows:
        return None

    row = rows[0]  # Consider only one row
    sensor_type, x, y, z, created_at, device_id = row

    if sensor_type != 'gravity':
        return None

    is_phone_up = is_screen_up(x, y, z)
    # print("is_phone_up", is_phone_up)

    if subscription.previous_result != is_phone_up:
        update_query = """
            UPDATE devices 
            SET screen_up = %s 
            WHERE id = %s
            RETURNING *
        """
        subscription.db.execute(update_query, (is_phone_up, device_id))
        # if is_phone_up:
        #     subscription.send_notification("Phone Status", "The phone is up", 10)
        # else:
        #     subscription.send_notification("Phone Status", "The phone is down", 10)
        # logging.info(f"Updated screen_up status to {is_phone_up} for device_id {device_id}")

    return is_phone_up

def handle_phone_stationary(subscription, rows):
    if not rows:
        return None

    row = rows[0]  # Consider only one row
    sensor_type, x, y, z, created_at, device_id = row

    if sensor_type != 'accelerometer':
        return None

    has_accelerometer_movement = is_moving(x, y, z)

    # print("has_accelerometer_movement", has_accelerometer_movement)
    if has_accelerometer_movement:
        update_query = """
            UPDATE devices 
            SET last_movement = NOW() 
            WHERE id = %s
            RETURNING *
        """
        subscription.db.execute(update_query, (device_id,))
        subscription.send_notification("Phone Moving", "The phone is moving", 10)
        # logging.info(f"Updated last_movement for device_id {device_id}")

    return has_accelerometer_movement

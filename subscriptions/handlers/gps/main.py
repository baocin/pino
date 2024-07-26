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
import math
from collections import defaultdict
import requests

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(filename='subscription_handler.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_distance(point1, point2):
    try:
        lat1, lon1 = point1[0], point1[1]
        lat2, lon2 = point2[0], point2[1]
        radius = 3959

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = radius * c

        return distance
    except IndexError:
        logging.error(f"IndexError in calculate_distance: point1={point1}, point2={point2}")
        return None

def calculate_speed(first_point, last_point, time_diff):
    try:
        distance = calculate_distance(first_point, last_point)
        if distance is None:
            logging.warning("Failed to calculate distance between GPS points.")
            return None
        time_diff_hours = time_diff.total_seconds() / 3600  # Convert timedelta to hours
        speed = distance / time_diff_hours
        
        return speed
    except Exception as e:
        logging.error(f"Unexpected error in calculate_speed: {e}")
        return None

def reverse_geocode(lat, lon):
    try:
        base_url = f"http://{os.getenv('NOMINATIM_URL')}:{os.getenv('NOMINATIM_PORT')}/reverse"
        params = {
            'lat': lat,
            'lon': lon,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 18
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(base_url, params=params, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if 'address' in data:
                return data['address']
            else:
                logging.warning(f"No address found for coordinates: {lat}, {lon}")
                return None
        else:
            logging.error(f"Failed to fetch address for coordinates {lat}, {lon}. Status code: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Error in reverse geocoding for coordinates {lat}, {lon}: {e}")
        return None

def handle_gps_data(subscription, rows):
    gps_points = rows

    speed = None
    if len(gps_points) >= 2:
        first_point = gps_points[0]
        last_point = gps_points[-1]
        last_lat, last_lon = last_point[0], last_point[1]
        time_diff = abs(first_point[2] - last_point[2]) / 1000  # Convert milliseconds to seconds
        time_diff_minutes = timedelta(seconds=time_diff)
        speed = calculate_speed((first_point[0], first_point[1]), (last_point[0], last_point[1]), time_diff_minutes)
        device_id = first_point[3]
        if speed is not None:
            if speed < 0.1:
                speed = 0
            # Update speed for the device
            update_query = """
                UPDATE devices 
                SET speed = %s, location=%s
                WHERE id = %s
                RETURNING id
            """
            point = f"POINT({last_lon} {last_lat})"
            subscription.db.execute(update_query, (speed, point, device_id))

        # Reverse geocode the last point
        address = reverse_geocode(last_lat, last_lon)
        if address:
            # logging.info(f"Reverse geocoded address: {address}")
            
            # Update the address for the device
            update_address_query = """
                UPDATE devices 
                SET last_known_address = %s::jsonb 
                WHERE id = %s
                RETURNING id
            """
            address_json = json.dumps(address)
            subscription.db.execute(update_address_query, (address_json, device_id))
        
    return speed

import os
import json
import logging
from dotenv import load_dotenv
from tools.gotify.gotify import send_gotify_message
from datetime import datetime, timedelta
import time
import math
from collections import defaultdict

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(filename='subscription_handler.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_distance(point1, point2):
    lat1, lon1 = point1[1], point1[2]
    lat2, lon2 = point2[1], point2[2]
    radius = 3959

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = radius * c

    return distance

def handle_gps_data(subscription, differences):
    gps_points = differences
    
    speed = None
    if len(gps_points) >= 2:
        first_point = gps_points[0]
        last_point = gps_points[-1]
        
        # Ensure gps_points are within minutes of each other
        time_diff_minutes = abs(first_point[4] - last_point[4]) / 60000  # Convert milliseconds to minutes
        if time_diff_minutes > 5:  # Assuming 5 minutes as the threshold
            logging.warning("GPS points are not within the acceptable time range.")
            return None
        
        distance = calculate_distance(first_point, last_point)
        
        # Calculate total time based on 'time' column
        time_diff_hours = time_diff_minutes / 60  # Convert minutes to hours
        speed = distance / time_diff_hours
        
        logging.info(f"Speed calculated: {speed:.2f} mph")
        if speed > 90:
            subscription.send_notification("GPS Speed Alert", f"Speed calculated: {speed:.2f} mph", 10)

    return speed

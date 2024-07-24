import logging
import json
from datetime import datetime

def handle_device_log(subscription, device_rows):
    for device_row in device_rows:
        device_id = device_row[0]
        last_movement = device_row[1]
        screen_up = device_row[2]
        speed = device_row[3]
        is_online = device_row[4]
        location = device_row[5]

        # Insert into device_status_log
        insert_query = """
            INSERT INTO device_status_log 
            (device_id, timestamp, last_movement, screen_up, speed, online, location)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        subscription.db.execute(insert_query, (device_id, datetime.now(), last_movement, screen_up, speed, is_online, location))

import logging
from datetime import datetime, timedelta

def handle_check_connection(subscription, latest_gps_rows):
    current_time = datetime.now().timestamp()
    offline_threshold = 1 * 60 #sec

    for latest_device_gps_row in latest_gps_rows:
        device_id = latest_device_gps_row[0]
        last_gps_time = latest_device_gps_row[1]
        time_since_last_row = current_time - (last_gps_time/1000)
        is_online = time_since_last_row <= offline_threshold
        update_online_query = """
                    UPDATE devices 
                    SET online = %s 
                    WHERE id = %s
                    RETURNING id
            """
        result = subscription.db.execute(update_online_query, (is_online, device_id))
        if not is_online:
            subscription.send_notification(f"Device {device_id} is offline","",10)

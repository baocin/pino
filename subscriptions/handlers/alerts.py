import logging
from datetime import datetime, timedelta

def handle_get_back_to_work(subscription, result):
    if result:
        try:
            phone_status = result[0]['phone_status']
            if phone_status == 'Phone is likely being held':
                subscription.send_notification(
                    "Get back to work!",
                    "You've been holding your phone for too long. Time to focus!",
                    priority=5
                )
            else:
                logging.info("Phone is not being held, no notification sent.")
        except (KeyError, IndexError) as e:
            logging.error(f"Error processing result in handle_get_back_to_work: {e}")
    else:
        logging.info("No result received in handle_get_back_to_work")

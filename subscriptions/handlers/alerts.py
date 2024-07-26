import logging
from datetime import datetime, timedelta

def handle_get_back_to_work(subscription, result):
    print("Sending handle_get_back_to_work notification")
    subscription.send_notification(
        "Get back to work!",
        "You've been holding your phone for too long. Time to focus!",
        priority=10
    )
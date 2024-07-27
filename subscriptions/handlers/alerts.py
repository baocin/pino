import logging
from datetime import datetime, timedelta

def handle_get_back_to_work(subscription, result):
    if result and result[0] is not None and result[0][0] > 200:
        subscription.send_notification(
            "Get back to work!",
            "You've been holding your phone for too long. Time to focus!",
            priority=10
        )
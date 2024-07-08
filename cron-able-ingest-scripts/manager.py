import threading
import schedule
import time
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
from db import DB  # Import the DB class from db.py

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='manager.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

class TaskManager:
    def __init__(self):
        self.running_tasks = {}
        self.db = self.setup_db()

    def setup_db(self):
        try:
            db_instance = DB()
            db_instance.initialize_db()
            logging.info("Database connection established via DB class")
            return db_instance.connection
        except Exception as e:
            logging.error(f"Error connecting to the database via DB class: {e}")
            return None

    def run_task(self, task, *args):
        task_name = task.__name__
        if self.running_tasks.get(task_name, False):
            logging.info(f"{task_name} already in progress, skipping this run.")
            return

        def task_wrapper():
            self.running_tasks[task_name] = True
            try:
                task(*args)
            except Exception as e:
                logging.error(f"Error running task {task_name}: {e}")
            finally:
                self.running_tasks[task_name] = False

        thread = threading.Thread(target=task_wrapper)
        thread.start()

    def schedule_task(self, interval, unit, task, *args):
        if unit == 'seconds':
            schedule.every(interval).seconds.do(self.run_task, task, *args)
        elif unit == 'minutes':
            schedule.every(interval).minutes.do(self.run_task, task, *args)
        elif unit == 'hours':
            schedule.every(interval).hours.do(self.run_task, task, *args)
        elif unit == 'days':
            schedule.every(interval).days.at("00:00").do(self.run_task, task, *args)
        else:
            logging.error(f"Unsupported time unit: {unit}")

    def start(self):
        while True:
            schedule.run_pending()
            time.sleep(1)

# Example usage
if __name__ == "__main__":
    manager = TaskManager()
    from calendars.injest import CalendarInjest
    from server_stats.injest import SystemStatsRecorder
    from emails.injest import EmailInjest
    from contacts.injest import ContactsInjest
    from budget.injest import BudgetInjest

    # Define the task to download the Google Doc as CSV
    def fetch_budget_task():
        logging.info("Running budget download task")
        budget_injest = BudgetInjest(manager.db)
        budget_injest.fetch_budget()

    # Define the task to fetch emails
    def fetch_email_task():
        logging.info("Running email fetch task")
        email_injest = EmailInjest(manager.db)
        email_injest.fetch_all_emails()

    # Define the task to fetch calendar events
    def fetch_calendar_task():
        logging.info("Running calendar fetch task")
        calendar_injest = CalendarInjest(manager.db)
        calendar_injest.fetch_all_calendar_events()

    # Define the task to record server stats
    def record_server_stats_task():
        logging.info("Running server stats recording task")
        system_stats_recorder = SystemStatsRecorder(manager.db)
        system_stats_recorder.record_stats()

    # Define the task to fetch contacts
    def fetch_contacts_task():
        logging.info("Running contacts fetch task")
        contacts_injest = ContactsInjest(manager.db)
        contacts_injest.fetch_all_contacts()

    # fetch_contacts_task()
    # record_server_stats_task()
    # fetch_email_task()
    # fetch_calendar_task()
    # fetch_budget_task()

    # Schedule the tasks
    manager.schedule_task(1, 'hours', fetch_budget_task)
    manager.schedule_task(5, 'minutes', fetch_email_task)
    manager.schedule_task(5, 'minutes', fetch_calendar_task)
    manager.schedule_task(5, 'minutes', record_server_stats_task)
    manager.schedule_task(1, 'hours', fetch_contacts_task)

    # Start the task manager
    manager.start()

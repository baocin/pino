import threading
import schedule
import time
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
from db import DB 
import asyncio



# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='manager.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

class TaskManager:
    def __init__(self):
        self.fetch_budget_lock = threading.Lock()
        self.fetch_email_lock = threading.Lock()
        self.fetch_calendar_lock = threading.Lock()
        self.record_server_stats_lock = threading.Lock()
        self.fetch_contacts_lock = threading.Lock()
        self.fetch_tweets_lock = threading.Lock()
        self.fetch_github_lock = threading.Lock()  # Added lock for GitHub scrape
        self.db = self.setup_db()

    def setup_db(self):
        try:
            db_instance = DB()
            db_instance.initialize_db()
            logging.info("Database connection established via DB class")
            return db_instance
        except Exception as e:
            logging.error(f"Error connecting to the database via DB class: {e}")
            return None

    def run_task(self, task, task_lock, *args):
        if not task_lock.acquire(blocking=False):
            logging.info(f"{task.__name__} already in progress, skipping this run.")
            return

        def task_wrapper():
            try:
                task(*args)
            except Exception as e:
                logging.error(f"Error running task {task.__name__}: {e}")
            finally:
                task_lock.release()

        thread = threading.Thread(target=task_wrapper)
        thread.start()

    def schedule_task(self, interval, unit, task, task_lock, *args):
        if unit == 'seconds':
            schedule.every(interval).seconds.do(self.run_task, task, task_lock, *args)
        elif unit == 'minutes':
            schedule.every(interval).minutes.do(self.run_task, task, task_lock, *args)
        elif unit == 'hours':
            schedule.every(interval).hours.do(self.run_task, task, task_lock, *args)
        elif unit == 'days':
            schedule.every(interval).days.at("00:00").do(self.run_task, task, task_lock, *args)
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
    from tweets.injest import TweetInjest
    from github.scrape import GitHubScrape

    # Define the task to download the Google Doc as CSV
    def fetch_budget_task():
        logging.info("Running budget download task")
        budget_injest = BudgetInjest(DB)
        budget_injest.fetch_budget()

    # Define the task to fetch emails
    def fetch_email_task():
        logging.info("Running email fetch task")
        email_injest = EmailInjest(DB)
        email_injest.fetch_all_emails()

    # Define the task to fetch calendar events
    def fetch_calendar_task():
        logging.info("Running calendar fetch task")
        calendar_injest = CalendarInjest(DB)
        calendar_injest.fetch_all_calendar_events()

    # Define the task to record server stats
    def record_server_stats_task():
        logging.info("Running server stats recording task")
        system_stats_recorder = SystemStatsRecorder(DB)
        system_stats_recorder.record_stats()

    # Define the task to fetch contacts
    def fetch_contacts_task():
        logging.info("Running contacts fetch task")
        contacts_injest = ContactsInjest(DB)
        contacts_injest.fetch_all_contacts()

    async def fetch_tweets_task():
        logging.info("Running tweets fetch task")
        tweets_injest = TweetInjest(DB)
        await tweets_injest.setup()
        await tweets_injest.scrape_tweets()
        await tweets_injest.screenshot_all_tweets()

    async def fetch_github_task():
        logging.info("Running GitHub scrape task")
        github_scrape = GitHubScrape(DB)
        await github_scrape.setup()
        await github_scrape.fetch_github_stars()

    def run_async_task(task, task_lock, *args):
        if not task_lock.acquire(blocking=False):
            logging.info(f"{task.__name__} already in progress, skipping this run.")
            return

        async def task_wrapper():
            try:
                await task(*args)
            except Exception as e:
                logging.error(f"Error running task {task.__name__}: {e}")
            finally:
                task_lock.release()

        asyncio.run(task_wrapper())

    # fetch_contacts_task()
    # record_server_stats_task()
    # fetch_email_task()
    # fetch_calendar_task()
    # calendar_injest = CalendarInjest(DB)
    # calendar_injest.fetch_all_calendar_events()
    # fetch_budget_task()
    # asyncio.run(fetch_tweets_task())
    # asyncio.run(fetch_github_task())

    # Schedule the tasks
    manager.schedule_task(12, 'hours', fetch_budget_task, manager.fetch_budget_lock)
    manager.schedule_task(5, 'minutes', fetch_email_task, manager.fetch_email_lock)
    manager.schedule_task(15, 'minutes', fetch_calendar_task, manager.fetch_calendar_lock)
    manager.schedule_task(1, 'minutes', record_server_stats_task, manager.record_server_stats_lock)
    manager.schedule_task(1, 'hours', fetch_contacts_task, manager.fetch_contacts_lock)
    manager.schedule_task(12, 'hours', run_async_task, manager.fetch_tweets_lock, fetch_tweets_task)
    manager.schedule_task(12, 'hours', run_async_task, manager.fetch_github_lock, fetch_github_task)

    # run_async_task(fetch_calendar_task, manager.fetch_calendar_lock)

    # run_async_task(fetch_tweets_task, manager.fetch_tweets_lock)
    # run_async_task(fetch_github_task, manager.fetch_github_lock)

    # Start the task manager
    manager.start()

import threading
import time
import logging
from datetime import datetime, timedelta
import os
import sys
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from libraries.db.db import DB

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
        self.fetch_github_lock = threading.Lock()
        self.db = DB(
                host=os.getenv("POSTGRES_HOST"),
                port=os.getenv("POSTGRES_PORT"),
                database=os.getenv("POSTGRES_DB"),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD")
            )
        self.tasks = []

    def add_task(self, interval, task, task_lock, *args):
        self.tasks.append({
            'interval': interval,
            'task': task,
            'lock': task_lock,
            'args': args,
            'last_run': datetime.min
        })

    async def run_task(self, task_info):
        if not task_info['lock'].acquire(blocking=False):
            logging.info(f"{task_info['task'].__name__} already in progress, skipping this run.")
            return

        try:
            if asyncio.iscoroutinefunction(task_info['task']):
                await task_info['task'](*task_info['args'])
            else:
                task_info['task'](*task_info['args'])
        except Exception as e:
            logging.error(f"Error running task {task_info['task'].__name__}: {e}")
        finally:
            task_info['lock'].release()

    async def start(self):
        while True:
            now = datetime.now()
            for task in self.tasks:
                if now - task['last_run'] >= timedelta(seconds=task['interval']):
                    task['last_run'] = now
                    asyncio.create_task(self.run_task(task))
            await asyncio.sleep(1)

# Example usage
if __name__ == "__main__":
    manager = TaskManager()
    
    from calendars.injest import CalendarInjest
    from server_stats.injest import SystemStatsRecorder
    from emails.injest import EmailInjest
    from contacts.injest import ContactsInjest
    from budget.injest import BudgetInjest
    from scheduled.tweets.injest import TweetInjest
    from github.scrape import GitHubScrape

    def fetch_budget_task():
        logging.info("Running budget download task")
        budget_injest = BudgetInjest(DB)
        budget_injest.fetch_budget()

    def fetch_email_task():
        logging.info("Running email fetch task")
        email_injest = EmailInjest(DB)
        email_injest.fetch_all_emails()

    def fetch_calendar_task():
        logging.info("Running calendar fetch task")
        calendar_injest = CalendarInjest(DB)
        calendar_injest.fetch_all_calendar_events()

    def record_server_stats_task():
        logging.info("Running server stats recording task")
        system_stats_recorder = SystemStatsRecorder(DB)
        system_stats_recorder.record_stats()

    def fetch_contacts_task():
        logging.info("Running contacts fetch task")
        contacts_injest = ContactsInjest(DB)
        contacts_injest.fetch_all_contacts()

    async def fetch_tweets_task():
        logging.info("Running tweets fetch task")
        try:
            tweets_injest = TweetInjest(DB)
            await tweets_injest.setup()
            tweets = await tweets_injest.scrape_tweets()
            if tweets:
                await tweets_injest.screenshot_all_tweets()
            else:
                logging.warning("No tweets were scraped.")
        except Exception as e:
            logging.error(f"Error in fetch_tweets_task: {e}")

    async def fetch_github_task():
        logging.info("Running GitHub scrape task")
        github_scrape = GitHubScrape(DB)
        await github_scrape.setup()
        await github_scrape.fetch_github_stars()

    seconds_in_hour = 3600

    manager.add_task(seconds_in_hour * 12, fetch_budget_task, manager.fetch_budget_lock)
    manager.add_task(60, fetch_email_task, manager.fetch_email_lock)
    manager.add_task(seconds_in_hour * 0.5, fetch_calendar_task, manager.fetch_calendar_lock)
    manager.add_task(60, record_server_stats_task, manager.record_server_stats_lock)
    manager.add_task(seconds_in_hour * 12, fetch_contacts_task, manager.fetch_contacts_lock)
    manager.add_task(seconds_in_hour * 6, fetch_tweets_task, manager.fetch_tweets_lock)
    manager.add_task(seconds_in_hour * 6, fetch_github_task, manager.fetch_github_lock)


    # Write a file to indicate that the service has started
    with open('started.txt', 'w') as f:
        f.write('Scheduled injest service started')

    # Start the task manager
    asyncio.run(manager.start())

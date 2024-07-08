from injest_mail import EmailInjest
from injest_server_stats import SystemStatsRecorder
from injest_calendars import CalendarInjest
from injest_budget import download_google_doc_as_csv
from dotenv import load_dotenv
from postgres import PostgresInterface
import os

load_dotenv() 

def main():
    # Initialize the database interface
    db = PostgresInterface(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432))
    )
    db.connect()

    # Initialize and start email ingestion
    email_injest = EmailInjest(db)
    email_injest.start_sync()

    # Initialize and start server stats recording
    server_stats_recorder = SystemStatsRecorder(db, interval=1)
    server_stats_recorder.start_sync()

    # Initialize and start calendar ingestion
    calendar_injest = CalendarInjest(db)
    calendar_injest.start_sync()

    # Start budget download
    google_doc_url = "https://docs.google.com/spreadsheets/d/1Vol4TOCPxHUAOd7jC89hLZ1cts7l-vcflidZ8uzbjX4/export?format=csv"
    save_path = "./knowledge_base/budget.csv"
    download_google_doc_as_csv(google_doc_url, save_path)

if __name__ == "__main__":
    main()

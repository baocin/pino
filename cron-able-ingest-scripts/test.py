import os
import random
import string
import psycopg2
from datetime import datetime, timedelta
from emails.injest import EmailInjest
from calendars.injest import CalendarInjest
from contacts.injest import ContactsInjest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure database connection
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )

# Initialize database and tables
def initialize_db():
    connection = get_db_connection()
    cursor = connection.cursor()
    
    # Create emails table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emails (
        email_id VARCHAR PRIMARY KEY,
        subject VARCHAR,
        sender VARCHAR,
        date_received TIMESTAMP,
        body TEXT,
        attachments BYTEA[],
        seen BOOLEAN,
        receiver VARCHAR,
        pull_id INTEGER
    )
    """)
    
    # Create calendar_events table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calendar_events (
        event_id VARCHAR PRIMARY KEY,
        summary VARCHAR,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        description TEXT,
        location VARCHAR,
        pull_id INTEGER
    )
    """)
    
    # Create contacts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        full_name VARCHAR,
        email VARCHAR PRIMARY KEY,
        phone VARCHAR
    )
    """)
    
    connection.commit()
    cursor.close()
    connection.close()

# Generate random data
def random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def random_email():
    return f"{random_string(5)}@{random_string(5)}.com"

def random_datetime():
    return datetime.now() - timedelta(days=random.randint(0, 365))

# Insert random data using the defined methods
def insert_random_data():
    db = get_db_connection()
    
    # Insert random emails
    email_injest = EmailInjest(db)
    for _ in range(5):
        email_data = {
            "email_id": random_string(10),
            "subject": random_string(20),
            "sender": random_email(),
            "date_received": random_datetime(),
            "body": random_string(100),
            "attachments": [psycopg2.Binary(random_string(50).encode())],
            "seen": random.choice([True, False]),
            "receiver": random_email(),
            "pull_id": random.randint(1, 100)
        }
        email_injest.insert_email_data(**email_data)
    
    # Insert random calendar events
    calendar_injest = CalendarInjest(db)
    for _ in range(5):
        calendar_data = {
            "event_id": random_string(10),
            "summary": random_string(20),
            "start": random_datetime(),
            "end": random_datetime() + timedelta(hours=1),
            "description": random_string(100),
            "location": random_string(30),
            "pull_id": random.randint(1, 100)
        }
        calendar_injest.insert_calendar_data(calendar_data)
    
    # Insert random contacts
    contacts_injest = ContactsInjest(db)
    for _ in range(5):
        contact_data = {
            "full_name": random_string(15),
            "email": random_email(),
            "phone": random_string(10)
        }
        contacts_injest.insert_contact_data(contact_data)
    
    db.close()

if __name__ == "__main__":
    initialize_db()
    insert_random_data()

import os
import psycopg2
import logging
from dotenv import load_dotenv

class DB:
    def __init__(self):
        load_dotenv()
        self.connection = self.connect()

    @staticmethod
    def connect():
        load_dotenv()
        try:
            connection = psycopg2.connect(
                dbname=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT")
            )
            return connection
        except Exception as e:
            logging.error(f"Error connecting to the database: {e}")
            raise
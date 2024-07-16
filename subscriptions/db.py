import os
import psycopg2
import select
import logging
import time
from dotenv import load_dotenv
import threading

class DB:
    def __init__(self):
        load_dotenv()
        self.connection = self.connect()
        self.cursor = self.connection.cursor()

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

    @staticmethod
    def initialize_db():
        connection = DB.connect()
        cursor = connection.cursor()
        # try:
        #     with open('../db/initialize_from_zero.sql', 'r') as sql_file:
        #         sql_commands = sql_file.read()
        #         cursor.execute(sql_commands)
        #     logging.info("Created table documents if not exists.")
        #     connection.commit()
        # except Exception as e:
        #     logging.error(f"Error initializing database: {e}")

        cursor.close()
        logging.info("Database initialization complete.")
        return connection

    # def listen_to_channel(self, channel_name):
    #     if not hasattr(self, 'cursor'):
    #         self.cursor = self.connection.cursor()
    #     self.cursor.execute(f"LISTEN {channel_name};")
    #     logging.info(f"Listening to channel: {channel_name}")
    #     return_value = f"Listening to channel: {channel_name}"
    #     logging.info(f"Return value: {return_value}")
    #     return return_value
    
    # def notify(self, channel_name, payload):
    #     if not hasattr(self, 'cursor'):
    #         self.cursor = self.connection.cursor()
    #     self.cursor.execute(f"NOTIFY {channel_name}, '{payload}';")
    #     self.connection.commit()
    #     logging.info(f"Notified channel: {channel_name} with payload: {payload}")

    # def start_listening(self, callback):
    #     try:
    #         while True:
    #             self.connection.poll()
    #             while self.connection.notifies:
    #                 notify = self.connection.notifies.pop(0)
    #                 logging.info(f"Received notification: {notify}")
    #                 callback(notify)
    #             if select.select([self.connection], [], [], 5) == ([], [], []):
    #                 logging.info("No notifications received")
    #     except Exception as e:
    #         logging.error(f"Error while listening for notifications: {e}")
    #     finally:
    #         if hasattr(self, 'cursor'):
    #             self.cursor.close()
    #         if hasattr(self, 'connection'):
    #             self.connection.close()

    def poll_query(self, query, interval, callback):
        self._cancel_polling = False  # Attribute to control polling
        self._polling_thread = threading.Thread(target=self._polling_loop, args=(query, interval, callback))
        self._polling_thread.start()

    def _polling_loop(self, query, interval, callback):
        previous_result = None
        first_fetch = True
        
        while not self._cancel_polling:
            try:
                self.cursor.execute(query)
                result = self.cursor.fetchall()
                
                if first_fetch:
                    first_fetch = False
                else:
                    differences = [row for row in result if row not in previous_result]
                    if differences:
                        callback(differences)
                
                if result != None:
                    previous_result = result
                logging.info(f"Result: {result}")

                time.sleep(interval)
            except Exception as e:
                logging.error(f"Error executing query: {query} {e}")
                break

    def cancel_polling(self):
        self._cancel_polling = True
        if self._polling_thread.is_alive():
            self._polling_thread.join()

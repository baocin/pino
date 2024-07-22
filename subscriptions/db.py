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

    def poll_query(self, query, interval, callback, trigger_on_all_queries=False):
        self._cancel_polling = False
        self._polling_thread = threading.Thread(target=self._polling_loop, args=(query, interval, callback, trigger_on_all_queries))
        self._polling_thread.start()

    def _polling_loop(self, query, interval, callback, trigger_on_all_queries):
        previous_result = None
        first_fetch = True
        
        while not self._cancel_polling:
            try:
                self.cursor.execute(query)
                result = self.cursor.fetchall()
                
                if first_fetch:
                    first_fetch = False
                else:
                    if trigger_on_all_queries:
                        callback(result)
                    else:
                        differences = [row for row in result if row not in previous_result]
                        if differences:
                            callback(differences)
                
                if result is not None:
                    previous_result = result

                time.sleep(interval)
            except Exception as e:
                logging.error(f"Error executing query: {query} {e}")
                break

    def cancel_polling(self):
        self._cancel_polling = True
        if self._polling_thread.is_alive():
            self._polling_thread.join()

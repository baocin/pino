import os
import psycopg2
import logging
import time
import json
from dotenv import load_dotenv
import threading

class DB:
    def __init__(self, host, port, database, user, password):
        self.connection = self.connect(host, port, database, user, password)
        self.cursor = self.connection.cursor()

    @staticmethod
    def connect(host, port, database, user, password):
        try:
            connection = psycopg2.connect(
                host=host or os.getenv("POSTGRES_HOST"),
                port=port or os.getenv("POSTGRES_PORT"),
                database=database or os.getenv("POSTGRES_DB"),
                user=user or os.getenv("POSTGRES_USER"),
                password=password or os.getenv("POSTGRES_PASSWORD")
            )
            return connection
        except Exception as e:
            logging.error(f"Error connecting to the database: {e}")
            raise

    def query(self, query, params=None):
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()


    def execute(self, query, params=None):
        def run_query():
            cursor = self.connection.cursor()
            try:
                cursor.execute(query, params)
                self.connection.commit()
                return cursor.fetchall()
            except psycopg2.Error as e:
                print(f"The error '{e}' occurred")
                self.connection.rollback()
                return None
            finally:
                cursor.close()

        thread = threading.Thread(target=run_query)
        thread.start()


    def poll_query(self, query, interval, callback, trigger_on_all_queries=False):
        self._cancel_polling = False
        self._polling_thread = threading.Thread(target=self._polling_loop, args=(query, interval, callback, trigger_on_all_queries))
        self._polling_thread.start()

    def _polling_loop(self, query, interval, callback, trigger_on_all_queries):
        previous_result = None
        first_fetch = True
        
        while not self._cancel_polling:
            try:
                cursor = self.connection.cursor()
                cursor.execute(query)
                result = cursor.fetchall()
                
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
            finally:
                cursor.close()

    def cancel_polling(self):
        self._cancel_polling = True
        if self._polling_thread.is_alive():
            self._polling_thread.join()


    def pgvector_similarity_search(self, table_name, vector_column, query_vector, columns='*', top_k=10, max_retries=3):
        """
        Perform a similarity search using pgvector with retry logic.

        :param table_name: Name of the table to search.
        :param vector_column: Name of the column containing the vectors.
        :param query_vector: The query vector to compare against.
        :param columns: Columns to select in the query (default is '*' for all columns).
        :param top_k: Number of top similar results to return.
        :param max_retries: Maximum number of retry attempts.
        :return: List of tuples containing the top_k similar results.
        """
        retries = 0
        while retries < max_retries:
            try:
                # Convert the query vector to a string format suitable for SQL
                query_vector_str = ','.join(map(str, query_vector))
                
                # Construct the SQL query
                sql_query = f"""
                    SELECT {columns}, {vector_column} <-> '[{query_vector_str}]' AS similarity
                    FROM {table_name}
                    ORDER BY similarity
                    LIMIT {top_k};
                """
                
                # Create a new cursor for this operation
                with self.connection.cursor() as cursor:
                    # Execute the query
                    cursor.execute(sql_query)
                    results = cursor.fetchall()
                
                return results
            except Exception as e:
                retries += 1
                logging.error(f"Error performing similarity search (attempt {retries}/{max_retries}): {e}")
                self.connection.rollback()  # Rollback the transaction
                if retries == max_retries:
                    logging.error("Max retries reached. Returning empty list.")
                    return []
                time.sleep(1)  # Wait for 1 second before retrying

    def get_known_classes(self, type='audio'):
        result = self.query("SELECT name, embedding, radius_threshold, embedded_data, id, gotify_priority, ignore FROM known_classes WHERE datatype = %s", (type,))
        
        known_classes = []
        for row in result:
            if row[1]:  # Check if embedding is not None
                embedding = [float(x) for x in row[1][1:-1].split(',')]  # Remove brackets and split
            else:
                embedding = None
            known_classes.append({
                'name': row[0],
                'embedding': embedding,
                'radius_threshold': row[2],
                'embedded_data': row[3],
                'id': row[4]
            })
        
        return known_classes
    
    def insert_screenshot_data(self, timestamp, image_data, device_id):
        query = """
        INSERT INTO screenshot_data (timestamp, image_data, device_id)
        VALUES (%s, %s, %s);
        """
        self.execute(query, (timestamp, image_data, device_id))
    def execute_query(self, query, params=None):
        def run_query():
            cursor = self.connection.cursor()
            try:
                # logging.info(f"Executing query: {query} with params: {params}")
                cursor.execute(query, params)
                self.connection.commit()
                try:
                    return cursor.fetchall()
                except psycopg2.ProgrammingError:
                    # Query was not a SELECT, so no results to fetch
                    return None
            except psycopg2.Error as e:
                if str(e) != 'no results to fetch':
                    logging.error(f"The error '{e}' occurred")
                self.connection.rollback()
            finally:
                cursor.close()

        thread = threading.Thread(target=run_query)
        thread.start()
            
            
    def sync_query(self, query, params=None):
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            try:
                result = cursor.fetchall()
                return result
            except psycopg2.ProgrammingError:
                # Query was not a SELECT, so no results to fetch
                return None
        except psycopg2.Error as e:
            if str(e) != 'no results to fetch':
                print(f"The error '{e}' occurred")
            self.connection.rollback()
            return None
        finally:
            cursor.close()
    def close_connection(self):
        if self.connection:
            self.connection.close()
            print("The connection is closed")

    def insert_gps_data(self, latitude, longitude, altitude, time, device_id):
        query = """
        INSERT INTO gps_data (latitude, longitude, altitude, time, device_id)
        VALUES (%s, %s, %s, %s, %s);
        """
        self.execute_query(query, (latitude, longitude, altitude, time, device_id))

    def insert_sensor_data(self, sensor_type, x, y, z, device_id):
        query = """
        INSERT INTO sensor_data (sensor_type, x, y, z, device_id)
        VALUES (%s, %s, %s, %s, %s);
        """
        self.execute_query(query, (sensor_type, x, y, z, device_id))
        

    def insert_app_usage_stats(self, package_name, total_time_in_foreground, first_timestamp, last_timestamp, last_time_used, last_time_visible, last_time_foreground_service_used, total_time_visible, total_time_foreground_service_used):
        check_query = """
        SELECT id FROM app_usage_stats 
        WHERE package_name = %s AND DATE(created_at) = DATE(NOW());
        """
        cursor = self.connection.cursor()
        cursor.execute(check_query, (package_name,))
        existing_record = cursor.fetchone()
        
        if existing_record:
            update_query = """
            UPDATE app_usage_stats
            SET total_time_in_foreground = %s, first_timestamp = %s, last_timestamp = %s, last_time_used = %s, last_time_visible = %s, last_time_foreground_service_used = %s, total_time_visible = %s, total_time_foreground_service_used = %s
            WHERE id = %s;
            """
            cursor.execute(update_query, (total_time_in_foreground, first_timestamp, last_timestamp, last_time_used, last_time_visible, last_time_foreground_service_used, total_time_visible, total_time_foreground_service_used, existing_record[0]))
        else:
            insert_query = """
            INSERT INTO app_usage_stats (package_name, total_time_in_foreground, first_timestamp, last_timestamp, last_time_used, last_time_visible, last_time_foreground_service_used, total_time_visible, total_time_foreground_service_used)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cursor.execute(insert_query, (package_name, total_time_in_foreground, first_timestamp, last_timestamp, last_time_used, last_time_visible, last_time_foreground_service_used, total_time_visible, total_time_foreground_service_used))
        
        self.connection.commit()
        cursor.close()

        

    def insert_key_event_data(self, keyCode, action):
        query = """
        INSERT INTO key_event_data (keyCode, action)
        VALUES (%s, %s);
        """
        self.execute_query(query, (keyCode, action))

    def insert_motion_event_data(self, x, y, action):
        query = """
        INSERT INTO motion_event_data (x, y, action)
        VALUES (%s, %s, %s);
        """
        self.execute_query(query, (x, y, action))

    def insert_notification_data(self, data):
        query = """
        INSERT INTO notification_data (data)
        VALUES (%s);
        """
        self.execute_query(query, (data,))

    def insert_audio_data(self, taken_at, data, device_id):
        query = """
        INSERT INTO audio_data (taken_at, data, device_id)
        VALUES (%s, %s, %s)
        RETURNING id;
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (taken_at, data, device_id))
        row_id = cursor.fetchone()[0]
        self.connection.commit()
        cursor.close()
        return row_id

    def insert_speech_data(self, text, result, started_at, ended_at, device_id):
        query = """
        INSERT INTO speech_data (text, result, started_at, ended_at, device_id)
        VALUES (%s, %s::json, %s, %s, %s);
        """
        self.execute_query(query, (text, result, started_at, ended_at, device_id))
        
    def insert_manual_photo_data(self, photo, is_screenshot, device_id):
        query = """
        INSERT INTO manual_photo_data (photo, is_screenshot, device_id)
        VALUES (%s, %s, %s);
        """
        self.execute_query(query, (photo, is_screenshot, device_id))
        
    def insert_screenshot_data(self, data, device_id):
        query = """
        INSERT INTO screenshot_data (data, device_id)
        VALUES (%s, %s);
        """
        self.execute_query(query, (data, device_id))
    
    def update_screenshot_data(self, id, clip):
        query = """
        UPDATE screenshot_data
        SET clip = %s
        WHERE id = %s;
        """
        self.execute_query(query, (clip, id))

    def insert_websocket_metadata(self, connected_at, disconnected_at, client_ip, client_user_agent, status):
        query = """
        INSERT INTO websocket_metadata (connected_at, disconnected_at, client_ip, client_user_agent, status)
        VALUES (%s, %s, %s, %s, %s);
        """
        self.execute_query(query, (connected_at, disconnected_at, client_ip, client_user_agent, status))

    def email_exists(self, email_id):
        query = """
        SELECT 1 FROM email_data WHERE email_id = %s;
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (email_id,))
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists

    def insert_email_data(self, email_id, subject, sender, received_at, body, attachments_bytea, seen, receiver):
        query = """
        INSERT INTO email_data (email_id, subject, sender, received_at, body, attachments, seen, receiver)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        self.execute_query(query, (email_id, subject, sender, received_at, body, attachments_bytea, seen, receiver))

    def insert_calendar_data(self, event_data):
        query = """
        INSERT INTO calendar_data (event_id, summary, start, end, description, location)
        VALUES (%s, %s, %s, %s, %s, %s);
        """
        self.execute_query(query, (
            event_data['event_id'], 
            event_data['summary'], 
            event_data['start'], 
            event_data['end'], 
            event_data['description'], 
            event_data['location']
        ))

    def event_exists(self, event_id):
        query = """
        SELECT 1 FROM event_data WHERE event_id = %s;
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (event_id,))
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists

    def insert_browser_data(self, data):
        query = """
        INSERT INTO browser_data (
            device_id, document, active, audible, auto_discardable, discarded, fav_icon_url, group_id, height, 
            highlighted, id, incognito, index, last_accessed, muted_info, pinned, selected, status, 
            title, url, width, window_id, type, useragent
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        );
        """
        self.execute_query(query, (6, # assume device id 6 - web
            data['document'], data['active'], data['audible'], data['autoDiscardable'], data['discarded'], 
            data['favIconUrl'], data['groupId'], data['height'], data['highlighted'], data['id'], 
            data['incognito'], data['index'], data['lastAccessed'], json.dumps(data['mutedInfo']), 
            data['pinned'], data['selected'], data['status'], data['title'], data['url'], data['width'], 
            data['windowId'], data['type'], data['useragent']
        ))
        
    def insert_server_stats(self, stat, device_id):
        query = """
        INSERT INTO server_stats (timestamp, disk_usage, cpu_usage, ram_usage, gpu_usage, device_id)
        VALUES (%s, %s, %s, %s, %s);
        """
        self.execute_query(query, (
            stat['timestamp'], 
            json.dumps(stat['disk_usage']), 
            stat['cpu_usage'], 
            json.dumps(stat['ram_usage']), 
            json.dumps(stat['gpu_usage']),
            device_id
        ))
    

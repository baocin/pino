import psycopg2
from psycopg2 import sql
import threading
import json

class PostgresInterface:
    def __init__(self, dbname, user, password, host='localhost', port=5432):
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.connection = None

    def connect(self):
        try:
            self.connection = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            print("Connection to PostgreSQL DB successful")
        except Exception as e:
            print(f"The error '{e}' occurred")

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
                cursor.execute(query, params)
                self.connection.commit()
            except psycopg2.Error as e:
                print(f"The error '{e}' occurred")
                self.connection.rollback()
            finally:
                cursor.close()

        thread = threading.Thread(target=run_query)
        thread.start()
            
    def sync_query(self, query, params=None):
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall()
            return result
        except psycopg2.Error as e:
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
    

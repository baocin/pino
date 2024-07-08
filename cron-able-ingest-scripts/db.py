import os
import psycopg2
from dotenv import load_dotenv

class DB:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        self.connection = self.connect()

    @staticmethod
    def connect():
        load_dotenv()
        return psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )

    @staticmethod
    def initialize_db():
        connection = DB.connect()
        cursor = connection.cursor()

        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("""
        CREATE OR REPLACE FUNCTION uuid_generate_v7()
        RETURNS uuid
        AS $$
        BEGIN
          -- use random v4 uuid as starting point (which has the same variant we need)
          -- then overlay timestamp
          -- then set version 7 by flipping the 2 and 1 bit in the version 4 string
          RETURN encode(
            set_bit(
              set_bit(
                overlay(uuid_send(gen_random_uuid())
                        placing substring(int8send(floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint) from 3)
                        from 1 for 6
                ),
                52, 1
              ),
              53, 1
            ),
            'hex')::uuid;
        END
        $$
        LANGUAGE plpgsql
        VOLATILE;
        """)

        cursor.execute("""
        CREATE OR REPLACE FUNCTION public.timestamp_from_uuid_v7(_uuid uuid)
        RETURNS timestamp without time zone
        LANGUAGE sql
        IMMUTABLE PARALLEL SAFE STRICT LEAKPROOF
        AS $$
          SELECT to_timestamp(('x0000' || substr(_uuid::text, 1, 8) || substr(_uuid::text, 10, 4))::bit(64)::bigint::numeric / 1000);
        $$;
        """)

        # Create emails table if it doesn't exist, with a UUIDv7 primary key and date_received as part of the primary key
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id UUID DEFAULT uuid_generate_v7(),
            email_id VARCHAR,
            subject VARCHAR,
            sender VARCHAR,
            date_received TIMESTAMPTZ NOT NULL,
            body TEXT,
            attachments BYTEA[],
            seen BOOLEAN,
            receiver VARCHAR,
            pull_id INTEGER,
            source_email_address VARCHAR,
            embedding VECTOR(512),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, date_received)
        )
        """)
        connection.commit()
        
        # Create calendar_events table if it doesn't exist, with a UUIDv7 primary key
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id UUID DEFAULT uuid_generate_v7(),
            event_id VARCHAR,
            summary VARCHAR,
            source_calendar VARCHAR,
            start_time TIMESTAMPTZ NOT NULL,
            end_time TIMESTAMPTZ,
            description TEXT,
            location VARCHAR,
            pull_id INTEGER,
            gps_point GEOMETRY(POINT, 4326),
            embedding VECTOR(512),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, start_time)
        )
        """)
        connection.commit()

        # Create contacts table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id UUID DEFAULT uuid_generate_v7() PRIMARY KEY,
            vcard_id VARCHAR,
            full_name VARCHAR,
            email VARCHAR UNIQUE,
            phone VARCHAR,
            last_contacted TIMESTAMPTZ,
            last_seen_timestamp TIMESTAMPTZ,
            embedding VECTOR(512),
            face_images BYTEA[],
            last_seen_location GEOMETRY(POINT, 4326),
            raw_vcard TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """)
        connection.commit()

        # Create server_stats table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_stats (
            id UUID DEFAULT uuid_generate_v7() PRIMARY KEY,
            timestamp TIMESTAMPTZ,
            device_id INTEGER,
            disk_usage FLOAT,
            cpu_usage FLOAT,
            ram_usage FLOAT,
            gpu_usage FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """)
        connection.commit()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id UUID DEFAULT uuid_generate_v7() PRIMARY KEY,
            name VARCHAR,
            gps_point GEOMETRY(POINT, 4326),
            document_text TEXT,
            document_bytes BYTEA,
            embedding VECTOR(512),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """)
        connection.commit()

        # Create hypertables
        cursor.execute("SELECT create_hypertable('emails', 'date_received', chunk_time_interval => INTERVAL '7 day', if_not_exists => TRUE)")
        cursor.execute("SELECT create_hypertable('calendar_events', 'start_time', chunk_time_interval => INTERVAL '14 day', if_not_exists => TRUE)")
        cursor.execute("SELECT create_hypertable('server_stats', 'timestamp', chunk_time_interval => INTERVAL '14 day', if_not_exists => TRUE)")

        
        connection.commit()
        cursor.close()
        return connection

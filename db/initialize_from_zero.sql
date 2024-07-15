-- Tables for scheduled tasks 
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE public."browser_tab_type" AS ENUM ('initial_load', 'visible', 'focused');

CREATE TYPE public."activity_enum" AS ENUM (
	'walking',
	'running',
	'stationary',
	'unknown'
);

CREATE TYPE public."sensor_type_enum" AS ENUM (
	'gravity',
	'linear_acceleration',
	'gyroscope',
	'accelerometer',
	'pressure',
	'rotation_vector',
	'magnetometer',
	'light',
	'proximity',
	'significant_motion'
);

CREATE TYPE public."email_addresses_enum" AS ENUM (
	'michael@steele.red',
	'steele.pedersen@gmail.com',
	'michaelp@discoverdst.com'
);

CREATE TYPE public."source_type" AS ENUM (
	'phone',
	'laptop',
	'wearable',
	'tablet',
	'desktop',
	'unknown'
);

CREATE
OR REPLACE FUNCTION uuid_generate_v7() RETURNS uuid AS $ $ BEGIN -- use random v4 uuid as starting point (which has the same variant we need)
-- then overlay timestamp
-- then set version 7 by flipping the 2 and 1 bit in the version 4 string
RETURN encode(
	set_bit(
		set_bit(
			overlay(
				uuid_send(gen_random_uuid()) placing substring(
					int8send(
						floor(
							extract(
								epoch
								FROM
									clock_timestamp()
							) * 1000
						) :: bigint
					)
					from
						3
				)
				from
					1 for 6
			),
			52,
			1
		),
		53,
		1
	),
	'hex'
) :: uuid;

END $ $ LANGUAGE plpgsql VOLATILE;

CREATE
OR REPLACE FUNCTION public.timestamp_from_uuid_v7(_uuid uuid) RETURNS timestamp without time zone LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT LEAKPROOF AS $ $
SELECT
	to_timestamp(
		(
			'x0000' || substr(_uuid :: text, 1, 8) || substr(_uuid :: text, 10, 4)
		) :: bit(64) :: bigint :: numeric / 1000
	);

$ $;

CREATE
OR REPLACE FUNCTION public.detect_location_transition() RETURNS trigger LANGUAGE plpgsql AS $ function $ DECLARE previous_location_id INT;

new_location_id INT;

old_location_count INT;

new_location_count INT;

BEGIN -- Get the previous and new classified_as values
SELECT
	classified_as INTO previous_location_id
FROM
	gps_data
WHERE
	id = OLD.id;

new_location_id := NEW.classified_as;

-- If the location has changed or was previously NULL, check the counts
IF previous_location_id IS DISTINCT
FROM
	new_location_id
	or previous_location_id is null THEN -- Count the number of detections at the old location within the last 30 rows and 30 seconds
SELECT
	COUNT(1) INTO old_location_count
FROM
	(
		SELECT
			*
		FROM
			gps_data
		WHERE
			classified_as = previous_location_id --AND created_at >= NOW() - INTERVAL '30 seconds'
		ORDER BY
			created_at DESC
		LIMIT
			30
	) AS recent_old_location;

-- Count the number of detections at the new location
--SELECT COUNT(*) INTO new_location_count FROM gps_data WHERE classified_as = new_location_id;
--AND new_location_count = 1
-- If both counts are at least 10, update the transitioned_from column
IF old_location_count >= 10 THEN
UPDATE
	gps_data
SET
	transitioned_from = previous_location_id
WHERE
	id = NEW.id;

END IF;

END IF;

RETURN NEW;

END;

$ function $;

CREATE
OR REPLACE FUNCTION public.classify_gps_data() RETURNS trigger LANGUAGE plpgsql AS $ function $ DECLARE location_id INT;

previous_location_id INT;

old_location_count INT;

BEGIN -- Find a known location that contains the GPS point or is within the radius
SELECT
	id INTO location_id
FROM
	known_locations
WHERE
	(
		gps_polygon IS NOT NULL
		AND ST_Contains(
			gps_polygon,
			ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)
		)
	)
	OR (
		gps_polygon IS NOT NULL
		AND ST_DWithin(
			gps_polygon,
			ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326),
			radius_miles * 1609.34
		)
	) -- Convert miles to meters
	OR (
		gps_polygon IS NULL
		AND ST_DWithin(
			ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326),
			ST_SetSRID(
				ST_MakePoint(center_longitude, center_latitude),
				4326
			),
			radius_miles * 1609.34
		)
	) -- Convert miles to meters
LIMIT
	1;

IF location_id IS NOT NULL THEN -- UPDATE gps_data SET classified_as = location_id WHERE id = NEW.id;
new.classified_as = location_id;

end IF;

RETURN NEW;

END;

$ function $;

CREATE
OR REPLACE FUNCTION public.handle_location_transitions() RETURNS trigger LANGUAGE plpgsql AS $ function $ DECLARE location_id INT;

previous_location_id INT;

BEGIN -- Find the location_id for the new GPS data
SELECT
	classified_as INTO location_id
FROM
	gps_data
WHERE
	id = NEW.id;

-- Find previous_location_id for the row immediately prior to this one that occurred within 30 seconds
SELECT
	classified_as INTO previous_location_id
FROM
	gps_data
WHERE
	id = NEW.id - 1
	AND created_at >= NOW() - INTERVAL '30 seconds'
LIMIT
	1;

-- If a matching location is found, update the classified_as column
IF location_id IS NOT NULL THEN -- Detect location transitions
IF previous_location_id IS NULL THEN
INSERT INTO
	location_transitions (location_id, isEntering, isLeaving)
VALUES
	(location_id, TRUE, FALSE);

END IF;

ELSE IF previous_location_id IS NOT NULL THEN
INSERT INTO
	location_transitions (location_id, isEntering, isLeaving)
VALUES
	(previous_location_id, FALSE, TRUE);

END IF;

END IF;

RETURN NEW;

END;

$ function $;

CREATE
OR REPLACE FUNCTION public.update_updated_at_column() RETURNS trigger LANGUAGE plpgsql AS $ function $ BEGIN NEW.updated_at = NOW();

RETURN NEW;

END;

$ function $;

CREATE TABLE IF NOT EXISTS emails (
	id UUID DEFAULT uuid_generate_v7(),
	email_id VARCHAR,
	subject VARCHAR,
	sender VARCHAR,
	date_received TIMESTAMPTZ NOT NULL,
	body TEXT,
	attachments BYTEA [],
	seen BOOLEAN,
	receiver VARCHAR,
	pull_id INTEGER,
	source_email_address VARCHAR,
	embedding VECTOR(512),
	created_at TIMESTAMPTZ DEFAULT NOW(),
	PRIMARY KEY (id, date_received)
);

CREATE INDEX idx_email_id ON public.emails USING btree (email_id);

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
	PRIMARY KEY (event_id, source_calendar, start_time)
);

CREATE TABLE IF NOT EXISTS contacts (
	id UUID DEFAULT uuid_generate_v7() PRIMARY KEY,
	vcard_id VARCHAR,
	full_name VARCHAR,
	email VARCHAR UNIQUE,
	phone VARCHAR,
	last_contacted TIMESTAMPTZ,
	last_seen_timestamp TIMESTAMPTZ,
	embedding VECTOR(512),
	face_images BYTEA [],
	last_seen_location GEOMETRY(POINT, 4326),
	raw_vcard TEXT,
	created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS server_stats (
	id UUID DEFAULT uuid_generate_v7(),
	timestamp TIMESTAMPTZ,
	device_id INTEGER,
	disk_usage FLOAT,
	cpu_usage FLOAT,
	ram_usage FLOAT,
	gpu_usage FLOAT,
	created_at TIMESTAMPTZ DEFAULT NOW(),
	PRIMARY KEY (id, timestamp)
);

CREATE TABLE IF NOT EXISTS documents (
	id UUID DEFAULT uuid_generate_v7(),
	name VARCHAR,
	gps_point GEOMETRY(POINT, 4326),
	document_text TEXT,
	document_bytes BYTEA,
	embedding VECTOR(512),
	created_at TIMESTAMPTZ DEFAULT NOW(),
	PRIMARY KEY (id, created_at)
);

-- public.browser_data definition
-- Drop table
-- DROP TABLE public.browser_data;
CREATE TABLE public.browser_data (
	id int4 NOT NULL,
	"document" text NULL,
	active bool NULL,
	audible bool NULL,
	auto_discardable bool NULL,
	discarded bool NULL,
	fav_icon_url text NULL,
	group_id int4 NULL,
	height int4 NULL,
	highlighted bool NULL,
	incognito bool NULL,
	"index" int4 NULL,
	last_accessed int8 NULL,
	muted_info json NULL,
	pinned bool NULL,
	selected bool NULL,
	status text NULL,
	title text NULL,
	url text NULL,
	width int4 NULL,
	window_id int4 NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	device_id int4 NULL,
	"type" public."browser_tab_type" NULL,
	useragent text NULL
);

-- public.devices definition
-- Drop table
-- DROP TABLE public.devices;
CREATE TABLE public.devices (
	id serial4 NOT NULL,
	"name" varchar(255) NOT NULL,
	description text NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT devices_pkey PRIMARY KEY (id)
);

CREATE INDEX idx_devices_updated_at ON public.devices USING btree (updated_at);

-- Table Triggers
create trigger update_devices_updated_at before
update
	on public.devices for each row execute function update_updated_at_column();

-- public.known_locations definition
-- Drop table
-- DROP TABLE public.known_locations;
CREATE TABLE public.known_locations (
	id serial4 NOT NULL,
	gps_polygon public.geometry(polygon, 4326) NULL,
	center_latitude float8 NULL,
	center_longitude float8 NULL,
	radius_miles float8 NULL,
	"name" varchar(255) NULL,
	notes text NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT known_locations_pkey PRIMARY KEY (id)
);

-- public.labeled_embeddings definition
-- Drop table
-- DROP TABLE public.labeled_embeddings;
CREATE TABLE public.labeled_embeddings (
	id serial4 NOT NULL,
	clip_embedding public.vector NULL,
	clap_embedding public.vector NULL,
	"name" varchar(255) NULL,
	notes text NULL,
	embedding_radius float8 NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT labeled_embeddings_pkey PRIMARY KEY (id)
);

-- public.spatial_ref_sys definition
-- Drop table
-- DROP TABLE public.spatial_ref_sys;
CREATE TABLE public.spatial_ref_sys (
	srid int4 NOT NULL,
	auth_name varchar(256) NULL,
	auth_srid int4 NULL,
	srtext varchar(2048) NULL,
	proj4text varchar(2048) NULL,
	CONSTRAINT spatial_ref_sys_pkey PRIMARY KEY (srid),
	CONSTRAINT spatial_ref_sys_srid_check CHECK (
		(
			(srid > 0)
			AND (srid <= 998999)
		)
	)
);

-- public.audio_data definition
-- Drop table
-- DROP TABLE public.audio_data;
CREATE TABLE public.audio_data (
	id serial4 NOT NULL,
	taken_at timestamp NOT NULL,
	"data" bytea NOT NULL,
	"text" text NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	archived bool DEFAULT false NULL,
	processed_at timestamp NULL,
	"result" json NULL,
	"source" public."source_type" NULL,
	clap public.vector NULL,
	device_id int4 NULL,
	CONSTRAINT audio_data_pkey PRIMARY KEY (id),
	CONSTRAINT audio_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

-- public.gps_data definition
-- Drop table
-- DROP TABLE public.gps_data;
CREATE TABLE public.gps_data (
	id serial4 NOT NULL,
	latitude float8 NOT NULL,
	longitude float8 NOT NULL,
	altitude float8 NOT NULL,
	"time" int8 NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	archived bool DEFAULT false NULL,
	classified_as int4 NULL,
	device_id int4 NULL,
	CONSTRAINT gps_data_pkey PRIMARY KEY (id),
	CONSTRAINT gps_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_gps_data_classified_as ON public.gps_data USING btree (classified_as);

CREATE INDEX idx_gps_data_created_at ON public.gps_data USING btree (created_at);

-- Table Triggers
create trigger classify_gps_data_trigger before
insert
	on public.gps_data for each row execute function classify_gps_data();

create trigger handle_location_transitions_trigger
after
insert
	on public.gps_data for each row execute function handle_location_transitions();

-- public.location_transitions definition
-- Drop table
-- DROP TABLE public.location_transitions;
CREATE TABLE public.location_transitions (
	id serial4 NOT NULL,
	location_id int4 NULL,
	isentering bool NOT NULL,
	isleaving bool NOT NULL,
	transitioned_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	device_id int4 NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT location_transitions_pkey PRIMARY KEY (id),
	CONSTRAINT location_transitions_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id),
	CONSTRAINT location_transitions_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.known_locations(id)
);

CREATE INDEX idx_location_transitions_location_id ON public.location_transitions USING btree (location_id);

CREATE INDEX idx_location_transitions_transitioned_at ON public.location_transitions USING btree (transitioned_at);

COMMENT ON TABLE public.location_transitions IS 'All regions must be non overlapping';

-- public.manual_photo_data definition
-- Drop table
-- DROP TABLE public.manual_photo_data;
CREATE TABLE public.manual_photo_data (
	id serial4 NOT NULL,
	photo bytea NULL,
	is_screenshot bool NULL,
	clip public.vector NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	device_id int4 NULL,
	CONSTRAINT manual_photo_data_pkey PRIMARY KEY (id),
	CONSTRAINT manual_photo_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_manual_photo_data_created_at ON public.manual_photo_data USING btree (created_at);

-- public.notification_data definition
-- Drop table
-- DROP TABLE public.notification_data;
CREATE TABLE public.notification_data (
	id serial4 NOT NULL,
	"data" text NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	archived bool DEFAULT false NULL,
	processed_at timestamp NULL,
	clip public.vector NULL,
	device_id int4 NULL,
	CONSTRAINT notification_data_pkey PRIMARY KEY (id),
	CONSTRAINT notification_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_notification_data_created_at ON public.notification_data USING btree (created_at);

-- public.screenshot_data definition
-- Drop table
-- DROP TABLE public.screenshot_data;
CREATE TABLE public.screenshot_data (
	id serial4 NOT NULL,
	"data" bytea NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	archived bool DEFAULT false NULL,
	processed_at timestamp NULL,
	bounding_boxes json NULL,
	"result" json NULL,
	"text" varchar NULL,
	clip public.vector NULL,
	device_id int4 NULL,
	CONSTRAINT screenshot_data_pkey PRIMARY KEY (id),
	CONSTRAINT screenshot_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_screenshot_data_created_at ON public.screenshot_data USING btree (created_at);

-- public.sensor_data definition
-- Drop table
-- DROP TABLE public.sensor_data;
CREATE TABLE public.sensor_data (
	id serial4 NOT NULL,
	sensor_type public."sensor_type_enum" NOT NULL,
	x float8 NULL,
	y float8 NULL,
	z float8 NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	device_id int4 NULL,
	CONSTRAINT sensor_data_pkey PRIMARY KEY (id),
	CONSTRAINT sensor_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_sensor_data_created_at ON public.sensor_data USING btree (created_at);

-- public.server_data definition
-- Drop table
-- DROP TABLE public.server_data;
CREATE TABLE public.server_data (
	id serial4 NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	device_id int4 NULL,
	"timestamp" float8 NULL,
	disk_usage json NULL,
	cpu_usage float8 NULL,
	ram_usage json NULL,
	gpu_usage json NULL,
	CONSTRAINT server_data_pkey PRIMARY KEY (id),
	CONSTRAINT server_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

-- public.sms_data definition
-- Drop table
-- DROP TABLE public.sms_data;
CREATE TABLE public.sms_data (
	id int4 NOT NULL,
	message text NULL,
	sender text NULL,
	receiver text NULL,
	"timestamp" timestamp NULL,
	device_id int4 NULL,
	CONSTRAINT sms_data_pkey PRIMARY KEY (id),
	CONSTRAINT sms_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

-- public.speech_data definition
-- Drop table
-- DROP TABLE public.speech_data;
CREATE TABLE public.speech_data (
	id serial4 NOT NULL,
	"text" text NOT NULL,
	"result" json NOT NULL,
	started_at timestamp NULL,
	ended_at timestamp NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	clip public.vector NULL,
	clap public.vector NULL,
	device_id int4 NULL,
	CONSTRAINT speech_data_pkey PRIMARY KEY (id),
	CONSTRAINT speech_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_speech_data_created_at ON public.speech_data USING btree (created_at);

-- public.wake_word_data definition
-- Drop table
-- DROP TABLE public.wake_word_data;
CREATE TABLE public.wake_word_data (
	id int4 NOT NULL,
	wake_word text NULL,
	"timestamp" timestamp NULL,
	device_id int4 NULL,
	CONSTRAINT wake_word_data_pkey PRIMARY KEY (id),
	CONSTRAINT wake_word_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

-- public.websocket_metadata definition
-- Drop table
-- DROP TABLE public.websocket_metadata;
CREATE TABLE public.websocket_metadata (
	id serial4 NOT NULL,
	connected_at timestamp NOT NULL,
	disconnected_at timestamp NULL,
	client_ip varchar(45) NULL,
	client_user_agent text NULL,
	status varchar(20) NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	device_id int4 NULL,
	CONSTRAINT websocket_metadata_pkey PRIMARY KEY (id),
	CONSTRAINT websocket_metadata_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_websocket_metadata_created_at ON public.websocket_metadata USING btree (created_at);

-- public.movement_data definition
-- Drop table
-- DROP TABLE public.movement_data;
CREATE TABLE public.movement_data (
	id serial4 NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	source_sensor_id int4 NULL,
	screen_up bool NULL,
	screen_down bool NULL,
	significant_movement bool NULL,
	activity_type public."activity_enum" NULL,
	activity_confidence float8 NULL,
	CONSTRAINT movement_data_pkey PRIMARY KEY (id),
	CONSTRAINT movement_data_source_sensor_id_fkey FOREIGN KEY (source_sensor_id) REFERENCES public.sensor_data(id)
);


-- public.gotify_message_log definition
-- Drop table
-- DROP TABLE public.gotify_message_log;
CREATE TABLE public.gotify_message_log (
	id serial4 NOT NULL,
	message text NOT NULL,
	sent_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	parameters jsonb NOT NULL,
	device_id int4 NULL,
	CONSTRAINT gotify_message_log_pkey PRIMARY KEY (id),
	CONSTRAINT gotify_message_log_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

-- Drop table if exists before creating tweets table

-- Table for storing tweets
CREATE TABLE public.tweets (
    id UUID DEFAULT uuid_generate_v7(),
    tweet_text text NOT NULL,
    tweet_url text NOT NULL,
    profile_link text NOT NULL,
    timestamp timestamp NOT NULL,
    text_embedding vector(512) NOT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT tweets_pkey PRIMARY KEY (id)
);

-- Drop table if exists before creating tweet_images table

-- Table for storing tweet images
CREATE TABLE public.tweet_images (
    id UUID DEFAULT uuid_generate_v7(),
	url text NOT NULL,
    tweet_id UUID NOT NULL,
    image_data bytea NOT NULL,
    image_embedding vector(512) NOT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT tweet_images_pkey PRIMARY KEY (id),
);

CREATE INDEX idx_tweets_created_at ON public.tweets USING btree (created_at);
CREATE INDEX idx_tweet_images_created_at ON public.tweet_images USING btree (created_at);

ALTER TABLE public.tweet_images
ADD CONSTRAINT tweet_images_tweet_id_fkey FOREIGN KEY (tweet_id) REFERENCES public.tweets(id);


ALTER TABLE public.tweets
ADD COLUMN tweet_json jsonb;


-- -- Create enum type for tool_type
-- CREATE TYPE public.tool_type_enum AS ENUM (
-- 	'gotify',
-- 	'llm',
-- 	'ocr',
-- 	'browser',
-- 	'calculator',
-- 	'camera',
-- 	'keyboard',
-- 	'mouse',
-- 	'screen_reader',
-- 	'voice_input',
-- 	'other'
-- );

-- -- Create table for tool_use_analytics
-- CREATE TABLE public.tool_use_analytics (
-- 	id serial4 NOT NULL,
-- 	tool_name text NOT NULL,
-- 	tool_type public.tool_type_enum NOT NULL,
-- 	tokens_in int4 NOT NULL,
-- 	tokens_out int4 NOT NULL,
-- 	parameters jsonb NOT NULL,
-- 	used_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
-- 	device_id int4 NULL,
-- 	CONSTRAINT tool_use_analytics_pkey PRIMARY KEY (id),
-- 	CONSTRAINT tool_use_analytics_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
-- );


-- Table for storing GitHub stars
CREATE TABLE public.github_stars (
    repo_id INT NOT NULL,
    repo_name VARCHAR NOT NULL,
    repo_url TEXT NOT NULL,
    owner_login VARCHAR NOT NULL,
    owner_url TEXT NOT NULL,
    description TEXT,
    description_embedding VECTOR(512),
    readme_data TEXT,
    readme_embedding VECTOR(512),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT github_stars_pkey PRIMARY KEY (repo_id)
);

CREATE INDEX idx_github_stars_created_at ON public.github_stars USING btree (created_at);



SELECT
	create_hypertable(
		'emails',
		'date_received',
		chunk_time_interval = > INTERVAL '7 day',
		if_not_exists = > TRUE
	);

SELECT
	create_hypertable(
		'calendar_events',
		'start_time',
		chunk_time_interval = > INTERVAL '14 day',
		if_not_exists = > TRUE
	);

SELECT
	create_hypertable(
		'server_stats',
		'timestamp',
		chunk_time_interval = > INTERVAL '14 day',
		if_not_exists = > TRUE
	);

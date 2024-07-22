
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
OR REPLACE FUNCTION uuid_generate_v7() RETURNS uuid AS $ $ BEGIN 

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
BEGIN 
SELECT
	classified_as INTO previous_location_id
FROM
	gps_data
WHERE
	id = OLD.id;
new_location_id := NEW.classified_as;

IF previous_location_id IS DISTINCT
FROM
	new_location_id
	or previous_location_id is null THEN 
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

--SELECT COUNT(*) INTO new_location_count FROM gps_data WHERE classified_as = new_location_id;
--AND new_location_count = 1
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
BEGIN 
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
	) 
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
	) 
LIMIT
	1;
IF location_id IS NOT NULL THEN 
new.classified_as = location_id;
end IF;
RETURN NEW;
END;
$ function $;



CREATE OR REPLACE FUNCTION public.handle_location_transitions()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$

DECLARE

location_id INT;

previous_location_id INT;

BEGIN

-- Find the location_id for the new GPS data

SELECT classified_as INTO location_id

FROM gps_data

WHERE id = NEW.id;



-- Find previous_location_id for the row immediately prior to this one that occurred within 30 seconds

SELECT classified_as INTO previous_location_id

FROM gps_data

WHERE id = NEW.id - 1

AND created_at >= NOW() - INTERVAL '30 seconds'

LIMIT 1;



-- If a matching location is found, update the classified_as column

IF location_id IS NOT NULL THEN

-- Detect location transitions

IF previous_location_id IS NULL THEN

INSERT INTO location_transitions (location_id, isEntering, isLeaving, device_id)

VALUES (location_id, TRUE, false, new.device_id);

END IF;

ELSE

IF previous_location_id IS NOT NULL THEN

INSERT INTO location_transitions (location_id, isEntering, isLeaving, device_id)

VALUES (previous_location_id, FALSE, true, new.device_id);

END IF;

END IF;



RETURN NEW;

END;

$function$
;



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


CREATE TABLE public.device_status_log (
	id serial4 NOT NULL,
	device_id int4 NOT NULL,
	timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
	last_movement TIMESTAMPTZ,
	screen_up BOOLEAN,
	speed FLOAT,
	last_known_address JSONB,
	online BOOLEAN,
	CONSTRAINT device_status_log_pkey PRIMARY KEY (id),
	CONSTRAINT fk_device FOREIGN KEY (device_id) REFERENCES public.devices(id)
);

CREATE INDEX idx_device_status_log_device_id_timestamp ON public.device_status_log (device_id, timestamp);
ALTER TABLE public.device_status_log
ADD COLUMN location GEOGRAPHY(POINT, 4326);

COMMENT ON COLUMN public.device_status_log.location IS 'Geographic point representing the device''s location at the time of the log entry';

CREATE INDEX idx_device_status_log_location ON public.device_status_log USING GIST (location);
ALTER TABLE public.device_status_log
DROP COLUMN last_known_address;

COMMENT ON COLUMN public.device_status_log.last_known_address IS NULL;

COMMENT ON TABLE public.device_status_log IS 'Timeseries log of device status changes';
COMMENT ON COLUMN public.device_status_log.last_movement IS 'Timestamp of the last detected movement of the device';
COMMENT ON COLUMN public.device_status_log.screen_up IS 'Indicates whether the device screen is facing up (true) or down (false)';
COMMENT ON COLUMN public.device_status_log.speed IS 'Current speed of the device in mph';
COMMENT ON COLUMN public.device_status_log.last_known_address IS 'JSON object containing the last known address details of the device';
COMMENT ON COLUMN public.device_status_log.online IS 'Indicates whether the device is currently online (true) or offline (false)';

CREATE TABLE public.devices (
	id serial4 NOT NULL,
	"name" varchar(255) NOT NULL,
	description text NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT devices_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_devices_updated_at ON public.devices USING btree (updated_at);
ALTER TABLE public.devices
ADD COLUMN location GEOGRAPHY(POINT, 4326);

COMMENT ON COLUMN public.devices.location IS 'Geographic point representing the device''s current location';

CREATE INDEX idx_devices_location ON public.devices USING GIST (location);

ALTER TABLE public.devices
ADD COLUMN last_movement TIMESTAMPTZ,
ADD COLUMN screen_up BOOLEAN;

COMMENT ON COLUMN public.devices.last_movement IS 'Timestamp of the last detected movement of the device';
COMMENT ON COLUMN public.devices.screen_up IS 'Indicates whether the device screen is facing up (true) or down (false)';

ALTER TABLE public.devices
ADD COLUMN speed FLOAT;

COMMENT ON COLUMN public.devices.speed IS 'Current speed of the device in mph';

ALTER TABLE public.devices
ADD COLUMN last_known_address JSONB;

COMMENT ON COLUMN public.devices.last_known_address IS 'JSON object containing the last known address details of the device';

ALTER TABLE public.devices
ADD COLUMN online BOOLEAN DEFAULT false;

COMMENT ON COLUMN public.devices.online IS 'Indicates whether the device is currently online (true) or offline (false)';


create trigger update_devices_updated_at before
update
	on public.devices for each row execute function update_updated_at_column();


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

create trigger classify_gps_data_trigger before
insert
	on public.gps_data for each row execute function classify_gps_data();
create trigger handle_location_transitions_trigger
after
insert
	on public.gps_data for each row execute function handle_location_transitions();


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

-- make alter table expression to add caption, TEXT (MORE_DETAILED_CAPTION) ocr_raw_text (OCR), ocr_regions JSONB (OCR_WITH_REGION), object detection JSONB (DENSE_REGION_CAPTION), and caption_phrase_grounding JSONB (CAPTION_TO_PHRASE_GROUNDING)
ALTER TABLE public.manual_photo_data
ADD COLUMN caption TEXT,
ADD COLUMN more_detailed_caption TEXT,
ADD COLUMN ocr_raw_text TEXT,
ADD COLUMN ocr_regions JSONB,
ADD COLUMN object_detection JSONB,
ADD COLUMN caption_phrase_grounding JSONB;

ALTER TABLE public.manual_photo_data
DROP COLUMN clip,
ADD COLUMN embedding vector(512);


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


CREATE TABLE public.wake_word_data (
	id int4 NOT NULL,
	wake_word text NULL,
	"timestamp" timestamp NULL,
	device_id int4 NULL,
	CONSTRAINT wake_word_data_pkey PRIMARY KEY (id),
	CONSTRAINT wake_word_data_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);


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


CREATE TABLE public.gotify_message_log (
	id serial4 NOT NULL,
	message text NOT NULL,
	sent_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	parameters jsonb NOT NULL,
	device_id int4 NULL,
	CONSTRAINT gotify_message_log_pkey PRIMARY KEY (id),
	CONSTRAINT gotify_message_log_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id)
);


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

ALTER TABLE public.github_stars
ADD COLUMN repo_json JSONB;


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

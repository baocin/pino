# pino - your friendly background helper agent
![image](https://github.com/baocin/pino/assets/5463986/686825fe-1422-4693-a1f1-8ca19c9e4be1)

An early prototype for a behind-the-scenes autonomous agent that helps the user by suggesting real-time information when appropriate.

**Disclaimer: This project is currently a work in progress. Many features are experimental and may not be fully functional.**

## Project Goal

To run pino on a moderately powerful modern GPU:
- Target: NVIDIA GeForce RTX 2070 (8GB) or equivalent
- ~15 TFLOPS at FP16
- ~7 TFLOPS at FP32

## Folder Structure (in order of install/setup)
- `db/`
  - timescaledb
  - start: `docker-compose up -d`
  - data volume: `/var/lib/docker/volumes/db_timescaledb-data/_data`

- `maps/`
  - Contains the docker-compose for the nominatim server
  - start: `docker-compose up -d`
  - data volume: `/var/lib/docker/volumes/maps_nominatim-data/_data`

- `android-app/`
  - Contains the Android application for sending off gps/audio/sensors/screenshots
  - 

- `realtime-ingest/`
  - For real-time sensor data ingestion from Android
  - 

- `scheduled-injest/`
  - Scripts for periodic data ingestion
    - `twitter/` Twitter/X likes ingestion
    - 

## Features

- **Background Operation**: Pino runs unobtrusively in the background.
- **Real-time Suggestions**: Provides timely and relevant information based on current context.
- **Autonomous Decision Making**: Intelligently decides when to offer assistance.
- **User-Friendly Interface**: Yeah, no - there is no actual ui besides the terrible android app

## How It Works

1. Monitor user activities (with permission) from as many sources as possible
2. Analyze context and user needs
3. Generate relevant suggestions
4. Act on the information
   1. Present information at appropriate times to the user (Think AR Glasses like the [Frame](https://brilliant.xyz/products/frame))
   2. Run tools to benefit the user

## Getting Started

(Instructions for installation and setup to be added)

- Update the .env files:
  - `android-app/app/src/main/java/red/steele/injest/.env`
    - Needs Websocket Server IP
  - 

## Contribution

Contributions are welcome. Please refer to the issues page.

## License

This project is licensed under the MIT License. 

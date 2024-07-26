from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Any
from pydantic import BaseModel
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
import json
import shutil
import os
import sys
import base64
from collections import deque
from processors.process_audio import AudioProcessor
from processors.process_screenshot import ScreenshotProcessor
from processors.process_photo import PhotoProcessor
# from injest_mail import EmailInjest
# from injest_server_stats import SystemStatsRecorder

from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from libraries.db.db import DB

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

db = DB(
    host=os.getenv("POSTGRES_HOST"),
    port=os.getenv("POSTGRES_PORT"),
    database=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD")
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmbedRequest(BaseModel):
    texts: List[str] = None
    image_paths: List[str] = None

@dataclass(order=True)
class PrioritizedItem:
    priority: int
    item: Any=field(compare=False)

class GpsData(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    time: int
    
class SensorData(BaseModel):
    time: int
    sensorType: str
    x: float
    y: float | None = None
    z: float | None = None
    
class KeyEventData(BaseModel):
    keyCode: int
    action: int

class MotionEventData(BaseModel):
    x: float
    y: float
    action: int

class NotificationData(BaseModel):
    data: str

audio_processor = AudioProcessor(db)
screenshot_processor = ScreenshotProcessor(db)
photo_processor = PhotoProcessor(db)

packet_tally = {
        "audio": 0,
        "gps": 0,
        "sensor": 0,
        "manual_photo": 0,
        "screenshot": 0,
        "unknown": 0
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global packet_tally
    client_ip = websocket.client.host
    client_user_agent = websocket.headers.get('user-agent', 'unknown')
    connection_time = datetime.now()
    
    db.insert_websocket_metadata(connection_time, None, client_ip, client_user_agent, "connected")
    
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # print(data[:100])
            messages = json.loads(data)
                
            if not isinstance(messages, list):
                messages = [messages]
            
            for message in messages:
                if "type" not in message:
                    raise HTTPException(status_code=422, detail="Unprocessable Entity: No type specified - type not in message")

                message_type = message["type"]
                device_id = message["device_id"]
                message_id = message["message_id"]
                                
                packet_tally[message_type] = packet_tally.get(message_type, 0) + 1
            
                if message_type == "audio":
                    await audio_processor.handle_audio_message(message, websocket, device_id)
                elif message_type == "gps":
                    gps_model = GpsData(**message.get("data"))
                    db.insert_gps_data(gps_model.latitude, gps_model.longitude, gps_model.altitude, gps_model.time, device_id)
                elif message_type == "sensor":
                    sensor_data = SensorData(**message.get("data"))
                    db.insert_sensor_data(sensor_data.sensorType, sensor_data.x, sensor_data.y, sensor_data.z, device_id)
                    
                elif message_type == "manual_photo":
                    await photo_processor.handle_photo_message(message.get("data"), websocket, device_id)
                elif message_type == "screenshot":
                    await screenshot_processor.handle_screenshot_message(message, websocket, device_id)
                else:
                    packet_tally["unknown"] += 1
                    raise HTTPException(status_code=422, detail=f"Unprocessable Entity: Unknown message type {message_type}")
            
            response = {
                "message_id": message_id,
                "status": 200,
                "message_type": message_type
            }
            # logger.info(f"Response sent: {response}")
            await websocket.send_json(response)
            
            # os.system('cls' if os.name == 'nt' else 'clear')
            # print("Packet Tally:")
            # for packet_type, count in packet_tally.items():
            #     print(f"{packet_type}: {count}")

    except WebSocketDisconnect:
        logger.info("Client disconnected")
        disconnection_time = datetime.now()
        db.insert_websocket_metadata(connection_time, disconnection_time, client_ip, client_user_agent, "disconnected")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)  # Add exc_info=True to log the traceback
        await websocket.send_json({"status": "error", "detail": str(e)})
        disconnection_time = datetime.now()
        db.insert_websocket_metadata(connection_time, disconnection_time, client_ip, client_user_agent, "error")

@app.get("/heartbeat")
async def heartbeat():
    # return JSONResponse(status_code=200, content={"status": "online"})
    try:
        # Check database connection
        db.execute_query("SELECT 1")

        # Check disk space
        _, _, free = shutil.disk_usage("/")
        free_gb = free // (2**30)

        if free_gb < 1:  # Less than 1 GB free
            return JSONResponse(status_code=500, content={"status": f"Low disk space: {free_gb} GB free"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": f"Error: {str(e)}"})
    return JSONResponse(status_code=200, content={"status": "online"})
@app.get("/get-detection-audio/{known_class_detection_id}")
async def get_detection_audio(known_class_detection_id: str):
    try:
        # Query the database to get the source_data for the given id
        query = """
        SELECT source_data
        FROM known_class_detections
        WHERE id = %s AND source_data_type = 'audio'
        """
        result = db.sync_query(query, (known_class_detection_id,))

        if not result:
            raise HTTPException(status_code=404, detail="Detection not found or not audio type")

        audio_data = result[0][0]

        # Add WAVE RIFF header
        sample_rate = 48000  # Assuming 48kHz sample rate, adjust if different
        channels = 1  # Assuming mono, adjust if stereo
        bits_per_sample = 16  # Assuming 16-bit audio, adjust if different
        import struct
        header = struct.pack('<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + len(audio_data),
            b'WAVE',
            b'fmt ',
            16,
            1,
            channels,
            sample_rate,
            sample_rate * channels * bits_per_sample // 8,
            channels * bits_per_sample // 8,
            bits_per_sample,
            b'data',
            len(audio_data)
        )

        # Combine header and audio data
        wav_data = header + audio_data

        # Convert the WAV data to base64
        audio_base64 = base64.b64encode(wav_data).decode('utf-8')

        return JSONResponse(content={"audio_base64": audio_base64})

    except Exception as e:
        logger.error(f"Error retrieving audio data: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/verify-detection/{known_class_detection_id}")
async def verify_detection(request: Request, known_class_detection_id: str, name: str = None, audio_url: str = None):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verify Detection</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <script>
            async function updateGroundTruth(value) {{
                const response = await fetch('/update-ground-truth/{known_class_detection_id}/' + value, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        known_class_detection_id: '{known_class_detection_id}',
                        ground_truth: value
                    }})
                }});
                if (response.ok) {{
                    alert('Ground truth updated successfully');
                }} else {{
                    alert('Failed to update ground truth');
                }}
            }}

            async function fetchAndPlayAudio() {{
                const response = await fetch('{audio_url}');
                const data = await response.json();
                const audioPlayer = document.getElementById('audioPlayer');
                audioPlayer.src = 'data:audio/wav;base64,' + data.audio_base64;
                audioPlayer.style.display = 'block';
            }}
        </script>
    </head>
    <body class="bg-gray-100 flex items-center justify-center h-screen">
        <div class="bg-white p-8 rounded shadow-md">
            <h2 class="text-2xl font-bold mb-4">Verify Detection</h2>
            {('<p class="mb-4">Name: ' + name + '</p>') if name else ''}
            {('<div class="mb-4"><button onclick="fetchAndPlayAudio()" class="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded">Load Audio</button></div>') if audio_url else ''}
            <audio id="audioPlayer" controls style="display: none;" class="mb-4"></audio>
            <div class="flex space-x-4">
                <button onclick="updateGroundTruth(true)" class="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded">
                    True
                </button>
                <button onclick="updateGroundTruth(false)" class="bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-4 rounded">
                    False
                </button>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/update-ground-truth/{known_class_detection_id}/{ground_truth}")
async def update_ground_truth(known_class_detection_id: str, ground_truth: bool):
    try:
        query = """
        UPDATE known_class_detections
        SET ground_truth = %s
        WHERE id = %s
        """
        db.execute_query(query, (ground_truth, known_class_detection_id))
        return JSONResponse(status_code=200, content={"message": "Ground truth updated successfully"})
    except Exception as e:
        logger.error(f"Error updating ground truth: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating ground truth")

@app.get("/context")
async def get_current_context(request: Request, json_only: bool = False):
    try:
        query = """
        SELECT 
            d.name AS device_name,
            d.speed,
            d.screen_up,
            d.last_movement,
            d.online,
            kl.name AS last_known_location,
            ST_AsText(d.location) AS current_location,
            ST_Distance(d.location::geography, kl.gps_polygon::geography) AS distance_from_last_known_location,
            CASE 
                WHEN d.speed IS NULL THEN 'unknown'
                WHEN d.speed <= 0 THEN 'stationary'
                WHEN d.speed <= 3 THEN 'walking'
                WHEN d.speed <= 10 THEN 'running'
                WHEN d.speed <= 1000 THEN 'vehicle'
                WHEN d.speed > 1000 THEN 'aircraft'
                ELSE 'unknown'
            END AS movement_type,
            EXTRACT(EPOCH FROM (now() - d.last_movement)) / 60 AS minutes_since_last_movement,
            d.last_known_address::json->>'street' AS street,
            d.last_known_address::json->>'city' AS city,
            d.last_known_address::json->>'country' AS country,
            (SELECT COUNT(*) FROM location_transitions lt WHERE lt.device_id = d.id AND lt.created_at > now() - interval '24 hours') AS location_changes_last_24h,
            (SELECT STRING_AGG(DISTINCT kl.name, ', ') 
             FROM location_transitions lt 
             JOIN known_locations kl ON lt.location_id = kl.id
             WHERE lt.device_id = d.id AND lt.created_at > now() - interval '24 hours') AS visited_known_locations_last_24h,
            (SELECT COUNT(*) FROM emails e WHERE e.date_received > now() - interval '24 hours') AS emails_received_last_24h,
            (SELECT COUNT(*) FROM calendar_events ce WHERE ce.start_time > now() AND ce.start_time < now() + interval '24 hours') AS upcoming_events_next_24h,
            (SELECT STRING_AGG(DISTINCT 
                ce.summary || ' (' || 
                CASE 
                    WHEN ce.start_time - now() < interval '1 hour' 
                    THEN EXTRACT(MINUTE FROM (ce.start_time - now())) || ' minutes'
                    ELSE EXTRACT(HOUR FROM (ce.start_time - now())) || ' hours'
                END || ')', ', ') 
             FROM calendar_events ce 
             WHERE ce.start_time > now() 
               AND ce.start_time < now() + interval '24 hours'
               AND ce.summary NOT ILIKE '%Forecast%'
               AND ce.summary NOT ILIKE '%work%') AS upcoming_event_titles,
            (SELECT MAX(kcd.created_at)
             FROM known_class_detections kcd
             JOIN known_classes kc ON kcd.known_class_id = kc.id
             WHERE kc.name = 'electric_toothbrush') AS last_brushed_teeth,
            CASE 
                WHEN (SELECT MAX(kcd.created_at)
                      FROM known_class_detections kcd
                      JOIN known_classes kc ON kcd.known_class_id = kc.id
                      WHERE kc.name = 'electric_toothbrush') > now() - interval '24 hours'
                THEN true
                ELSE false
            END AS brushed_teeth_last_24h,
            (SELECT ce.summary
             FROM calendar_events ce
             WHERE ce.related_known_location_id = d.last_known_location_id
             ORDER BY ce.start_time
             LIMIT 1) AS relevant_calendar_event_based_on_known_location,
            (SELECT STRING_AGG(ce.summary, ', ')
             FROM calendar_events ce
             WHERE ce.start_time BETWEEN now() - interval '3 hours' AND now() + interval '3 hours'
             LIMIT 5) AS relevant_calendar_event_based_on_time
        FROM
            devices d
        LEFT JOIN known_locations kl ON kl.id = d.last_known_location_id
        WHERE d.id = 1
        """
        result = db.sync_query(query)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail="No data found")
        
        context = {
            'device_name': result[0][0],
            'online': result[0][4],
            'speed': float(result[0][1]) if result[0][1] is not None else None,
            'screen_up': result[0][2],
            'last_movement': result[0][3].isoformat() if result[0][3] else None,
            'movement_type': result[0][8],
            'minutes_since_last_movement': float(result[0][9]) if result[0][9] is not None else None,
            'last_known_location': result[0][5],
            'current_location': result[0][6],
            'distance_from_last_known_location': f"{round(float(result[0][7]))} meters" if result[0][7] else None,
            'street': result[0][10],
            'city': result[0][11],
            'country': result[0][12],
            'location_changes_last_24h': int(result[0][13]) if result[0][13] is not None else 0,
            'visited_known_locations_last_24h': result[0][14],
            'emails_received_last_24h': int(result[0][15]) if result[0][15] is not None else 0,
            'upcoming_events_next_24h': int(result[0][16]) if result[0][16] is not None else 0,
            'upcoming_event_titles': result[0][17],
            'last_brushed_teeth': result[0][18].isoformat() if result[0][18] else None,
            'brushed_teeth_last_24h': result[0][19],
            'relevant_calendar_event_based_on_known_location': result[0][20],
            'last_brushed_teeth_relative': f"{int((datetime.now(timezone.utc) - result[0][18]).total_seconds() / 3600)} hours ago" if result[0][18] else None,
            'relevant_calendar_event_based_on_time': result[0][21]
        }

        if json_only:
            return JSONResponse(content=context)
        
        return templates.TemplateResponse("current_context.html", {"request": request, **context})
    
    except Exception as e:
        logger.error(f"Error fetching current context: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching current context: {str(e)}")
    
@app.get("/latest-updates")
async def get_latest_updates():
    try:
        query = """
        SELECT * FROM latest_updates
        ORDER BY cdt_time DESC;
        """
        result = db.sync_query(query)
        print(result)
        try:
            def default_serializer(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Type {obj.__class__.__name__} not serializable")

            json_result = json.dumps(result, default=default_serializer)
        except (TypeError, ValueError) as e:
            logger.error(f"Error converting result to JSON: {str(e)}", exc_info=True)
            json_result = None
        if json_result:
            html_content = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Latest Updates</title>
                <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mx-auto py-8">
                    <h1 class="text-2xl font-bold mb-4">Latest Updates</h1>
                    <table class="min-w-full bg-white">
                        <thead>
                            <tr>
                                <th class="py-2 px-4 border-b border-gray-200">Update Type</th>
                                <th class="py-2 px-4 border-b border-gray-200">Server Time</th>
                                <th class="py-2 px-4 border-b border-gray-200">Local Time</th>
                                <th class="py-2 px-4 border-b border-gray-200">Relative Time</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            data = json.loads(json_result)
            for row in data:
                html_content += f"""
                            <tr>
                                <td class="py-2 px-4 border-b border-gray-200">{row[0]}</td>
                                <td class="py-2 px-4 border-b border-gray-200">{row[1]}</td>
                                <td class="py-2 px-4 border-b border-gray-200">{row[2]}</td>
                                <td class="py-2 px-4 border-b border-gray-200">{row[3]}</td>
                            </tr>
                """
            html_content += """
                        </tbody>
                    </table>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=200)
        else:
            raise HTTPException(status_code=500, detail="Error converting result to JSON")
    except Exception as e:
        logger.error(f"Error fetching latest updates: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/submitBrowserData")
async def submit_browser_data(request: Request):
    try:
        data = await request.json()
        db.insert_browser_data(data)
        logger.info(f"Received browser data: {data}")
        return {"status": "success", "message": "Data logged successfully"}
    except Exception as e:
        logger.error(f"Error processing browser data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/map")
@app.get("/gps")
async def gps_map(start_date: str = None, end_date: str = None, days: int = 1):
    try:
        # Determine the time range for GPS data
        end_time = datetime.utcnow()
        if start_date and end_date:
            start_time = datetime.fromisoformat(start_date)
            end_time = datetime.fromisoformat(end_date)
        else:
            start_time = end_time - timedelta(days=days)
        
        query = f"SELECT * FROM gps_data WHERE created_at >= '{start_time}' AND created_at <= '{end_time}'"
        gps_data = db.sync_query(query)

        if not gps_data:
            raise HTTPException(status_code=404, detail="No GPS data found for the specified period")

        # Generate GeoJSON LineString from GPS data
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[row[2], row[1]] for row in gps_data]  # [longitude, latitude]
                    },
                    "properties": {}
                }
            ]
        }

        # Prepare the HTML content
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>GPS Map</title>
            <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
            <style>
                #map { height: calc(100vh - 50px); }
                #slider { width: 100%; }
            </style>
            <script src="https://cdn.jsdelivr.net/npm/leaflet@1.7.1/dist/leaflet.js"></script>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.7.1/dist/leaflet.css" />
        </head>
        <body>
            <div id="map"></div>
            <div class="w-full p-4 bg-gray-200">
                <input id="slider" type="range" min="0" max="100" value="100" class="w-full">
            </div>
            <script>
                const geojson = """ + json.dumps(geojson, default=str) + """;
                const map = L.map('map').setView([geojson.features[0].geometry.coordinates[0][1], geojson.features[0].geometry.coordinates[0][0]], 13);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                }).addTo(map);

                let geoJsonLayer = L.geoJSON(geojson).addTo(map);

                document.getElementById('slider').addEventListener('input', function(e) {
                    const value = e.target.value;
                    const endIndex = Math.floor((value / 100) * geojson.features[0].geometry.coordinates.length);
                    const slicedGeojson = {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {
                                    "type": "LineString",
                                    "coordinates": geojson.features[0].geometry.coordinates.slice(0, endIndex + 1)
                                },
                                "properties": {}
                            }
                        ]
                    };
                    map.removeLayer(geoJsonLayer);
                    geoJsonLayer = L.geoJSON(slicedGeojson).addTo(map);
                });
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        logger.error(f"Error generating GPS map: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("REALTIME_SERVER_PORT", "8000"))
    host = os.getenv("REALTIME_SERVER_URL", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
    #443, ssl_keyfile="path/to/your/keyfile.pem", ssl_certfile="path/to/your/certfile.pem")
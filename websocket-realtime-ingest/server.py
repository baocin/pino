from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi import HTTPException
from typing import List
import logging
from pydantic import BaseModel
import json
import shutil
from fastapi import Request
import wave
import struct
from datetime import datetime
import base64
from collections import deque
import heapq
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass, field
from typing import Any
from process_heap import QueueProcessor
import hashlib
from postgres import PostgresInterface
from process_audio import AudioProcessor
from process_screenshot import ScreenshotProcessor
from process_photo import PhotoProcessor
import zstd
from injest_mail import EmailInjest
from injest_server_stats import SystemStatsRecorder
from dotenv import load_dotenv
from postgres import PostgresInterface
import os
from datetime import datetime, timedelta

load_dotenv()  # Load environment variables from .env file

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = PostgresInterface(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432))
)
db.connect()

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

email_injest = EmailInjest(db)

server_stats_injest = SystemStatsRecorder(db)
# email_injest.start_sync()
# recorder.start()
# time.sleep(10)  # Record stats for 10 seconds
# recorder.stop()
# print(recorder.stats)


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
            print(data[:100])
            messages = json.loads(data)
                
            if not isinstance(messages, list):
                messages = [messages]
            
            for message in messages:
                if "type" not in message:
                    raise HTTPException(status_code=422, detail="Unprocessable Entity: No type specified - type not in message")

                message_type = message["type"]
                device_id = message["device_id"]
                message_id = message["message_id"]
                
                # print(message_type, device_id, message_id)
                
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
            logger.info(f"Response sent: {response}")
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

# @app.post("/embed")
# async def embed(request: EmbedRequest):
#     if request.texts:
#         try:
#             text_embeddings = embedder.embed_text(request.texts)
#             return {"text_embeddings": text_embeddings.tolist()}
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Error embedding texts: {str(e)}")
#     elif request.image_paths:
#         try:
#             # Download images to temporary files
#             temp_image_paths = []
#             for path in request.image_paths:
#                 response = requests.get(path, stream=True)
#                 temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
#                 for chunk in response.iter_content(chunk_size=8192):
#                     temp_file.write(chunk)
#                 temp_file.close()
#                 temp_image_paths.append(temp_file.name)
            
#             image_embeddings = embedder.embed_images(temp_image_paths)
            
#             # Clean up temporary files
#             for temp_file in temp_image_paths:
#                 os.remove(temp_file)
                
#             return {"embeddings": image_embeddings.tolist()}
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Error embedding images: {str(e)}")
#     else:
#         raise HTTPException(status_code=400, detail="No texts or image paths provided for embedding")

@app.get("/heartbeat")
async def heartbeat():
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


@app.get("/gps_map")
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
    uvicorn.run(app, host="0.0.0.0", port=80)
    #443, ssl_keyfile="path/to/your/keyfile.pem", ssl_certfile="path/to/your/certfile.pem")
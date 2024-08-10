from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, File, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Any
from pydantic import BaseModel
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
import json
import shutil
import threading
import os
import sys
import base64
from collections import deque
from processors.process_audio import AudioProcessor
from processors.process_image import ImageProcessor
from libraries.embed.embed import EmbeddingService
import tempfile
# from injest_mail import EmailInjest
# from injest_server_stats import SystemStatsRecorder

from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from libraries.db.db import DB
from realtime.context import get_current_context_logic  # Import the function

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
image_processor = ImageProcessor(db)
embedding_service = EmbeddingService()

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

                if message_type in ["manual_photo", "screenshot", "image"]:
                    print(f"packet_tally: {packet_tally}")
            
                if message_type == "audio":
                    await audio_processor.handle_audio_message(message, websocket, device_id)
                elif message_type == "gps":
                    gps_model = GpsData(**message.get("data"))
                    db.insert_gps_data(gps_model.latitude, gps_model.longitude, gps_model.altitude, gps_model.time, device_id)
                elif message_type == "sensor":
                    sensor_data = SensorData(**message.get("data"))
                    db.insert_sensor_data(sensor_data.sensorType, sensor_data.x, sensor_data.y, sensor_data.z, device_id)
                    
                # elif message_type == "manual_photo":
                #     print(f"message: {message}")
                #     await photo_processor.handle_photo_message(message.get("data"), websocket, device_id)
                # elif message_type == "screenshot":
                #     print(f"message: {message}")
                #     await image_processor.handle_image_message(message, websocket, device_id)
                elif message_type == "image":
                    await image_processor.handle_image_message(message.get("data"), websocket, device_id)
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

@app.get("/context")
async def get_current_context(request: Request, json_only: bool = False, hours_ago: int = 24):
    return await get_current_context_logic(request, json_only, hours_ago)

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

        # Convert the WAV data to base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        return JSONResponse(content={"audio_base64": audio_base64})

    except Exception as e:
        logger.error(f"Error retrieving audio data: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
@app.post("/embed")
async def embed_file(file: UploadFile = File(...)):
    # Create a temporary file to store the uploaded content
    try:
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as temp_file:
            contents = await file.read()
            temp_file.write(contents)
            temp_file_path = temp_file.name

        # Determine if it's an image, audio, or text file
        if file.content_type.startswith('image/'):
            embedding = embedding_service.embed_image(temp_file_path)
        elif file.content_type.startswith('audio/'):
            embedding = embedding_service.embed_audio(temp_file_path)
        else:
            # Assume it's a text file
            try:
                with open(temp_file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except UnicodeDecodeError:
                # If UTF-8 decoding fails, try with latin-1 encoding
                with open(temp_file_path, 'r', encoding='latin-1') as f:
                    text = f.read()
            embedding = embedding_service.embed_text([text])

        return {"embedding": embedding[0]}  # Return the first (and only) embedding
    except Exception as e:
        logger.error(f"Error in embed_file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    finally:
        # Clean up the temporary file
        try:
            os.unlink(temp_file_path)
        except Exception as e:
            logger.error(f"Error deleting temporary file: {str(e)}")

@app.get("/embed-ui")
async def embed_ui():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>File Embedding</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <script>
            function handleDrop(event) {
                event.preventDefault();
                const file = event.dataTransfer.files[0];
                uploadFile(file);
            }

            function handleDragOver(event) {
                event.preventDefault();
            }

            function uploadFile(file) {
                const formData = new FormData();
                formData.append('file', file);

                fetch('/embed', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    document.getElementById('result').textContent = JSON.stringify(data, null, 2);
                })
                .catch(error => {
                    console.error('Error:', error);
                });
            }
        </script>
    </head>
    <body class="bg-gray-100 flex items-center justify-center h-screen">
        <div class="bg-white p-8 rounded shadow-md w-full max-w-md">
            <h2 class="text-2xl font-bold mb-4">File Embedding</h2>
            <div 
                id="dropZone" 
                class="border-2 border-dashed border-gray-300 rounded p-4 text-center cursor-pointer"
                ondrop="handleDrop(event)" 
                ondragover="handleDragOver(event)"
            >
                Drag and drop a file here
            </div>
            <pre id="result" class="mt-4 bg-gray-100 p-2 rounded"></pre>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


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
                    window.close();
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
                audioPlayer.play();
            }}
        </script>
    </head>
    <body class="bg-gray-100 flex flex-col items-center pt-1/3 h-screen">
        <div class="bg-white p-8 rounded-lg shadow-lg max-w-md w-full">
            <h2 class="text-3xl font-bold mb-6 text-center text-gray-800">Verify Detection</h2>
            {('<p class="mb-4 text-lg text-gray-700">Name: <span class="font-semibold">' + name + '</span></p>') if name else ''}
            {('<div class="mb-6"><button onclick="fetchAndPlayAudio()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-md transition duration-300 ease-in-out">Load Audio</button></div>') if audio_url else ''}
            <audio id="audioPlayer" controls style="display: none;" class="w-full mb-6"></audio>
            <div class="flex space-x-4">
                <button onclick="updateGroundTruth(true)" class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-3 px-6 rounded-md transition duration-300 ease-in-out">
                    Confirm
                </button>
                <button onclick="updateGroundTruth(false)" class="flex-1 bg-red-600 hover:bg-red-700 text-white font-bold py-3 px-6 rounded-md transition duration-300 ease-in-out">
                    Reject
                </button>
            </div>
            <div class="mt-4">
                <button onclick="window.close()" class="w-full bg-gray-500 hover:bg-gray-600 text-white font-bold py-3 px-6 rounded-md transition duration-300 ease-in-out">
                    Close
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
        threading.Thread(target=audio_processor.update_known_classes, daemon=True).start()
        return JSONResponse(status_code=200, content={"message": "Ground truth updated successfully"})
    except Exception as e:
        logger.error(f"Error updating ground truth: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating ground truth")

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
async def gps_map(request: Request, start_date: str = None, end_date: str = None, days: int = 1):
    try:
        # Determine the time range for GPS data
        end_time = datetime.utcnow()
        if start_date and end_date:
            start_time = datetime.fromisoformat(start_date)
            end_time = datetime.fromisoformat(end_date)
        else:
            start_time = end_time - timedelta(days=days)
        
        query = f"SELECT * FROM gps_data WHERE created_at >= '{start_time}' AND created_at <= '{end_time}' ORDER BY created_at DESC"
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

        return templates.TemplateResponse("map.html", {"request": request, "geojson": geojson})
    except Exception as e:
        logger.error(f"Error generating GPS map: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("REALTIME_SERVER_PORT", "8000"))
    host = os.getenv("REALTIME_SERVER_URL", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
    #443, ssl_keyfile="path/to/your/keyfile.pem", ssl_certfile="path/to/your/certfile.pem")
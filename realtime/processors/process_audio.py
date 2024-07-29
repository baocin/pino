import threading
import datetime
import base64 
import os 
import zstd
import requests
import time
import json
import asyncio
import torch
import torchaudio
import numpy as np
import re
import struct
import pycodec2
import numpy as np
import wave
import schedule
from fastapi import HTTPException
import sys
import os
from transformers import ClapModel, ClapProcessor
from sklearn.metrics.pairwise import cosine_similarity
import logging
import librosa
import psycopg2

from websockets.sync.client import connect


# Add the directory containing whisper_streaming to the Python path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from libraries.gotify.gotify import send_gotify_message

# Set up logging
log_file = 'process_audio.log'
logging.basicConfig(filename=log_file, level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERVER_START_TIME = int(datetime.datetime.now().timestamp())

class AudioProcessor:
    def __init__(self, db_interface):
        self.db = db_interface
        self.known_classes = self.db.get_known_classes(type='audio')
        self.audio_start_time = None
        self.sample_rate = 8000
        self.channels = 1
        self.sample_width = 2
        self.speech_probs = []
        self.audio_frame_cache = []
        self.speech_detected = False
        self.device_id = 1
        self.last_speech_detected = 0
        if not os.path.exists("audio/persistent"):
            os.makedirs("audio/persistent")
        logger.info("AudioProcessor initialized")

        # initialize streamed whisper
        # Initialize WebSocket connection to whisper-streaming
        self.whisper_ws = None
        self.whisper_url = "ws://whisper-streaming:43007/"
        self.connect_to_whisper()

        # zero shot audio classification
        self.audio_classification_buffer_path = "audio/temp_classification_buffer.wav"
        self.clap_model = ClapModel.from_pretrained("laion/clap-htsat-unfused")
        self.clap_processor = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")
        self.classification_lock = asyncio.Lock()

        schedule.every(1).minutes.do(self.update_known_classes)

    def update_known_classes(self):
        self.known_classes = self.db.get_known_classes(type='audio')
        logger.info("Updated known_classes")

    def on_message(self, message):
        logger.info(f"Received message from whisper-streaming: {message}")
        # Process the received transcription here
        threading.Thread(target=lambda: self.db.insert_speech_data(message, json.dumps({}), None, None, self.device_id), daemon=True).start()

    def connect_to_whisper(self):
        try:
            self.whisper_ws = connect(self.whisper_url)
            logger.info("Connected to whisper-streaming WebSocket")
            
            # Start a background thread to handle incoming messages
            threading.Thread(target=self.receive_messages, daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to connect to whisper-streaming: {e}")
            self.whisper_ws = None
    
    def receive_messages(self):
        while True:
            try:
                message = self.whisper_ws.recv()
                self.on_message(message)
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                break
        
    def send_audio_to_whisper(self, audio_data):
        if self.whisper_ws is None:
            logger.info("+++++++++++++++++++++++ Connecting to whisper-streaming")
            self.connect_to_whisper()
        
        if self.whisper_ws:
            try:
                # logger.info(">>>>>>>>>>>>>>>>>>>>>>> Sending audio to whisper-streaming")
                # Convert audio_data to Int16Array
                int16_data = np.frombuffer(audio_data, dtype=np.int16)
                # Resample to 16000 Hz if necessary
                if self.sample_rate != 16000:
                    if self.sample_rate < 16000:
                        int16_data = self.upsample_buffer(int16_data, self.sample_rate, 16000)
                # Send the audio data as an ArrayBuffer
                self.whisper_ws.send(int16_data.tobytes())
               
            except Exception as e:
                logger.error(f"==================== Error sending audio to whisper-streaming: {e}")
                self.whisper_ws = None

    def upsample_buffer(self, buffer, sampleRate, outSampleRate):
        if outSampleRate == sampleRate:
            return buffer
        if outSampleRate < sampleRate:
            raise ValueError('upsampling rate should be larger than original sample rate')
        
        sampleRateRatio = outSampleRate / sampleRate
        newLength = int(len(buffer) * sampleRateRatio)
        result = np.zeros(newLength, dtype=np.int16)
        
        for i in range(newLength):
            sourceIndex = int(i / sampleRateRatio)
            result[i] = buffer[sourceIndex]
        
        return result

    async def detect_known_audio_classes(self, audio_path):
        if not os.path.exists(audio_path):
            logger.warning(f"Audio file not found: {audio_path}")
            return

        # Load audio data with the required sample rate of 48000
        audio_data, sr = librosa.load(audio_path, sr=8000)
        # logger.info(f"Loaded audio data shape: {audio_data.shape}, sr: {sr}")

        # Ensure the audio data is at 48000 Hz sample rate
        if sr != 48000:
            audio_data = librosa.resample(audio_data, orig_sr=sr, target_sr=48000)
            sr = 48000
        # logger.info(f"Audio data shape: {audio_data.shape}, Sample rate: {sr}")

        audio_embed = self.embed_audio(audio_data, sr)

        for known_class in self.known_classes:
            known_embed = np.array(known_class['embedding'], dtype=np.float32)
            similarity = cosine_similarity(audio_embed, known_embed.reshape(1, -1))[0][0]

            if similarity >= known_class['radius_threshold']:
                logger.info(f"Detected known audio class: {known_class['name']} with similarity {similarity:.4f}")
                try:
                    returned_row = self.db.sync_query(
                        """
                        INSERT INTO known_class_detections 
                        (known_class_id, distance, source_data, source_data_type, metadata, embedding) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (known_class['id'],
                        float(similarity),  # Ensure similarity is a Python float
                        psycopg2.Binary(audio_data.tobytes()),  # Convert numpy array to bytes
                        'audio',
                        json.dumps({
                            'audio_start_time': self.audio_start_time,
                        }),
                        json.dumps(audio_embed.squeeze().tolist())  # Convert numpy array to JSON string
                        )
                    )
                    inserted_id = returned_row[0][0]


                    try:
                        extras = {
                            "client::display": {
                                "contentType": "text/plain"
                            },
                            "client::notification": {
                                "click": {
                                    "url": f"http://{os.getenv('SERVER_URL')}:{os.getenv('SERVER_PORT')}/verify-detection/{inserted_id}?name={known_class['name']}&audio_url=http://{os.getenv('SERVER_URL')}:{os.getenv('SERVER_PORT')}/get-detection-audio/{inserted_id}",
                                }
                            }
                        }
                        if known_class.get('ignore', False) or known_class.get('gotify_priority', 10) < 0:
                            logger.info(f"Ignoring class detection: {known_class['name']} ({similarity:.4f} out of {known_class['radius_threshold']:.4f})")
                            return
                        else:
                            logger.info(f"Sending gotify message for class detection: {known_class['name']} ({similarity:.4f} out of {known_class['radius_threshold']:.4f}) {extras}")
                            send_gotify_message(
                                title=f"Detected {known_class['name']}", 
                                message=f"Similarity: {similarity:.4f}, Threshold: {known_class['radius_threshold']:.4f}",
                                extras=extras,
                                priority=known_class.get('gotify_priority', 10)
                            )
                    except Exception as e:
                        logger.error(f"Error sending gotify message: {str(e)}")

                    # logger.info(f"Similarity to {known_class['name']}: {similarity:.4f}, Threshold: {known_class['radius_threshold']:.4f}")
                    # http://pino.steele.red:8081/verify-detection/1?name=electric_toothbrush&audio_url=http://pino.steele.red:8081/get-detection-audio/1
                except Exception as e:
                    logger.error(f"Error inserting known class detection: {str(e)}")

            # Delete the audio classification buffer file
            if os.path.exists(audio_path):
                os.remove(audio_path)


    async def handle_audio_message(self, message, websocket, device_id):
        audio_data_base64 = message.get("data")
        if not audio_data_base64:
            logger.error("No audio data received")
            raise HTTPException(status_code=422, detail="Unprocessable Entity: No audio data received")
        self.audio_start_time = datetime.datetime.now().isoformat()
        audio_data = self.decode_and_decompress_audio(audio_data_base64)
        
        # Long term storage of audio
        self.today_wav_file_path = self.calculate_date_path(source=device_id)
        self.append_audio_to_file(audio_data, file_path=self.today_wav_file_path)
        file_length = os.path.getsize(self.today_wav_file_path) - 44
        self.write_wav_header(self.today_wav_file_path, self.sample_rate, self.sample_width * 8, 1, file_length)


        try:
            self.send_audio_to_whisper(audio_data)
        except Exception as e:
            logger.error(f"Error sending audio to Whisper: {str(e)}")


        # Create the audio classification buffer file if it doesn't exist
        if not os.path.exists(self.audio_classification_buffer_path):
            with open(self.audio_classification_buffer_path, 'wb') as f:
                # Write an empty WAV header
                f.write(b'\x00' * 44)
            # logger.info(f"Created new audio classification buffer file: {self.audio_classification_buffer_path}")
        self.append_audio_to_file(audio_data, file_path=self.audio_classification_buffer_path)
        file_length = os.path.getsize(self.audio_classification_buffer_path) - 44
        self.write_wav_header(self.audio_classification_buffer_path, self.sample_rate, self.sample_width * 8, 1, file_length)
        samples_per_5_seconds = 5 * self.sample_rate

        if file_length >= samples_per_5_seconds * self.sample_width:
            if self.classification_lock.locked():
                pass
            else:
                self.send_audio_to_whisper(audio_data)
                # Convert the audio data to float32 numpy array
                async with self.classification_lock:
                    asyncio.create_task(self.detect_known_audio_classes(self.audio_classification_buffer_path))
                

        # Pass the audio data to the whisper streaming processor
        # self.online.process_audio(audio_data)
        # ad = np.frombuffer(audio_data, dtype=np.float32)
        
        
    
    def embed_audio(self, audio_data, sample_rate):
        inputs = self.clap_processor(audios=audio_data, return_tensors="pt", sampling_rate=sample_rate)
        audio_embed = self.clap_model.get_audio_features(**inputs)
        # logging.info("audio_embed before numpy detach", audio_embed)
        return audio_embed.detach().numpy()

    def calculate_date_path(self, days_in_past=0, format="wav", prefix="", source="phone"):
        target_day = (datetime.datetime.now() - datetime.timedelta(days=days_in_past)).strftime("%Y-%m-%d")
        return f"audio/persistent/{prefix}{source}_{target_day}.{format}"
    
    def create_wav_header(self, sample_rate, bits_per_sample, channels, data_size):
        chunk_id = b'RIFF'
        chunk_size = (36 + data_size).to_bytes(4, 'little')
        format = b'WAVE'
        subchunk1_id = b'fmt '
        subchunk1_size = (16).to_bytes(4, 'little')
        audio_format = (1).to_bytes(2, 'little')  # PCM
        num_channels = channels.to_bytes(2, 'little')
        sample_rate_bytes = sample_rate.to_bytes(4, 'little')
        byte_rate = ((sample_rate * channels * bits_per_sample) // 8).to_bytes(4, 'little')
        block_align = ((channels * bits_per_sample) // 8).to_bytes(2, 'little')
        bits_per_sample_bytes = bits_per_sample.to_bytes(2, 'little')
        subchunk2_id = b'data'
        subchunk2_size = data_size.to_bytes(4, 'little')
        header = (chunk_id + chunk_size + format + subchunk1_id + subchunk1_size + audio_format +
                  num_channels + sample_rate_bytes + byte_rate + block_align + bits_per_sample_bytes +
                  subchunk2_id + subchunk2_size)
        return header

    def write_wav_header(self, file_path, sample_rate, bits_per_sample, channels, data_size):
        header = self.create_wav_header(sample_rate, bits_per_sample, channels, data_size)
        with open(file_path, 'r+b') as f:
            f.seek(0)
            f.write(header)

    def decode_and_decompress_audio(self, audio_data_base64):
        compressed_audio_data = base64.b64decode(audio_data_base64)
        decompressed_audio_data = zstd.decompress(compressed_audio_data)
        return decompressed_audio_data

    def append_audio_to_file(self, audio_data, file_path):
        if not os.path.exists(file_path):
            # Create a new WAV file with header if it doesn't exist
            with wave.open(file_path, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.sample_width)
                wf.setframerate(self.sample_rate)
                wf.writeframes(b'')  # Write empty frames to create the header

        with open(file_path, "ab") as audio_file:
            audio_file.write(audio_data)


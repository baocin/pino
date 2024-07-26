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

# Add the directory containing whisper_streaming to the Python path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from libraries.whisper_streaming import whisper_online
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
        whisper_cache_dir = "whisper_cache"
        self.asr = whisper_online.FasterWhisperASR(lan="en", cache_dir=whisper_cache_dir, model_dir="distil-large-v3")
        self.online = whisper_online.OnlineASRProcessor(self.asr)
        self.target_buffer_size_in_seconds = 1
        self.online_buffer = torch.tensor([], dtype=torch.float32)
        logger.info("Whisper streaming initialized")

        # zero shot audio classification
        self.audio_classification_buffer_path = "audio/temp_classification_buffer.wav"
        self.clap_model = ClapModel.from_pretrained("laion/clap-htsat-unfused")
        self.clap_processor = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")
        self.classification_lock = asyncio.Lock()


    
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
        # logging.info(f"Audio embed: {audio_embed}, shape: {audio_embed.shape}")

        for known_class in self.known_classes:
            known_embed = np.array(known_class['embedding'], dtype=np.float32)
            similarity = cosine_similarity(audio_embed, known_embed.reshape(1, -1))[0][0]

            if similarity >= known_class['radius_threshold']:
                
                # logger.info(f"Detected known audio class: {known_class['name']} with similarity {similarity:.4f}")
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
                                    # "url": "http://steele.red"
                                    "url": f"http://{os.getenv('SERVER_URL')}:{os.getenv('SERVER_PORT')}/verify-detection/{inserted_id}?name={known_class['name']}&audio_url=http://{os.getenv('SERVER_URL')}:{os.getenv('SERVER_PORT')}/get-detection-audio/{inserted_id}",
                                }
                            }
                        }
                        logger.info(f"Notification extras: {extras}")
                        send_gotify_message(
                            title=f"Detected {known_class['name']}", 
                            message=f"Similarity: {similarity:.4f}, Threshold: {known_class['radius_threshold']:.4f}",
                            extras=extras,
                            priority=10
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
                # logger.info("Classification in progress, skipping this batch")
                pass
            else:
                async with self.classification_lock:
                    asyncio.create_task(self.detect_known_audio_classes(self.audio_classification_buffer_path))
                # logger.info("Classification task created, releasing lock")

    
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

    # def run_scheduler(self):
    #     while True:
    #         schedule.run_pending()
    #         time.sleep(1)
    
    # def daily_task(self):
    #     # Transcribe yesterdays speech only file
    #     yesterday_vad_file_path = self.calculate_date_path(prefix="vad_", days_in_past=1, source=self.device_id)
    #     if os.path.exists(yesterday_vad_file_path):
    #         start_time = datetime.datetime.now().isoformat()
    #         print("Vadding ", yesterday_vad_file_path)
    #         new_yesterday_vad_file_path = yesterday_vad_file_path.replace(".wav", "_processed.wav")
    #         try:
    #             os.rename(yesterday_vad_file_path, new_yesterday_vad_file_path)
    #         except Exception as e:
    #             print('Couldnt remove yesterday vad file', e)
    #         self.process_audio_file(
    #             new_yesterday_vad_file_path, start_time, self.device_id)
        
    # async def call_whisper_transcribe(self, file_path):
    #     reqUrl = "https://baocin--whisper-v3-entrypoint.modal.run/transcribe"
    #     post_files = {
    #         "file": open(file_path, "rb"),
    #     }
    #     headersList = {
    #         "Accept": "*/*",
    #         "User-Agent": "Thunder Client (https://www.thunderclient.com)"
    #     }
    #     payload = ""

    #     response = requests.request("POST", reqUrl, data=payload, files=post_files, headers=headersList)
    #     call_id = response.text.strip().replace('"', '')
    #     print(f"Call ID: {call_id}")
    #     return call_id

    # async def get_whisper_result(self, call_id):
    #     reqUrl = "https://baocin--whisper-v3-entrypoint.modal.run/call_id"
    #     headersList = {
    #         "Content-Type": "multipart/form-data; boundary=kljmyvW1ndjXaOEAg4vPm6RBUqO6MC5A" 
    #     }
    #     payload = f"--kljmyvW1ndjXaOEAg4vPm6RBUqO6MC5A\r\nContent-Disposition: form-data; name=call_id\r\n\r\n{call_id}\r\n--kljmyvW1ndjXaOEAg4vPm6RBUqO6MC5A--\r\n"
        
    #     while True:
    #         response = requests.request("POST", reqUrl, data=payload, headers=headersList)
    #         if response.status_code == 200:
    #             whisper_result = response.json()
    #             print(whisper_result)
    #             return whisper_result
    #         else:
    #             print(f"Waiting for transcription result, status code: {response.status_code}")
    #             time.sleep(5)

    # async def process_audio_file(self, file_path, audio_start_time, device_id):
    #     # Check the duration of the audio file
    #     with wave.open(file_path, 'rb') as audio_file:
    #         frame_rate = audio_file.getframerate()
    #         num_frames = audio_file.getnframes()
    #         duration = num_frames / float(frame_rate)
        
    #     # If the duration is less than or equal to 20 seconds, return
    #     if duration <= 20: # super short audio = SHIT transcription on whisper
    #         return
        
    #     # with open(file_path, 'rb') as vad_audio_file:
    #     #     raw_vad_audio = vad_audio_file.read()

    #     # Transcribe the audio file
    #     call_id = await self.call_whisper_transcribe(file_path)
    #     whisper_result = await self.get_whisper_result(call_id)
    #     print(f"Whisper result: {json.dumps(whisper_result)}")
        
    #     if whisper_result:
    #         started_at = datetime.datetime.fromisoformat(audio_start_time)
    #         ended_at = datetime.datetime.now()
    #         text_result = whisper_result[0]['text'] if whisper_result and isinstance(whisper_result, list) and 'text' in whisper_result[0] else None
    #         print("Text Result", text_result)
    #         # embeded_text = embedder.embed_text([text_result])
    #         self.db.insert_speech_data(text_result, json.dumps(whisper_result), started_at, ended_at, device_id)
    #         yesterday_vad_file_path = self.calculate_date_path(
    #             prefix="vad_", days_in_past=1, source=device_id).replace('.wav', '.txt')
    #         with open(yesterday_vad_file_path, 'w') as text_file:
    #             text_file.write(text_result)
    
    # def convert_to_codec2(self, input_path, output_path):
    #     print("convert_to_codec2")
    #     if not os.path.exists(input_path):
    #         print("Input file does not exist", input_path)
    #         return None
        
    #     c2 = pycodec2.Codec2(1200)
    #     INT16_BYTE_SIZE = 2
    #     PACKET_SIZE = c2.samples_per_frame() * INT16_BYTE_SIZE
    #     STRUCT_FORMAT = '{}h'.format(c2.samples_per_frame())

    #     with open(input_path, 'rb') as input_file, \
    #          open(output_path, 'wb') as output_file:
    #         while True:
    #             packet = input_file.read(PACKET_SIZE)
    #             if len(packet) != PACKET_SIZE:
    #                 break
    #             packet = np.array(struct.unpack(STRUCT_FORMAT, packet), dtype=np.int16)
    #             encoded = c2.encode(packet)
    #             output_file.write(encoded)
    #     try:
    #         # os.remove(input_path)
    #         processed_filename = os.path.splitext(os.path.basename(input_path))[
    #             0] + '_processed_to_codec' + os.path.splitext(input_path)[1]
    #         processed_filepath = os.path.join(
    #             os.path.dirname(input_path), processed_filename)
    #         os.rename(output_path, processed_filepath)
    #     except Exception as e:
    #         print('renamed older file', e)




        # Archive any older than today audio as codec2
        # self.yesterday_wav_file_path = self.calculate_date_path(1, source=device_id)
        # self.yesterday_codec2_file_path = self.calculate_date_path(1, format='raw', source=device_id)
        # if os.path.exists(self.today_wav_file_path) and not os.path.exists(self.yesterday_codec2_file_path):
        #     threading.Thread(target=self.convert_to_codec2, args=(self.yesterday_wav_file_path, self.yesterday_codec2_file_path)).start()
        # print("Converted to codec2")
        # Detect Speech
        # yesterdays_temp_vad_file_path = self.calculate_date_path(prefix="vad_temp_", source=device_id)
        # print(
        #     f"Yesterday's temp VAD file path: {yesterdays_temp_vad_file_path}")
        # if os.path.exists(yesterdays_temp_vad_file_path):
        #     print(
        #         f"Removing yesterday's temp VAD file: {yesterdays_temp_vad_file_path}")
        #     os.remove(yesterdays_temp_vad_file_path)
        # print("Yesterday's temp VAD file removed if it existed")
        # todays_temp_vad_file_path = self.calculate_date_path(prefix="vad_temp_", source=device_id)
        # print(f"Today's temp VAD file path: {todays_temp_vad_file_path}")
        # self.append_audio_to_file(audio_data, file_path=todays_temp_vad_file_path)
        # print(f"Audio data appended to {todays_temp_vad_file_path}")
        # self.write_wav_header(todays_temp_vad_file_path, self.sample_rate, self.sample_width * 8, 1, len(audio_data))
        # print(f"WAV header written to {todays_temp_vad_file_path}")
        # wav = self.read_audio(todays_temp_vad_file_path, sampling_rate=self.sample_rate)
        # print(f"Audio read from {todays_temp_vad_file_path}")
        # todays_vad_file_path = self.calculate_date_path(prefix="vad_", source=device_id)
        # print(f"Today's VAD file path: {todays_vad_file_path}")
        # await self.detect_and_save_speech(audio_data, device_id, todays_vad_file_path)
        # print("Speech detection and saving completed")
        # print("Speech detected")


    # async def detect_and_save_speech(self, audio_data, source, todays_vad_file_path):
    #     print("detect_and_save_speech")
    #     self.audio_frame_cache.append(audio_data)
    #     if self.speech_detected:
    #         self.last_speech_detected += 1

    #     tensor = torch.tensor(np.frombuffer(
    #         audio_data, dtype=np.int16).astype(np.float32))
    #     window_size_samples = 512
    #     buffer_frames = 10  # Number of frames to include before and after speech

    #     for i in range(0, len(tensor), window_size_samples):
    #         audio_chunk = tensor[i: i + window_size_samples]

    #         if len(audio_chunk) < window_size_samples:
    #             break
    #         speech_prob = self.model(audio_chunk, self.sample_rate).item()
    #         self.speech_probs.append(speech_prob)
    #         recent_probs = self.speech_probs[-10:]
    #         mean_prob = np.mean(recent_probs)
    #         std_dev = np.std(recent_probs)
    #         threshold = mean_prob + 2 * std_dev

    #         if speech_prob and speech_prob > 0.15 and speech_prob > threshold:
    #             self.speech_detected = True

    #         # Yield control to the event loop to allow other tasks to run
    #         await asyncio.sleep(0)

    #     if self.speech_detected and self.last_speech_detected > 20:
    #         start_index = max(0, len(self.audio_frame_cache) -
    #                         self.last_speech_detected - buffer_frames)
    #         end_index = len(self.audio_frame_cache)
    #         for frame in self.audio_frame_cache[start_index:end_index]:
    #             self.append_audio_to_file(
    #                 bytearray(frame), file_path=todays_vad_file_path)
    #         silence_duration = 1  # 1 second
    #         silence_audio = np.zeros(
    #             int(self.sample_rate * silence_duration), dtype=np.int16).tobytes()
    #         self.append_audio_to_file(
    #             silence_audio, file_path=todays_vad_file_path)
    #         file_length = os.path.getsize(todays_vad_file_path) - 44
    #         self.write_wav_header(
    #             todays_vad_file_path, self.sample_rate, self.sample_width * 8, 1, file_length)
    #         # Clear processed frames
    #         self.audio_frame_cache = self.audio_frame_cache[end_index:]
    #         start_time = datetime.datetime.now().isoformat()
    #         self.last_speech_detected = 0
    #         self.speech_detected = False

    #     self.vad_iterator.reset_states()


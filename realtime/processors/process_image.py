from fastapi import HTTPException
import surya
import base64
from datetime import datetime
import zstd
import sys
import os
import tempfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from libraries.embed.embed import EmbeddingService

class ImageProcessor:
    def __init__(self, db_interface):
        self.last_screenshot = None
        self.db = db_interface
        self.embedding_service = EmbeddingService()

    async def handle_image_message(self, message, websocket, device_id=1):
        is_screenshot = message.get("is_screenshot", False)
        is_generated = message.get("is_generated", False)
        is_manual = message.get("is_manual", False)
        is_front_camera = message.get("is_front_camera", False)
        is_rear_camera = message.get("is_rear_camera", False)
        image_data_base64 = message.get("data")
        image_hash = message.get("image_hash", None)
        image_id = message.get("image_id", None)
        metadata = message.get("metadata", None)
        print(f"""
            is_screenshot:   {is_screenshot}
            is_generated:    {is_generated}
            is_manual:       {is_manual}
            is_front_camera: {is_front_camera}
            is_rear_camera:  {is_rear_camera}
            image_hash:      {image_hash}
            image_id:        {image_id}
            metadata:        {metadata}
        """, flush=True)

        return
        if not image_data_base64:
            raise HTTPException(status_code=422, detail="Unprocessable Entity: No image data provided")

        # Query the database to check if the image hash already exists
        if image_hash:
            query = "SELECT id FROM image_data WHERE image_id = %s"
            result = self.db.execute(query, (image_id,))
            
            if result:
                print(f"Image with hash {image_hash} already exists in the database. Skipping insertion.")
                return  # Exit the function if the image already exists
        
        # If the image doesn't exist or no hash was provided, proceed with processing
        compressed_image_data = base64.b64decode(image_data_base64)
        image_data = zstd.decompress(compressed_image_data)

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webp') as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name
                image_embedding = self.embedding_service.embed_image(temp_file_path)[0]
        except Exception as e:
            print(f"Error processing image: {str(e)}")
            image_embedding = None

        # location = message.get("location", None)
        # camera_pose = message.get("camera_pose", None)
        # metadata = message.get("metadata", None)
        # ocr_result = message.get("ocr_result", None)

        query = """
        INSERT INTO image_data (
            device_id, image_data, is_screenshot, is_generated, is_manual, 
            is_front_camera, is_rear_camera, image_embedding, sha256
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """
        result = self.db.execute_query(query, (
            device_id, image_data, is_screenshot, is_generated, is_manual, 
            is_front_camera, is_rear_camera, image_embedding, image_hash
        ))
        print(f"Image data inserted. Result: {result}")
        

    def _convert_to_degrees(self, value):
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
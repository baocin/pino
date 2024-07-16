
import surya
import base64
from datetime import datetime
import zstd

class PhotoProcessor:
    def __init__(self, db_interface):
        self.last_photo = None
        self.db = db_interface
        # self.det_processor, self.det_model = segformer.load_processor(), segformer.load_model()
        # self.rec_model, self.rec_processor = load_model(), load_processor()
        # self.langs = ["en"]  # Replace with your languages

    async def handle_photo_message(self, message, websocket, device_id):
        photo_data_base64 = message.get("photo")
        is_screenshot = message.get("isScreenshot", False)
        if not photo_data_base64:
            raise HTTPException(status_code=422, detail="Unprocessable Entity: No photo data provided")
        
        compressed_photo_data = base64.b64decode(photo_data_base64)
        decompressed_photo_data = zstd.decompress(compressed_photo_data)
        photo_data = decompressed_photo_data
        
        if photo_data == self.last_photo:
            return
        self.last_photo = photo_data
        self.db.insert_manual_photo_data(photo_data, is_screenshot, device_id)
        
        # Run OCR in an asyncio thread
        # await asyncio.to_thread(self.run_ocr_on_screenshot, photo_data, timestamp, source)

    # def run_ocr_on_screenshot(self, photo_data, timestamp, source):
    #     image = Image.open(io.BytesIO(photo_data))
    #     try:
    #         predictions = run_ocr([image], [self.langs], self.det_model, self.det_processor, self.rec_model, self.rec_processor)
    #         ocr_result = []
    #         for prediction in predictions:
    #             text_lines = []
    #             for line in prediction.text_lines:
    #                 text_lines.append({
    #                     "polygon": line.polygon,
    #                     "confidence": line.confidence,
    #                     "text": line.text,
    #                     "bbox": line.bbox
    #                 })
    #             ocr_result.append({
    #                 "text_lines": text_lines,
    #                 "languages": prediction.languages,
    #                 "image_bbox": prediction.image_bbox,
    #                 "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
    #                 "source": source
    #             })
    #         for result in ocr_result:
    #             merged_text = " ".join([line["text"] for line in result["text_lines"]])
    #             result["merged_text"] = merged_text

    #         ocr_result_json = orjson.dumps(ocr_result, option=orjson.OPT_NAIVE_UTC | orjson.OPT_NON_STR_KEYS).decode()
    #         print(ocr_result_json)
    #     except IndexError as e:
    #         print(f"List index out of range error during OCR processing: {e}")
    #     except Exception as e:
    #         print(f"Error during OCR processing: {e}")
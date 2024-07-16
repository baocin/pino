
import surya
import base64
from datetime import datetime
import zstd

class ScreenshotProcessor:
    def __init__(self, db_interface):
        self.last_screenshot = None
        self.db = db_interface
        # self.det_processor, self.det_model = segformer.load_processor(), segformer.load_model()
        # self.rec_model, self.rec_processor = load_model(), load_processor()
        # self.langs = ["en"]  # Replace with your languages

    async def handle_screenshot_message(self, message, websocket, device_id):
        screenshot_data_base64 = message.get("data")
        if not screenshot_data_base64:
            raise HTTPException(status_code=422, detail="Unprocessable Entity: No screenshot data received")
        
        compressed_screenshot_data = base64.b64decode(screenshot_data_base64)
        decompressed_screenshot_data = zstd.decompress(compressed_screenshot_data)
        screenshot_data = decompressed_screenshot_data
        
        if screenshot_data == self.last_screenshot:
            return
        self.last_screenshot = screenshot_data
        timestamp = int(datetime.now().timestamp())
        self.db.insert_screenshot_data(screenshot_data, device_id)

        # Run OCR in an asyncio thread
        # await asyncio.to_thread(self.run_ocr_on_screenshot, screenshot_data, timestamp, source)

    def run_ocr_on_screenshot(self, screenshot_data, timestamp, device_id):
        image = Image.open(io.BytesIO(screenshot_data))
        try:
            predictions = run_ocr([image], [self.langs], self.det_model, self.det_processor, self.rec_model, self.rec_processor)
            ocr_result = []
            for prediction in predictions:
                text_lines = []
                for line in prediction.text_lines:
                    text_lines.append({
                        "polygon": line.polygon,
                        "confidence": line.confidence,
                        "text": line.text,
                        "bbox": line.bbox
                    })
                ocr_result.append({
                    "text_lines": text_lines,
                    "languages": prediction.languages,
                    "image_bbox": prediction.image_bbox,
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "device_id": device_id
                })
            for result in ocr_result:
                merged_text = " ".join([line["text"] for line in result["text_lines"]])
                result["merged_text"] = merged_text

            ocr_result_json = orjson.dumps(ocr_result, option=orjson.OPT_NAIVE_UTC | orjson.OPT_NON_STR_KEYS).decode()
            print(ocr_result_json)
        except IndexError as e:
            print(f"List index out of range error during OCR processing: {e}")
        except Exception as e:
            print(f"Error during OCR processing: {e}")
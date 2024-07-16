import requests
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM

class Florence2:
    def __init__(self, model_name="microsoft/Florence-2-large"):
        self.model = AutoModelForCausalLM.from_pretrained(model_name, trust_remote_code=True)
        self.processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

    def generate_text_from_image(self, image_url, prompt="<OD>", max_new_tokens=1024, num_beams=3, do_sample=False):
        image = Image.open(requests.get(image_url, stream=True).raw)
        inputs = self.processor(text=prompt, images=image, return_tensors="pt")

        generated_ids = self.model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=max_new_tokens,
            num_beams=num_beams,
            do_sample=do_sample
        )
        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed_answer = self.processor.post_process_generation(generated_text, task=prompt, image_size=(image.width, image.height))

        return parsed_answer

if __name__ == "__main__":
    florence_util = Florence2()
    result = florence_util.generate_text_from_image("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg?download=true")
    print(result)

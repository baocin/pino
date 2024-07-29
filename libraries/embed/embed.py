from fastembed import TextEmbedding, ImageEmbedding
from typing import List
import numpy as np
from transformers import ClapModel, ClapProcessor
import librosa

class EmbeddingService:
    def __init__(self):
        self.text_model = TextEmbedding(model_name="Qdrant/clip-ViT-B-32-text")
        self.image_model = ImageEmbedding(model_name="Qdrant/clip-ViT-B-32-vision")
        self.clap_model = ClapModel.from_pretrained("laion/clap-htsat-unfused")
        self.clap_processor = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")

    def embed_text(self, texts: List[str]):
        embeddings = self.text_model.embed(texts)
        return [embedding.tolist() for embedding in embeddings]

    def embed_image(self, image_path: str):
        embeddings = self.image_model.embed([image_path])
        return [embedding.tolist() for embedding in embeddings]

    def embed_audio(self, audio_path: str):
        audio_data, sr = librosa.load(audio_path, sr=48000)
        inputs = self.clap_processor(audios=audio_data, return_tensors="pt", sampling_rate=sr)
        audio_embed = self.clap_model.get_audio_features(**inputs)
        return audio_embed.detach().numpy().tolist()

from fastembed import TextEmbedding, ImageEmbedding
from typing import List
import numpy as np

class EmbeddingService:
    def __init__(self):
        self.text_model = TextEmbedding(model_name="Qdrant/clip-ViT-B-32-text")
        self.image_model = ImageEmbedding(model_name="Qdrant/clip-ViT-B-32-vision")

    def embed_text(self, texts: List[str]):
        embeddings = self.text_model.embed(texts)
        return [embedding.tolist() for embedding in embeddings]

    def embed_image(self, image_paths: List[str]):
        embeddings = self.image_model.embed(image_paths)
        return [embedding.tolist() for embedding in embeddings]

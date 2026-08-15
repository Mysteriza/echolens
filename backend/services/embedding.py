from google import genai
from core.config import settings

class GeminiEmbeddingService:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = 'text-embedding-004'

    def generate_embedding(self, text: str) -> list[float]:
        try:
            response = self.client.models.embed_content(
                model=self.model_id,
                contents=text
            )
            if response.embeddings:
                return response.embeddings[0].values
        except Exception as e:
            print(f"Error generating embedding: {e}")
            
        return []

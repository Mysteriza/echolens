import os

import torch
from transformers import pipeline

# Aspect Categories removed as Zero-Shot is disabled


class IndoBERTService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return

        print("Detecting Hardware for IndoBERT...")
        self.device_id = -1  # CPU fallback
        self.batch_size = 16

        if torch.cuda.is_available():
            self.device_id = 0
            vram = torch.cuda.get_device_properties(0).total_memory
            if vram > 8 * 1024**3:
                self.batch_size = 100
            else:
                self.batch_size = 50
            print(
                f"Hardware: NVIDIA GPU (CUDA) detected. Batch Size: {self.batch_size}"
            )
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device_id = "mps"
            self.batch_size = 50
            print(
                f"Hardware: Apple Silicon (MPS) detected. Batch Size: {self.batch_size}"
            )
        else:
            cores = os.cpu_count() or 4
            if cores >= 8:
                self.batch_size = 100
            elif cores >= 4:
                self.batch_size = 50
            else:
                self.batch_size = 16
            print(
                f"Hardware: CPU detected ({cores} Cores). Batch Size: {self.batch_size}"
            )

        self.initialized = True

    def load_indobert(self):
        if hasattr(self, "classifier"):
            return
            
        print("Loading IndoBERT Model... (This may take a moment)")
        model_name = "w11wo/indonesian-roberta-base-sentiment-classifier"

        self.classifier = pipeline(
            "sentiment-analysis",
            model=model_name,
            device=self.device_id,
            truncation=True,
            max_length=512,
        )
        print("IndoBERT Model Loaded Successfully!")



    def analyze_sentiment(self, text: str) -> dict:
        try:
            result = self.classifier(text)
            if result and len(result) > 0:
                prediction = result[0]
                return {
                    "sentiment": prediction["label"],
                    "confidence": prediction["score"],
                }
            return {"sentiment": "neutral", "confidence": 0.0}
        except Exception as e:
            print(f"Error in IndoBERT classification: {e}")
            return {"sentiment": "neutral", "confidence": 0.0}

    def analyze_sentiments_batch(self, texts: list[str]) -> list[dict]:
        """
        Analyzes the sentiment of a list of texts using optimized batching.
        """
        if not texts:
            return []

        try:
            results = self.classifier(texts, batch_size=self.batch_size)
            output = []
            for pred in results:
                output.append({"sentiment": pred["label"], "confidence": pred["score"]})
            return output
        except Exception as e:
            print(f"Error in IndoBERT batch classification: {e}")
            return [{"sentiment": "neutral", "confidence": 0.0} for _ in texts]

import logging
import os
import threading

import torch
from transformers import pipeline

logger = logging.getLogger(__name__)

# Aspect Categories removed as Zero-Shot is disabled


class IndoBERTService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return

        logger.info("Detecting Hardware for IndoBERT...")
        self.device_id = -1  # CPU fallback
        self.batch_size = 16

        if torch.cuda.is_available():
            self.device_id = 0
            vram = torch.cuda.get_device_properties(0).total_memory
            if vram > 8 * 1024**3:
                self.batch_size = 100
            else:
                self.batch_size = 50
            logger.info(
                "Hardware: NVIDIA GPU (CUDA) detected. Batch Size: %d", self.batch_size
            )
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device_id = "mps"
            self.batch_size = 50
            logger.info(
                "Hardware: Apple Silicon (MPS) detected. Batch Size: %d", self.batch_size
            )
        else:
            cores = os.cpu_count() or 4
            if cores >= 8:
                self.batch_size = 100
            elif cores >= 4:
                self.batch_size = 50
            else:
                self.batch_size = 16
            logger.info(
                "Hardware: CPU detected (%d Cores). Batch Size: %d", cores, self.batch_size
            )

        self.initialized = True

    def load_indobert(self):
        if hasattr(self, "classifier"):
            return

        with IndoBERTService._lock:
            if hasattr(self, "classifier"):
                return
            logger.info("Loading IndoBERT Model... (This may take a moment)")
            model_name = "w11wo/indonesian-roberta-base-sentiment-classifier"

            if self.device_id == -1:
                from transformers import (
                    AutoModelForSequenceClassification,
                    AutoTokenizer,
                )

                logger.info(
                    "Applying Dynamic Quantization (INT8) for faster CPU inference..."
                )
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model = AutoModelForSequenceClassification.from_pretrained(model_name)

                # Compress Linear layers to INT8 for ~2x speedup on CPU
                quantized_model = torch.quantization.quantize_dynamic(
                    model, {torch.nn.Linear}, dtype=torch.qint8
                )

                self.classifier = pipeline(
                    "sentiment-analysis",
                    model=quantized_model,
                    tokenizer=tokenizer,
                    device=-1,
                    truncation=True,
                    max_length=512,
                )
            else:
                self.classifier = pipeline(
                    "sentiment-analysis",
                    model=model_name,
                    device=self.device_id,
                    truncation=True,
                    max_length=512,
                )
            # Serialize inference: transformers pipelines are not thread-safe.
            self._infer_lock = threading.Lock()
            logger.info("IndoBERT Model Loaded Successfully!")

    def analyze_sentiments_batch(self, texts: list[str]) -> list[dict]:
        """
        Analyzes the sentiment of a list of texts using optimized batching.
        """
        if not texts:
            return []

        try:
            with self._infer_lock:
                results = self.classifier(texts, batch_size=self.batch_size)
            output = []
            for pred in results:
                output.append({"sentiment": pred["label"], "confidence": pred["score"]})
            return output
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in IndoBERT batch classification: %s", exc)
            return [{"sentiment": "neutral", "confidence": 0.0} for _ in texts]

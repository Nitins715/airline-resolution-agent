"""
Hugging Face Client with strict 1 req/sec rate-limiting and robust fallback mechanism.
"""

import time
import threading
import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Thread-safe rate limiter allowing at most 1 request per second."""
    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval = min_interval_seconds
        self.last_called = 0.0
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_called
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
            self.last_called = time.time()


hf_rate_limiter = RateLimiter(min_interval_seconds=1.0)


class HuggingFaceClient:
    """
    Interacts with Hugging Face Inference API with rate-limiting and template fallback.
    """

    @classmethod
    def get_token(cls) -> str:
        return os.environ.get('HUGGINGFACEHUB_API_TOKEN') or getattr(settings, 'HUGGINGFACEHUB_API_TOKEN', '')

    @classmethod
    def generate_response(
        cls,
        prompt: str,
        system_instruction: str = "",
        model_name: str = None
    ) -> str:
        token = cls.get_token()
        if not token:
            logger.info("No Hugging Face token found; using deterministic policy template.")
            return ""

        model = model_name or getattr(settings, 'HF_MODEL_NAME', 'mistralai/Mistral-7B-Instruct-v0.3')
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        full_prompt = f"<s>[INST] {system_instruction}\n\n{prompt} [/INST]"
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": 300,
                "temperature": 0.2,
                "return_full_text": False
            }
        }

        try:
            # Enforce 1 req/sec rate limit
            hf_rate_limiter.acquire()

            response = requests.post(api_url, headers=headers, json=payload, timeout=12)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0 and 'generated_text' in data[0]:
                    generated = data[0]['generated_text'].strip()
                    return generated
            logger.warning(f"HF API returned status {response.status_code}: {response.text}")
        except Exception as e:
            logger.warning(f"Error calling Hugging Face API: {str(e)}")

        return ""

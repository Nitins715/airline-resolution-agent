"""
Hugging Face Client with modern Router API (OpenAI-compatible) and strict 1 req/sec rate-limiting.
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
    Interacts with Hugging Face Inference API / Router with rate-limiting and fallback.
    """

    DEFAULT_LIGHT_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct"

    @classmethod
    def get_token(cls) -> str:
        token = os.environ.get('HUGGINGFACEHUB_API_TOKEN') or getattr(settings, 'HUGGINGFACEHUB_API_TOKEN', '')
        return token.strip().strip('"').strip("'") if token else ""

    @classmethod
    def generate_response(
        cls,
        prompt: str,
        system_instruction: str = "",
        model_name: str = None
    ) -> str:
        token = cls.get_token()
        if not token:
            logger.info("No Hugging Face token found; using deterministic response.")
            return ""

        model = model_name or os.environ.get('HF_MODEL_NAME') or getattr(settings, 'HF_MODEL_NAME', cls.DEFAULT_LIGHT_MODEL)
        if "mistral" in model.lower():
            # Automatically migrate legacy unsupported Mistral model to lightweight supported model
            model = cls.DEFAULT_LIGHT_MODEL

        api_url = "https://router.huggingface.co/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 300,
            "temperature": 0.2
        }

        try:
            hf_rate_limiter.acquire()

            response = requests.post(api_url, headers=headers, json=payload, timeout=12)
            if response.status_code == 200:
                data = response.json()
                choices = data.get('choices', [])
                if choices and 'message' in choices[0] and 'content' in choices[0]['message']:
                    generated = choices[0]['message']['content'].strip()
                    return generated
            logger.warning(f"HF API returned status {response.status_code}: {response.text}")
        except Exception as e:
            logger.warning(f"Error calling Hugging Face API: {str(e)}")

        return ""

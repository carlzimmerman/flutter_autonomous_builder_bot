# ai_client.py

import ollama
from gemini_api_client import GeminiApiClient
from config import USE_GEMINI_API, OLLAMA_MODEL

class AIClient:
    def __init__(self):
        if USE_GEMINI_API:
            self.client = GeminiApiClient()
        else:
            self.client = ollama.Client()

    def generate(self, prompt):
        if USE_GEMINI_API:
            return self.client.generate(prompt)
        else:
            response = self.client.generate(model=OLLAMA_MODEL, prompt=prompt)
            return response  # Return the full response object
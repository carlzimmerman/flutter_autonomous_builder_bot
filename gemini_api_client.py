import json
import logging
from google.generativeai import GenerativeModel, configure, GenerationConfig
from config import GEMINI_API_KEY, GEMINI_MODEL

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GeminiApiClient:
    def __init__(self):
        configure(api_key=GEMINI_API_KEY)
        self.model = GenerativeModel(model_name=GEMINI_MODEL)

    def generate(self, prompt):
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=0.7,
                    top_p=1,
                    top_k=1,
                    max_output_tokens=2048,
                )
            )

            if response.text:
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse JSON from response. Attempting self-correction.")
                    return self.self_correct_json(response.text)
            else:
                raise Exception("No valid response received from Gemini API")
        except Exception as e:
            logger.error(f"Gemini API request failed: {str(e)}")
            raise Exception(f"Gemini API request failed: {str(e)}")

    def self_correct_json(self, invalid_json: str) -> dict:
        correction_prompt = f"""
        The following text is supposed to be a valid JSON object, but it may contain errors:

        {invalid_json}

        Please correct any JSON syntax errors and return only the corrected, valid JSON object.
        Ensure all string values are properly quoted, and any unintended line breaks within string values are removed.
        Do not include any explanation or markdown syntax in your response, just the corrected JSON.
        """

        try:
            correction_response = self.model.generate_content(correction_prompt)
            corrected_json_str = correction_response.text.strip()
            return json.loads(corrected_json_str)
        except Exception as e:
            logger.error(f"Failed to self-correct JSON: {str(e)}")
            # If self-correction fails, return an empty dict or a minimal valid structure
            return {"error": "Failed to generate a valid JSON structure"}
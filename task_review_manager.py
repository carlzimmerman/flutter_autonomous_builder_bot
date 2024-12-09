import json
import re
import logging
from typing import Dict, Any, Optional
from ai_client import AIClient

logger = logging.getLogger(__name__)

class TaskReviewManager:
    def __init__(self, client: AIClient):
        self.client = client
        self.max_retries = 3

    def review_task_plan(self, task_plan: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """
        Review and enhance task plan to ensure it fully captures user requirements.
        """
        prompt = """
        Review and enhance this task plan based on the user's request.

        Original User Request: """ + user_input + """

        Current Task Plan:
        """ + json.dumps(task_plan, indent=2) + """

        Review Instructions:
        1. Identify ALL specific requirements:
           - Numbers (counts, sizes)
           - Text content (exact strings)
           - UI elements (widgets, components)
           - Layout details (positioning)

        2. Enhance ONLY the descriptions to include these details
        3. Keep EXACTLY the same structure and values for:
           - File paths
           - Routes
           - Imports
           - Dependencies

        Return task plan with enhanced descriptions using EXACTLY this structure:
        {
            "steps": [
                {
                    "type": "create_file",
                    "file_path": "lib/screens/name_screen.dart",
                    "description": "Enhanced description with ALL specific details from user request"
                }
            ],
            "update_main_dart": {
                "imports_to_add": ["package:flutter/material.dart"],
                "routes_to_add": {"/route": "ScreenName()"},
                "initial_route": "/route",
                "providers_to_initialize": []
            },
            "dependencies": []
        }

        Respond with ONLY the enhanced JSON object.
        """

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Reviewing task plan (attempt {attempt + 1})")
                response = self.client.generate(prompt=prompt)

                if isinstance(response, dict) and 'response' in response:
                    reviewed_plan = self.extract_json(response['response'])
                elif isinstance(response, str):
                    reviewed_plan = self.extract_json(response)
                else:
                    raise ValueError(f"Unexpected response type: {type(response)}")

                if self.validate_task_plan(reviewed_plan):
                    logger.info("Successfully enhanced task plan")
                    return reviewed_plan
                else:
                    logger.warning(f"Invalid enhanced plan generated (attempt {attempt + 1})")

            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error in review (attempt {attempt + 1}): {str(e)}")
            except Exception as e:
                logger.error(f"Error reviewing task plan (attempt {attempt + 1}): {str(e)}")

        logger.warning("Failed to enhance task plan, returning original")
        return task_plan

    def extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from text, handling various formats."""
        try:
            # First try direct JSON parsing
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON-like structure
            json_pattern = r'\{[\s\S]*\}'  # Matches everything between first { and last }
            match = re.search(json_pattern, text, re.DOTALL)
            if match:
                potential_json = match.group(0)
                # Try robust correction if initial cleaning fails
                cleaned_json = (
                    potential_json
                    .replace('\n', ' ')
                    .replace('```json', '')
                    .replace('```', '')
                    .replace('\"', '"')
                    .replace("'", '"')
                )

                try:
                    return json.loads(cleaned_json)
                except json.JSONDecodeError:
                    # If cleaning fails, try robust correction
                    return self.robust_json_correction(potential_json)

            logger.error("No valid JSON structure found")
            return {}

    def validate_task_plan(self, task_plan: Dict[str, Any]) -> bool:
        """Validate the task plan has required structure."""
        try:
            # Basic structure validation
            required_keys = ['steps', 'update_main_dart', 'dependencies']
            if not all(key in task_plan for key in required_keys):
                logger.error("Missing required top-level keys")
                return False

            # Validate steps
            if not isinstance(task_plan['steps'], list):
                logger.error("'steps' must be a list")
                return False

            for step in task_plan.get('steps', []):
                if not all(key in step for key in ['type', 'file_path', 'description']):
                    logger.error("Step missing required keys")
                    return False
                if step['type'] not in ['create_file', 'update_file', 'delete_file']:
                    logger.error(f"Invalid step type: {step['type']}")
                    return False

            # Validate main.dart updates
            main_dart_updates = task_plan.get('update_main_dart', {})
            required_main_keys = ['imports_to_add', 'routes_to_add', 'initial_route', 'providers_to_initialize']
            if not all(key in main_dart_updates for key in required_main_keys):
                logger.error("Missing required main.dart update keys")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating task plan: {str(e)}")
            return False

    def robust_json_correction(self, invalid_json: str) -> Dict[str, Any]:
        """Attempt to correct invalid JSON."""
        # Remove any non-JSON content before and after the main JSON structure
        json_match = re.search(r'\{.*\}', invalid_json, re.DOTALL)
        if not json_match:
            logger.error(f"No JSON-like structure found in: {invalid_json}")
            return {}

        potential_json = json_match.group(0)

        # Handle escaped quotes within JSON strings
        potential_json = re.sub(r'(?<!\\)"([^"]*)"', lambda m: '"{}"'.format(m.group(1).replace('"', '\\"')), potential_json)

        # Fix common JSON errors
        potential_json = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', potential_json)  # Add quotes to keys
        potential_json = re.sub(r',\s*([}\]])', r'\1', potential_json)  # Remove trailing commas
        potential_json = potential_json.replace("'", '"')  # Replace single quotes with double quotes

        try:
            return json.loads(potential_json)
        except json.JSONDecodeError as e:
            logger.error(f"JSON correction failed: {str(e)}")
            logger.error(f"Problematic JSON: {potential_json}")
            return {}
import json
import os
import re
import logging
from typing import List, Dict, Any, Tuple
from ai_client import AIClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskPlanner:
    def __init__(self, client: AIClient):
        self.client = client
        self.max_retries = 3


    def generate_task_plan(self, user_input: str, current_project_files: Dict[str, str]) -> Dict[str, Any]:
        system_context = """You are a Flutter Development Expert AI that converts natural language into working Flutter applications.

        IMPORTANT:
        - Treat the example structure below as a template - adapt it based on the user's request
        - Extract specific requirements from the user input (e.g., if user asks for 3 items, keep it as 3)
        - Generate only necessary code and files
        - Keep the code minimal but complete
        - Never include test files or comments
        """

        analysis_prompt = f"""
        {system_context}

        Current Task: {user_input}

        Project Structure:
        {json.dumps(list(current_project_files.keys()), indent=2)}

        Return a minimal JSON plan that creates or updates ONLY the necessary files.
        Make sure to:
        1. Include ALL specific requirements from the user input
        2. Only create files that are needed
        3. Keep descriptions detailed and explicit
        4. Match the following structure but adapt it to the actual task

        Example structure (adapt based on actual needs):
        {{
            "steps": [
                {{
                    "type": "create_file",
                    "file_path": "lib/screens/example_screen.dart",
                    "description": "Detailed description including specific requirements from user input"
                }}
            ],
            "update_main_dart": {{
                "imports_to_add": ["package:flutter/material.dart"],
                "routes_to_add": {{}},
                "initial_route": null,
                "providers_to_initialize": []
            }},
            "dependencies": []
        }}

        Return ONLY a valid JSON object.
        Include ALL specific details from user input in the descriptions.
        """

        for attempt in range(self.max_retries):
            try:
                response = self.client.generate(prompt=analysis_prompt)

                if isinstance(response, dict) and 'response' in response:
                    task_plan = self.extract_json(response['response'])
                elif isinstance(response, str):
                    task_plan = self.extract_json(response)
                else:
                    raise ValueError(f"Unexpected response type: {type(response)}")

                # Validate and potentially simplify the plan
                if task_plan and self.validate_task_plan(task_plan):
                    simplified_plan = self._simplify_plan(task_plan)
                    return simplified_plan
                else:
                    logger.warning(f"Generated invalid task plan on attempt {attempt + 1}. Retrying...")

            except Exception as e:
                logger.error(f"Error in generate_task_plan (attempt {attempt + 1}): {str(e)}")

        raise ValueError("Failed to generate a valid task plan after maximum retries.")

    def _simplify_plan(self, task_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simplify the task plan to ensure minimal necessary changes.
        """
        simplified = {
            "steps": [],
            "update_main_dart": {
                "imports_to_add": [],
                "routes_to_add": {},
                "initial_route": None,
                "providers_to_initialize": []
            },
            "dependencies": []
        }

        # Keep only essential steps
        for step in task_plan["steps"]:
            if self._is_step_necessary(step):
                simplified["steps"].append(step)

        # Only include main.dart updates if absolutely needed
        main_updates = task_plan.get("update_main_dart", {})
        if main_updates.get("imports_to_add"):
            simplified["update_main_dart"]["imports_to_add"] = main_updates["imports_to_add"]
        if main_updates.get("initial_route"):
            simplified["update_main_dart"]["initial_route"] = main_updates["initial_route"]
            # Only add routes if we have an initial route
            if main_updates.get("routes_to_add"):
                simplified["update_main_dart"]["routes_to_add"] = main_updates["routes_to_add"]

        # Only include dependencies if they're absolutely required
        if task_plan.get("dependencies"):
            simplified["dependencies"] = [
                dep for dep in task_plan["dependencies"]
                if self._is_dependency_necessary(dep)
            ]

        return simplified

    def _is_step_necessary(self, step: Dict[str, Any]) -> bool:
        """
        Determine if a step is necessary for the requested functionality.
        """
        # Always keep direct screen/widget creation
        if step["type"] == "create_file" and "screens/" in step["file_path"]:
            return True
        # Keep main.dart updates
        if step["file_path"] == "lib/main.dart":
            return True
        # Skip test files
        if "test/" in step["file_path"]:
            return False
        # Skip unnecessary abstractions
        if "utils/" in step["file_path"] or "helpers/" in step["file_path"]:
            return False
        return True

    def _is_dependency_necessary(self, dependency: Dict[str, str]) -> bool:
        """
        Determine if a dependency is necessary for core functionality.
        """
        essential_packages = {"provider", "shared_preferences", "http"}
        return dependency.get("package_name", "") in essential_packages


    def extract_json(self, text: str) -> Dict[str, Any]:
        # First try direct JSON parsing
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # If that fails, try to find and parse JSON
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    # If JSON extraction fails, try to get structured response
                    logger.info("Attempting to get structured response from LLM")
                    return self._get_structured_response(text)
            else:
                logger.error("No JSON structure found. Attempting to get structured response.")
                return self._get_structured_response(text)
        return {}

    def _get_structured_response(self, failed_response: str) -> Dict[str, Any]:
        """Attempt to get structured response after JSON parse failure."""
        retry_prompt = f"""
        The previous response was not valid JSON. Please convert this response into a valid JSON object:
        {failed_response}

        Return ONLY a valid JSON object in this exact structure:
        {{
            "steps": [
                {{
                    "type": "create_file",
                    "file_path": "lib/screens/example_screen.dart",
                    "description": "brief description"
                }}
            ],
            "update_main_dart": {{
                "imports_to_add": [],
                "routes_to_add": {{}},
                "initial_route": null,
                "providers_to_initialize": []
            }},
            "dependencies": []
        }}
        """

        try:
            response = self.client.generate(prompt=retry_prompt)
            return json.loads(response['response'])
        except Exception as e:
            logger.error(f"Failed to get structured response: {e}")
            return {}


    def validate_task_plan(self, task_plan: Dict[str, Any]) -> bool:
        required_keys = ['steps', 'update_main_dart', 'dependencies']
        if not all(key in task_plan for key in required_keys):
            return False
        if not isinstance(task_plan['steps'], list) or not task_plan['steps']:
            return False
        if not isinstance(task_plan['update_main_dart'], dict):
            return False
        if not isinstance(task_plan['dependencies'], list):
            return False
        return True



    def generate_file_content(self, file_path: str, description: str, project_files: Dict[str, str]) -> str:
        existing_content = project_files.get(file_path, "")
        prompt = f"""
        Generate Flutter code for: {file_path}
        EXACT REQUIREMENTS: {description}

        RULES:
        1. Follow requirements EXACTLY as specified
        2. Include ONLY necessary imports
        3. Do NOT use const anywhere
        4. Keep code minimal but complete
        5. No comments unless absolutely necessary
        6. Match file name to class name
        7. For screens: include Scaffold
        8. For main.dart: keep minimal setup

        Current content (if updating):
        ```dart
        {existing_content}
        ```

        Project files: {list(project_files.keys())}

        Return ONLY the Dart code.
        """

        try:
            response = self.client.generate(prompt=prompt)
            code = self.remove_code_markers(response['response'].strip())
            # Add const stripping here
            return strip_const_declarations(code)  # Make sure strip_const_declarations is imported or available
        except Exception as e:
            logger.error(f"Error generating content for {file_path}: {str(e)}")
            return existing_content

    def _clean_generated_code(self, code: str) -> str:
        """
        Clean and minimize generated code.
        """
        # Remove markdown
        code = re.sub(r'```dart\s*', '', code)
        code = re.sub(r'\s*```', '', code)

        # Clean up extra whitespace
        code = re.sub(r'\n{3,}', '\n\n', code)

        # Organize imports
        lines = code.split('\n')
        imports = sorted([l for l in lines if l.strip().startswith('import')])
        other_lines = [l for l in lines if not l.strip().startswith('import')]

        return '\n'.join(imports + [''] + other_lines).strip()

    def update_main_dart(self, main_dart_content: str, updates: Dict[str, Any]) -> str:
        prompt = f"""
        Update the following main.dart file with these changes:
        {json.dumps(updates, indent=2)}

        Current main.dart content:
        ```dart
        {main_dart_content}
        ```

        Provide the updated main.dart content, ensuring all existing functionality is preserved unless explicitly stated otherwise.
        Do not include any markdown code block syntax in the response.
        """

        for attempt in range(self.max_retries):
            try:
                response = self.client.generate(prompt=prompt)
                if isinstance(response, dict) and 'response' in response:
                    return self.remove_code_markers(response['response'])
                elif isinstance(response, str):
                    return self.remove_code_markers(response)
                else:
                    logger.error(f"Unexpected response format: {response}")
            except Exception as e:
                logger.error(f"Error updating main.dart (attempt {attempt + 1}): {str(e)}")

        logger.error(f"Failed to update main.dart after {self.max_retries} attempts. Returning original content.")
        return main_dart_content

    def remove_code_markers(self, content: str) -> str:
        # Remove any potential markdown code block markers
        content = re.sub(r'```dart\s*', '', content)
        content = re.sub(r'\s*```', '', content)
        return content.strip()

    def determine_task_complexity(self, user_input: str) -> str:
        # Simple heuristic for task complexity
        if len(user_input.split()) < 10 and 'create' not in user_input.lower() and 'implement' not in user_input.lower():
            return 'simple'
        return 'complex'

    def robust_json_correction(self, invalid_json: str) -> Dict[str, Any]:
        # Remove any non-JSON content before and after the main JSON structure
        json_match = re.search(r'\{.*\}', invalid_json, re.DOTALL)
        if json_match:
            potential_json = json_match.group(0)
        else:
            logger.error(f"No JSON-like structure found in: {invalid_json}")
            return {}

        # Handle escaped quotes within JSON strings
        potential_json = re.sub(r'(?<!\\)"([^"]*)"', lambda m: '"{}"'.format(m.group(1).replace('"', '\\"')), potential_json)

        # Fix common JSON errors
        potential_json = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', potential_json)  # Add quotes to keys
        potential_json = re.sub(r',\s*([}\]])', r'\1', potential_json)  # Remove trailing commas
        potential_json = potential_json.replace("'", '"')  # Replace single quotes with double quotes

        # Handle unescaped quotes in values
        potential_json = re.sub(r':\s*"([^"]*)"([^,}\]]*)"', r':"\1\2"', potential_json)

        try:
            return json.loads(potential_json)
        except json.JSONDecodeError as e:
            logger.error(f"JSON correction failed: {str(e)}")
            logger.error(f"Problematic JSON: {potential_json}")
            return {}

    def parse_and_validate_tasks(self, response: str) -> Dict[str, Any]:
        try:
            tasks = json.loads(response)
            if isinstance(tasks, dict) and all(key in tasks for key in ['files_to_create_or_update', 'update_main_dart', 'dependencies']):
                return tasks
        except json.JSONDecodeError:
            pass

        logger.error(f"Invalid task plan format:\n{response}")
        return {}

    def fallback_task_extraction(self, response: str) -> List[Dict[str, Any]]:
        logger.info("Attempting fallback task extraction")
        tasks = []
        task_pattern = r'"main_task":\s*"([^"]*)"'
        subtasks_pattern = r'"subtasks":\s*\[(.*?)\]'
        files_pattern = r'"files":\s*\[(.*?)\]'
        code_changes_pattern = r'"code_changes":\s*\[(.*?)\]'
        dependencies_pattern = r'"dependencies":\s*\[(.*?)\]'

        main_tasks = re.findall(task_pattern, response)
        subtasks_lists = re.findall(subtasks_pattern, response, re.DOTALL)
        files_lists = re.findall(files_pattern, response, re.DOTALL)
        code_changes_lists = re.findall(code_changes_pattern, response, re.DOTALL)
        dependencies_lists = re.findall(dependencies_pattern, response, re.DOTALL)

        for i, main_task in enumerate(main_tasks):
            task = {
                "main_task": main_task,
                "subtasks": self.extract_list_items(subtasks_lists[i] if i < len(subtasks_lists) else ""),
                "files": self.extract_list_items(files_lists[i] if i < len(files_lists) else ""),
                "code_changes": self.extract_code_changes(code_changes_lists[i] if i < len(code_changes_lists) else ""),
                "dependencies": self.extract_list_items(dependencies_lists[i] if i < len(dependencies_lists) else "")
            }
            tasks.append(task)

        return tasks

    def extract_list_items(self, list_str: str) -> List[str]:
        return [item.strip().strip('"') for item in list_str.split(',') if item.strip()]

    def extract_code_changes(self, code_changes_str: str) -> List[Dict[str, str]]:
        changes = []
        file_pattern = r'"file":\s*"([^"]*)"'
        changes_pattern = r'"changes":\s*"([^"]*)"'

        files = re.findall(file_pattern, code_changes_str)
        changes_list = re.findall(changes_pattern, code_changes_str)

        for i, file in enumerate(files):
            if i < len(changes_list):
                changes.append({"file": file, "changes": changes_list[i]})

        return changes
    def validate_and_connect_project(self, project_root: str, project_files: Dict[str, str], tasks: List[Dict[str, Any]]):
        self.flutter_validator.validate_and_connect_files(project_root, project_files, tasks)


    def update_or_create_file(self, project_root: str, file_path: str, description: str, project_files: Dict[str, str]):
        full_path = os.path.join(project_root, file_path)
        existing_content = project_files.get(file_path, "")

        prompt = f"""
        Update or create the following Dart file:
        File: {file_path}
        Description: {description}

        Existing content:
        ```dart
        {existing_content}
        ```

        Provide the complete, updated content for this file.
        """

        for attempt in range(self.max_retries):
            try:
                response = self.client.generate(prompt=prompt)
                generated_content = self.flutter_validator.extract_code_from_response(response['response'])

                if self.flutter_validator.validate_dart_code(generated_content):
                    project_files[file_path] = generated_content
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, 'w') as f:
                        f.write(generated_content)
                    logger.info(f"Successfully updated/created: {file_path}")
                    return
                else:
                    logger.warning(f"Generated invalid code for {file_path} (attempt {attempt + 1}). Retrying...")
            except Exception as e:
                logger.warning(f"Error generating code for {file_path} (attempt {attempt + 1}): {str(e)}")

        logger.error(f"Failed to generate valid code for {file_path} after {self.max_retries} attempts.")

    def summarize_file_contents(self, project_files: Dict[str, str]) -> str:
        summary = ""
        for file_path, content in project_files.items():
            summary += f"\nFile: {file_path}\n"
            summary += f"Content (first 500 characters):\n{content[:500]}...\n"
        return summary

    def save_task_history(self, task: Dict[str, Any], project_root: str):
        history_file = os.path.join(project_root, 'task_history.json')
        try:
            with open(history_file, 'r+') as f:
                history = json.load(f)
                history.append(task)
                f.seek(0)
                json.dump(history, f, indent=2)
                f.truncate()
            logger.info(f"Task saved to history: {task['main_task']}")
        except FileNotFoundError:
            with open(history_file, 'w') as f:
                json.dump([task], f, indent=2)
            logger.info(f"Created new task history file with task: {task['main_task']}")
        except json.JSONDecodeError:
            logger.error("Error reading task history. Creating new history.")
            with open(history_file, 'w') as f:
                json.dump([task], f, indent=2)

    def load_task_history(self, project_root: str) -> List[Dict[str, Any]]:
        history_file = os.path.join(project_root, 'task_history.json')
        try:
            with open(history_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("Task history file not found. Returning empty history.")
            return []
        except json.JSONDecodeError:
            logger.error("Error decoding task history. Returning empty history.")
            return []

    def summarize_task_history(self, tasks: List[Dict[str, Any]], max_tasks: int = 5) -> str:
        recent_tasks = tasks[-max_tasks:]
        summary = "Previous tasks:\n"
        for i, task in enumerate(recent_tasks, 1):
            summary += f"{i}. {task['main_task']}\n"
            for subtask in task.get('subtasks', [])[:3]:  # Limit to first 3 subtasks for brevity
                summary += f"   - {subtask}\n"
        return summary

    def summarize_project_structure(self, project_files: Dict[str, str]) -> str:
        summary = "Current project structure:\n"
        for file_path in sorted(project_files.keys()):
            summary += f"- {file_path}\n"
        return summary

    def generate_detailed_tasks(self, prompt: str, project_files: Dict[str, str], project_root: str) -> Dict[str, Any]:
        planning_prompt = self.create_planning_prompt(prompt, project_files)

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Sending request to LLM (attempt {attempt + 1})")
                response = self.client.generate( prompt=planning_prompt)
                logger.info(f"Received response from LLM (attempt {attempt + 1})")
                logger.debug(f"Raw response from LLM (attempt {attempt + 1}):\n{response['response']}")

                tasks = self.parse_and_validate_tasks(response['response'])
                if tasks:
                    return tasks
                else:
                    logger.warning(f"Generated invalid task plan on attempt {attempt + 1}. Retrying...")

            except Exception as e:
                logger.error(f"Error generating tasks (attempt {attempt + 1}): {e}")

        logger.error("Max retries reached. Unable to generate a valid task plan.")
        return {}

    def generate_code(self, task: Dict[str, Any], project_files: Dict[str, str], project_root: str) -> Dict[str, str]:
        generated_updates = {}
        files = task.get('files', [])
        changes = task.get('changes', '')
        print(f"\n--- Generating code for task: {task['main_task']} ---")
        if not files:
            logger.warning(f"No files specified for task: {task.get('main_task', 'Unknown task')}")
            return generated_updates

        for file_path in files:
            try:
                full_path = os.path.join(project_root, file_path)
                existing_content = project_files.get(file_path, "")

                prompt = f"""
                As an expert Flutter developer, implement the following task:

                Task: {task.get('main_task', 'Unknown task')}
                Subtasks: {json.dumps(task.get('subtasks', []))}
                File: {file_path}

                Existing content:
                ```dart
                {existing_content}
                ```

                Changes to make:
                {changes}

                Please provide the complete, updated Dart code for this Flutter file. If it's a new file, provide the full content. If it's an existing file, incorporate the necessary changes while preserving existing functionality.

                Follow these Flutter-specific guidelines:
                1. Use Flutter widgets and material design principles where appropriate.
                2. Implement proper state management techniques (e.g., StatefulWidget, Provider, Riverpod).
                3. Follow Flutter best practices and conventions for code organization.
                4. Use Flutter-specific libraries and plugins when necessary.
                5. Implement error handling and input validation where appropriate.
                6. Ensure the code is null-safe and uses modern Dart features.
                7. Add comments to explain complex logic or widget structures.
                8. Organize imports properly, putting Flutter imports first, then package imports, then relative imports.

                Respond with only the Dart code for the Flutter file, nothing else. Do not include any explanations or comments outside the code.
                Wrap the code with ```dart and ``` markers.
                """

                response = self.client.generate( prompt=prompt)
                updated_content = self.remove_code_markers(response['response'].strip())
                generated_updates[file_path] = updated_content
                logger.info(f"Generated content for file: {file_path}")
                print(f"Generated content for file: {file_path}")
                print(f"Content:\n{updated_content}\n")
            except Exception as e:
                logger.error(f"Error generating code for file {file_path}: {str(e)}")
                print(f"Error generating code for file {file_path}: {str(e)}")

        print("--- Code generation complete ---\n")
        return generated_updates



    def generate_focused_task_plan(self, user_input: str) -> Dict[str, Any]:
        prompt = f"""
        Create a focused task plan for the following Flutter development task:

        {user_input}

        Consider the simplest possible implementation that fulfills the task requirements.
        Only include files and changes that are absolutely necessary.
        If the task can be accomplished by modifying existing files (e.g., main.dart), prefer that over creating new files.
        Only include dependencies if they are absolutely necessary for the task.

        Provide a JSON object with the following structure:
        {{
            "files_to_create_or_update": [
                {{
                    "path": "lib/main.dart",
                    "description": "Detailed description of the changes to be made to this file"
                }}
            ],
            "update_main_dart": {{
                "imports_to_add": [],
                "routes_to_add": {{}},
                "providers_to_add": []
            }},
            "dependencies": []
        }}

        Be specific about the changes to be made, mentioning exact widget names, text to be displayed, and layout modifications.
        If a section is not needed, return an empty list or object for that section.
        Ensure the response is a valid JSON object.
        """

        for attempt in range(self.max_retries):
            try:
                response = self.client.generate(prompt=prompt)
                logger.debug(f"Raw LLM response:\n{response['response']}")
                task_plan = json.loads(self.robust_json_correction(response['response']))
                logger.info(f"Generated task plan: {json.dumps(task_plan, indent=2)}")

                if self.validate_task_plan(task_plan, user_input):
                    return task_plan
                else:
                    logger.warning(f"Generated invalid task plan on attempt {attempt + 1}. Retrying...")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON in attempt {attempt + 1}: {str(e)}")
                logger.error(f"Problematic JSON:\n{response['response']}")
            except Exception as e:
                logger.error(f"Unexpected error in attempt {attempt + 1}: {str(e)}")

        logger.error("Max retries reached. Unable to generate a valid task plan.")
        return {}


    def generate_file_content(self, file_path: str, description: str, project_files: Dict[str, str]) -> str:
        existing_content = project_files.get(file_path, "")
        prompt = f"""
        Generate valid Dart code for a Flutter app for the file {file_path}.
        Description: {description}

        Existing content:
        ```dart
        {existing_content}
        ```

        Ensure to:
        1. Include necessary imports (e.g., 'package:flutter/material.dart')
        2. Extend appropriate classes (e.g., StatelessWidget)
        3. Implement required methods (e.g., build)
        4. Use proper Flutter widgets and syntax

        Existing project files:
        {json.dumps(list(project_files.keys()), indent=2)}

        Provide only the Dart code for the file, without any markdown code block syntax.
        """

        try:
            response = self.client.generate(prompt=prompt)
            return self.remove_code_markers(response['response'].strip())
        except Exception as e:
            logger.error(f"Error generating content for {file_path}: {str(e)}")
            return existing_content

    def update_main_dart(self, main_dart_content: str, updates: Dict[str, Any]) -> str:
        prompt = f"""
        Update the following main.dart file with these changes:
        {json.dumps(updates, indent=2)}

        Current main.dart content:
        ```dart
        {main_dart_content}
        ```

        Provide the updated main.dart content, ensuring all existing functionality is preserved unless explicitly stated otherwise.
        Do not include any markdown code block syntax in the response.
        """

        for attempt in range(self.max_retries):
            try:
                response = self.client.generate(prompt=prompt)
                return self.remove_code_markers(response['response'].strip())
            except Exception as e:
                logger.error(f"Error updating main.dart (attempt {attempt + 1}): {str(e)}")
                if attempt == self.max_retries - 1:
                    logger.error("Max retries reached. Returning original main.dart content.")
                    return main_dart_content

        return main_dart_content

    def update_project_structure(self, project_root: str, generated_updates: Dict[str, str]):
        for file_path, content in generated_updates.items():
            full_path = os.path.join(project_root, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
            logger.info(f"Updated file: {file_path}")

    def update_pubspec_yaml(self, project_root: str, new_dependencies: List[Dict[str, str]]):
        pubspec_path = os.path.join(project_root, 'pubspec.yaml')
        with open(pubspec_path, 'r') as f:
            content = f.read()

        dependencies_section = "dependencies:\n  flutter:\n    sdk: flutter\n"
        for dep in new_dependencies:
            package_name = dep.get('package_name', '')
            version = dep.get('version', '')
            if package_name and version and package_name not in ['flutter', 'dart']:
                dependencies_section += f"  {package_name}: {version}\n"

        content = re.sub(r'dependencies:.*?dev_dependencies:',
                         dependencies_section + '\ndev_dependencies:',
                         content, flags=re.DOTALL)

        with open(pubspec_path, 'w') as f:
            f.write(content)

        logger.info("Updated pubspec.yaml with new dependencies")

    def create_planning_prompt(self, prompt: str, project_files: Dict[str, str]) -> str:
        return f"""
        Create a detailed task plan for the following Flutter development request:

        {prompt}

        Current project structure:
        {json.dumps(list(project_files.keys()), indent=2)}

        Provide a task plan as a JSON object with the following structure:
        {{
            "files_to_create_or_update": [
                {{
                    "path": "path/to/file.dart",
                    "description": "Description of changes or new file content"
                }}
            ],
            "update_main_dart": {{
                "imports_to_add": ["package:flutter/material.dart", "package:your_app/path/to/file.dart"],
                "routes_to_add": {{"/route_name": "WidgetName()"}},
                "providers_to_add": ["ChangeNotifierProvider(create: (_) => SomeProvider())"]
            }},
            "dependencies": ["package_name: ^version"]
        }}

        Ensure your response is valid JSON and nothing else.
        """



    def generate_specific_code(self, task: Dict[str, Any], project_files: Dict[str, str], project_root: str) -> Tuple[List[str], Dict[str, str]]:
        new_directories = []
        generated_updates = {}

        for change in task['code_changes']:
            file_path = change['file']
            code_change = change['changes']

            full_path = os.path.join(project_root, file_path)
            directory = os.path.dirname(full_path)

            if directory not in new_directories and not os.path.exists(directory):
                os.makedirs(directory)
                new_directories.append(directory)

            if file_path in project_files:
                # Update existing file
                current_content = project_files[file_path]
                updated_content = self.apply_code_change(current_content, code_change)
            else:
                # Create new file
                updated_content = code_change

            generated_updates[file_path] = updated_content

        return new_directories, generated_updates

    def apply_code_change(self, current_content: str, code_change: str) -> str:
        prompt = f"""
        Current file content:
        ```dart
        {current_content}
        ```

        Proposed code change:
        ```dart
        {code_change}
        ```

        Please integrate the proposed code change into the current file content.
        Ensure that the changes are applied correctly and the resulting code is valid Dart/Flutter code.
        Return the entire updated file content.
        """

        response = self.client.generate(prompt=prompt)
        return response['response'].strip()

    def validate_task_structure(self, task: Dict[str, Any]) -> Dict[str, Any]:
        validated_task = {
            'main_task': task.get('main_task', ''),
            'subtasks': task.get('subtasks', []),
            'files': task.get('files', []),
            'changes': task.get('changes', ''),
            'dependencies': task.get('dependencies', [])
        }
        return validated_task

    def print_detailed_task_list(self, tasks: List[Dict[str, Any]]):
        logger.info("\nDetailed Task List:")
        for i, task in enumerate(tasks, 1):
            logger.info(f"{i}. {task['main_task']}")
            logger.info("   Subtasks:")
            for subtask in task['subtasks']:
                logger.info(f"   - {subtask}")
            logger.info("   Files:")
            for file in task['files']:
                logger.info(f"   - {file}")
            logger.info("   Dependencies to add:")
            for dep in task['dependencies']:
                if isinstance(dep, dict):
                    logger.info(f"   - {dep['package']} (version: {dep['version']})")
                else:
                    logger.info(f"   - {dep}")
            logger.info("   Code changes:")
            for change in task.get('code_changes', []):
                if isinstance(change, dict) and 'file' in change and 'changes' in change:
                    logger.info(f"   - {change['file']}:")
                    logger.info(f"     ```dart\n{change['changes']}\n     ```")
                else:
                    logger.info(f"   - {change}")
            logger.info("")


    def validate_and_connect_project(self, project_root: str, project_files: Dict[str, str], tasks: List[Dict[str, Any]]):
        try:
            self.flutter_validator.validate_and_connect_files(project_root, project_files, tasks)
        except Exception as e:
            logger.error(f"Error in validate_and_connect_project: {str(e)}")
            print(f"An error occurred while validating and connecting project files: {str(e)}")
            print("The development process will continue, but the project structure may not be optimal.")

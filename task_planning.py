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
        prompt = f"""
        Generate a task plan for the following Flutter development task:

        {user_input}

        Current project files:
        {json.dumps(list(current_project_files.keys()), indent=2)}


        The main.dart file uses a template with:
        - MultiProvider wrapper for state management
        - MaterialApp with initialRoute and named routes
        - Standard Material theme configuration

        Project architecture:
        1. lib/main.dart: Main entry point (using our template structure)
        2. lib/screens/: Contains screen widgets
        3. lib/widgets/: Reusable custom widgets
        4. lib/models/: Data models
        5. lib/providers/: State management providers
        6. lib/services/: Business logic and API calls

        Return a JSON plan that includes:
        1. Steps to create/update/delete files
        2. Main.dart updates (must follow template structure):
           - New imports
           - Route updates
           - Provider initialization
           - Initial route changes (if this is a home/landing screen)
        3. Required dependencies

        JSON structure:
        {{
            "steps": [
                {{
                    "type": "create_file" | "update_file" | "delete_file",
                    "file_path": "path/to/file",
                    "description": "Description of changes to the file. this should be interpreted from the prompt"
                }}
            ],
            "update_main_dart": {{
                "imports_to_add": ["package:flutter/material.dart"],
                "routes_to_add": {{"/route_name": "WidgetName()"}},
                "initial_route": "/route_name",  # If this is meant to be the home screen
                "providers_to_initialize": ["ChangeNotifierProvider(create: (_) => SomeProvider())"]
            }},
            "dependencies": [
                {{
                    "package_name": "package_name",
                    "version": "^version_number"
                }}
            ]
        }}

        IMPORTANT:
        1. Your response must be a valid JSON object
        2. If this is a home/landing screen task, set initial_route accordingly
        3. Ensure routes match created screen names
        4. Follow the template structure for main.dart updates
        """

    # Rest of your function remains the same...
        for attempt in range(self.max_retries):
            try:
                response = self.client.generate(prompt=prompt)
                logger.debug(f"Raw response: {response}")

                if isinstance(response, dict) and 'response' in response:
                    task_plan = self.extract_json(response['response'])
                elif isinstance(response, str):
                    task_plan = self.extract_json(response)
                else:
                    raise ValueError(f"Unexpected response type: {type(response)}")

                if task_plan and self.validate_task_plan(task_plan):
                    return task_plan
                else:
                    logger.warning(f"Generated invalid task plan on attempt {attempt + 1}. Retrying...")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error on attempt {attempt + 1}: {str(e)}")
            except Exception as e:
                logger.error(f"Error in generate_task_plan (attempt {attempt + 1}): {str(e)}")

        raise ValueError("Failed to generate a valid task plan after maximum retries.")

    def extract_json(self, text: str) -> Dict[str, Any]:
        # Try to find JSON-like structure in the text
        try:
            # First, try to parse the entire text as JSON
            return json.loads(text)
        except json.JSONDecodeError:
            # If that fails, try to find a JSON object within the text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    logger.error("Found JSON-like structure, but failed to parse it.")
            else:
                logger.error("No valid JSON structure found in the response.")
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

        Provide only the Dart code for the file, without any markdown code block syntax.
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
                logger.error(f"Error generating content for {file_path} (attempt {attempt + 1}): {str(e)}")

        logger.error(f"Failed to generate content for {file_path} after {self.max_retries} attempts.")
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

    def generate_specific_code(self, task: Dict[str, Any], project_files: Dict[str, str], project_root: str) -> Tuple[List[str], Dict[str, str]]:
        logger.info(f"Generating code for task: {task['main_task']}")
        new_directories = []
        generated_updates = {}

        for file_path in task['files']:
            full_path = os.path.join(project_root, file_path)
            directory = os.path.dirname(full_path)

            if directory not in new_directories and not os.path.exists(directory):
                os.makedirs(directory)
                new_directories.append(directory)

            existing_content = project_files.get(file_path, "")

            prompt = f"""
            Task: {task['main_task']}
            Subtasks: {json.dumps(task['subtasks'])}
            File: {file_path}

            Existing content:
            ```dart
            {existing_content}
            ```

            Changes to make:
            {task['changes']}

            Please provide the complete, updated content for this file. If it's a new file, provide the full content. If it's an existing file, incorporate the necessary changes while preserving existing functionality.

            Respond with only the file content, nothing else.
            """

            response = self.client.generate(prompt=prompt)
            updated_content = response['response'].strip()

            if updated_content:
                generated_updates[file_path] = updated_content
                logger.info(f"Generated content for file: {file_path}")
            else:
                logger.warning(f"No content generated for file: {file_path}")

        return new_directories, generated_updates

    def apply_code_change(self, current_content: str, code_change: str) -> str:
        prompt = f"""
        Current file content:
        ```dart
        {current_content}
        ```

        Proposed code change:
        {code_change}

        Please integrate the proposed code change into the current file content.
        Ensure that the changes are applied correctly and the resulting code is valid Dart/Flutter code.
        Return the entire updated file content.
        """

        response = self.client.generate(prompt=prompt)
        return response['response'].strip()


    def validate_and_connect_project(self, project_root: str, project_files: Dict[str, str], tasks: List[Dict[str, Any]]):
        try:
            self.flutter_validator.validate_and_connect_files(project_root, project_files, tasks)
        except Exception as e:
            logger.error(f"Error in validate_and_connect_project: {str(e)}")
            print(f"An error occurred while validating and connecting project files: {str(e)}")
            print("The development process will continue, but the project structure may not be optimal.")

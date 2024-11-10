import json
import time
import os
import subprocess
from typing import Dict, List, Optional, Tuple, Any
from project_context_manager import ProjectContextManager
from ai_client import AIClient

MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_CONTEXT_LENGTH = 100000

def generate_code(client: AIClient, task: Dict[str, Any], project_context_manager: ProjectContextManager) -> Tuple[List[str], Dict[str, str]]:
    print(f"\nInitiating code generation for task: {task['main_task']}")
    print(f"\n--- Generating code for task: {task['main_task']} ---")
    generated_updates = {}
    new_directories = set()
    context_prompt = project_context_manager.get_context_prompt()

    for file_path in task['files']:
        full_path = os.path.join(project_context_manager.project_root, file_path)
        existing_content = project_context_manager.file_contents.get(file_path, "")

        prompt = f"""
        Task: {task['main_task']}
        Subtasks: {json.dumps(task['subtasks'])}
        File to update: {file_path}

        Project Context:
        {context_prompt}

        Existing content of {file_path}:
        {existing_content}

        Generate valid Dart code for the file {file_path}, taking into account the existing project structure and file contents.
        Ensure that the generated code is compatible with the rest of the project and maintains all existing functionality.
        If you need to update other files to maintain consistency, please indicate those changes as well.

        Provide the complete, updated content for this file. If it's a new file, provide the full content. If it's an existing file, incorporate the necessary changes while preserving existing functionality.

        Respond with only the file content, nothing else.
        """

        response = client.generate( prompt=prompt)
        updated_content = clean_dart_code(response['response'].strip())

        if updated_content:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(updated_content)
            generated_updates[file_path] = updated_content
            new_directories.add(os.path.dirname(file_path))
            print(f"Generated and wrote {'new' if not existing_content else 'updated'} file: {file_path}")
        else:
            print(f"No changes generated for {file_path}")

    ensure_correct_structure(client, project_context_manager.file_contents, project_context_manager.project_root)
    project_context_manager.update_context()  # Update the context after changes
    return list(new_directories), generated_updates

def apply_code_changes(client: AIClient, new_directories: List[str], generated_updates: Dict[str, str], project_files: Dict[str, str], project_root: str, flutter_process: Optional[subprocess.Popen] = None):
    # This function is now redundant as we're writing files directly in generate_code
    # We'll keep it for compatibility, but it won't do much
    for file_path, content in generated_updates.items():
        project_files[file_path] = content

    if flutter_process:
        hot_reload_success = hot_reload(flutter_process)
        if not hot_reload_success:
            print("Hot reload failed. Manual intervention may be required.")
        else:
            print("Hot reload successful.")
    else:
        print("Flutter process not available. Skipping hot reload.")


def run_dart_analyzer(code: str) -> Tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False) as temp_file:
        temp_file.write(code)
        temp_file.flush()

        try:
            result = subprocess.run(['dart', 'analyze', temp_file.name], capture_output=True, text=True)
            is_valid = result.returncode == 0
            return is_valid, result.stdout + result.stderr
        finally:
            os.unlink(temp_file.name)

def fix_linting_errors(client: AIClient, original_code: str, linting_errors: str) -> str:
    prompt = f"""
    The following Dart code has linting errors:

    ```dart
    {original_code}
    ```

    Linting errors:
    {linting_errors}

    Please fix the linting errors in the code. Maintain the original structure and functionality of the code, only addressing the specific linting issues mentioned.
    Provide the corrected code, ensuring it's valid Dart syntax and likely to pass the linter check.
    """

    response = client.generate( prompt=prompt)
    return response['response'].strip()

def generate_and_lint_code(client: AIClient, task: Dict[str, Any], project_files: Dict[str, str], project_root: str) -> Tuple[List[str], Dict[str, str]]:
    new_directories = []
    generated_updates = {}

    for change in task['code_changes']:
        file_path = change['file']
        code_change = change['changes']

        full_path = os.path.join(project_root, file_path.lstrip('/'))
        directory = os.path.dirname(full_path)

        if directory not in new_directories and not os.path.exists(directory):
            os.makedirs(directory)
            new_directories.append(directory)

        if file_path in project_files:
            # Update existing file
            current_content = project_files[file_path]
            updated_content = intelligent_code_merge(client, current_content, code_change, file_path)
        else:
            # Create new file
            updated_content = code_change

        # Run Dart analyzer
        is_valid, linting_output = run_dart_analyzer(updated_content)

        if not is_valid:
            print(f"Linting errors found in {file_path}. Attempting to fix...")
            corrected_content = fix_linting_errors(client, updated_content, linting_output)

            # Verify the corrected code
            is_valid, linting_output = run_dart_analyzer(corrected_content)

            if is_valid:
                print(f"Linting errors in {file_path} successfully fixed.")
                updated_content = corrected_content
            else:
                print(f"Warning: Linting errors in {file_path} could not be fully resolved.")

        generated_updates[file_path] = updated_content
        print(f"Generated/Updated file: {file_path}")

    return new_directories, generated_updates


def intelligent_code_merge(client: 'AIClient', current_content: str, new_code: str, file_path: str) -> str:
    merge_prompt = f"""
    You are an expert Flutter developer. Your task is to intelligently merge the following new code into the existing file content.
    Avoid duplicating functionality or overwriting necessary code. Ensure the resulting code is valid Dart/Flutter code.

    Existing file ({file_path}):
    ```dart
    {current_content}
    ```

    New code to be merged:
    ```dart
    {new_code}
    ```

    Please provide the merged code, ensuring all functionality is preserved and no unnecessary duplication occurs.
    If any conflicts arise, resolve them in favor of maintaining existing functionality while integrating new features.
    """

    response = client.generate( prompt=merge_prompt)
    return response['response'].strip()

def apply_code_change(client: 'AIClient', current_content: str, code_change: str) -> str:
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
    If the current content is empty, use the proposed change as the entire content.
    Ensure that the changes are applied correctly and the resulting code is valid Dart/Flutter code.
    Return the entire updated file content.
    """

    response = client.generate( prompt=prompt)
    return response['response'].strip()

def create_decision_tree(client: AIClient, task: Dict[str, Any], project_files: Dict[str, str]) -> Dict[str, Any]:
    prompt = f"""
    Based on the following task and the current project structure, create a decision tree for updating the Flutter project:

    Task: {json.dumps(task)}
    Project Structure: {json.dumps({k: v for k, v in project_files.items()})}

    Provide a JSON object representing the decision tree. Each node should have:
    1. "action": The action to take (e.g., "create_file", "update_file", "check_condition")
    2. "file_path": The path of the file to create or update (if applicable)
    3. "condition": A condition to check (for "check_condition" actions)
    4. "true_branch": The next action if the condition is true
    5. "false_branch": The next action if the condition is false
    6. "content_prompt": A prompt to generate content for the file (for create or update actions)

    Ensure the decision tree covers all necessary file operations and checks for the given task.
    """

    response = client.generate( prompt=prompt)
    return json.loads(response['response'])

def execute_decision_tree(client: AIClient, decision_tree: Dict[str, Any], project_files: Dict[str, str], project_root: str) -> Tuple[List[str], Dict[str, str]]:
    new_directories = set()
    generated_updates = {}

    current_node = decision_tree
    while current_node:
        if current_node['action'] == 'create_file':
            file_path, content = create_file(client, current_node['file_path'], current_node['content_prompt'], project_root)
            generated_updates[file_path] = content
            new_directories.add(os.path.dirname(file_path))
            current_node = current_node.get('next')
        elif current_node['action'] == 'update_file':
            file_path, content = update_file(client, current_node['file_path'], current_node['content_prompt'], project_files, project_root)
            generated_updates[file_path] = content
            current_node = current_node.get('next')
        elif current_node['action'] == 'check_condition':
            condition_met = check_condition(client, current_node['condition'], project_files)
            current_node = current_node['true_branch'] if condition_met else current_node['false_branch']
        else:
            break

    return list(new_directories), generated_updates

def create_file(client: AIClient, file_path: str, content_prompt: str, project_root: str) -> Tuple[str, str]:
    full_path = os.path.join(project_root, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    content = generate_content(client, content_prompt)
    with open(full_path, 'w') as f:
        f.write(content)
    print(f"Created file: {file_path}")
    return file_path, content

def update_file(client: AIClient, file_path: str, content_prompt: str, project_files: Dict[str, str], project_root: str) -> Tuple[str, str]:
    full_path = os.path.join(project_root, file_path)
    existing_content = project_files.get(file_path, "")
    updated_content = generate_content(client, content_prompt, existing_content)
    with open(full_path, 'w') as f:
        f.write(updated_content)
    print(f"Updated file: {file_path}")
    return file_path, updated_content

def check_condition(client: AIClient, condition: str, project_files: Dict[str, str]) -> bool:
    prompt = f"""
    Check the following condition based on the current project structure:
    {condition}

    Project Structure: {json.dumps({k: v for k, v in project_files.items()})}

    Respond with a JSON object containing a single key "result" with a boolean value.
    """
    response = client.generate( prompt=prompt)
    return json.loads(response['response'])['result']

def generate_content(client: AIClient, prompt: str, existing_content: str = "") -> str:
    full_prompt = f"""
    {prompt}

    Existing content:
    {existing_content}

    Provide the complete, updated Dart code for the file, ensuring all existing functionality is preserved unless explicitly stated otherwise.
    """
    response = client.generate( prompt=full_prompt)
    return response['response'].strip()

def analyze_project_structure(client: AIClient, task: Dict[str, Any], project_files: Dict[str, str]) -> List[str]:
    file_list = "\n".join(project_files.keys())
    prompt = f"""
    Task: {task['main_task']}
    Subtasks: {json.dumps(task['subtasks'], indent=2)}

    Current project structure:
    {file_list}

    Analyze the project structure and determine which files are relevant to the given task.
    Consider the following:
    1. Files that need to be modified to implement the task.
    2. New files that need to be created for the task.
    3. Existing files that may be affected by the changes.

    Return a JSON array of file paths that need to be updated or created.
    Ensure that the response is a valid JSON array and nothing else.
    """

    try:
        response = client.generate( prompt=prompt)
        print("Raw response from LLM:")
        print(response['response'])

        parsed_response = parse_json_response(response['response'])

        # Attempt to extract the relevant files from the parsed response
        if isinstance(parsed_response.get('code'), list):
            relevant_files = parsed_response['code']
        elif isinstance(parsed_response.get('code'), str):
            # If 'code' is a string, try to parse it as JSON
            try:
                relevant_files = json.loads(parsed_response['code'])
            except json.JSONDecodeError:
                # If parsing fails, split the string into lines
                relevant_files = [line.strip() for line in parsed_response['code'].split('\n') if line.strip()]
        else:
            raise ValueError("Unexpected format in parsed response")

        if not isinstance(relevant_files, list):
            raise ValueError("Parsed result is not a list")

        print(f"Relevant files for the task: {relevant_files}")
        return relevant_files
    except Exception as e:
        print(f"Error analyzing project structure: {str(e)}")
        print("Falling back to task-provided files.")
        return task.get('files', [])

def check_consistency(client: AIClient, generated_updates: Dict[str, str]) -> Dict[str, str]:
    prompt = f"""
    Review the following generated files for consistency and remove any duplications:

    {json.dumps(generated_updates, indent=2)}

    Respond with a JSON object where keys are file paths and values are the updated, consistent file contents.
    """

    try:
        response = client.generate( prompt=prompt)
        json_string = response['response'].strip()
        return json.loads(json_string)
    except Exception as e:
        print(f"Error checking consistency: {e}")
        return generated_updates

def generate_code_for_file(client: AIClient, task: Dict[str, Any], file_path: str, existing_content: str) -> Tuple[str, str]:
    print(f"Generating code for file: {file_path}")
    prompt = f"""
    Task: {task['main_task']}
    Subtasks:
    {json.dumps(task['subtasks'], indent=2)}

    File: {file_path}

    Current file content:
    ```dart
    {existing_content}
    ```

    Update the content of this file to accomplish the task and subtasks. Provide the complete, updated file content.
    If adding new code, determine the best place to insert it within the existing structure.
    IMPORTANT: Ensure all existing functionality is preserved unless explicitly stated otherwise in the task.
    If you believe any existing code should be removed, explain why in a comment.

    Follow these guidelines:
    1. For main.dart: Initialize providers and set up routes.
    2. For screens: Create user interface components.
    3. For providers: Implement state management using the provider pattern.
    4. For services: Implement business logic and API calls.
    5. For models: Implement models required

    Respond with the updated code wrapped in triple backticks (```), followed by a brief summary of the changes made and why.
    Do not include the word 'dart' before the opening backticks.
    """

    try:
        response = client.generate( prompt=prompt)
        print(f"\nRaw LLM response for {file_path}:")
        print(response['response'])
        print("\nAttempting to parse response:")
        generated_code = parse_json_response(response['response'])

        if generated_code['code']:
            # Remove any leading 'dart' before the code
            code = generated_code['code'].lstrip('dart').strip()
            return code, generated_code['summary']
        else:
            print(f"No code generated for {file_path}")
            return "", ""
    except Exception as e:
        print(f"Error generating code for file {file_path}: {e}")
        return "", ""


def clean_dart_code(code: str) -> str:
    # Remove ```dart and ``` markers
    code = code.replace("```dart", "").replace("```", "")

    # Trim leading and trailing whitespace
    code = code.strip()

    # Validate Dart code (you may want to add more sophisticated validation)
    if not code.startswith("import") and not code.startswith("//") and not code.startswith("class"):
        print("Warning: Generated code may not be valid Dart. Please review.")

    return code


def parse_json_response(response: str) -> Dict[str, Any]:
    print("Raw response:")
    print(response)

    # Try to parse as JSON first
    try:
        parsed = json.loads(response)
        if isinstance(parsed, dict):
            return {
                "code": parsed.get("code", ""),
                "summary": json.dumps(parsed.get("summary", ""))
            }
        elif isinstance(parsed, list):
            return {"tasks": parsed}
    except json.JSONDecodeError:
        pass

    # If JSON parsing fails, try to extract code and summary manually
    code_start = response.find('```') + 3
    code_end = response.rfind('```')
    if code_start != -1 and code_end != -1:
        code = response[code_start:code_end].strip()
    else:
        # If no code block found, assume the entire response is code
        code = response.strip()

    # Extract summary (everything after the last ```)
    summary_start = response.rfind('```') + 3
    summary = response[summary_start:].strip()

    if not summary:
        # If no summary found, use everything before the first ``` as summary
        summary_end = response.find('```')
        summary = response[:summary_end].strip() if summary_end != -1 else ""

    # If we couldn't parse JSON or extract code/summary, try to correct the JSON
    if not code and not summary:
        try:
            corrected_json = correct_json(response)
            return json.loads(corrected_json)
        except Exception as e:
            print(f"Error correcting JSON: {e}")
            return {}

    return {
        "code": code,
        "summary": summary
    }



def correct_code(client: AIClient, error_message: str, file_path: str, current_content: str) -> Optional[str]:
    prompt = f"""
    The following code in {file_path} produced an error:

    {current_content}

    Error message:
    {error_message}

    Please provide a corrected version of the code that resolves this error.
    Respond with the corrected Dart code wrapped in triple backticks (```).
    Do not include the word 'dart' before the opening backticks.
    """

    try:
        response = client.generate( prompt=prompt)
        generated_code = parse_json_response(response['response'])
        return generated_code.get("code", "").lstrip('dart').strip()
    except Exception as e:
        print(f"Error generating corrected code: {e}")
        return None

def correct_json(invalid_json: str) -> str:
    correction_prompt = f"""
    The following text is supposed to be a JSON object or array, but it has some errors:

    ```
    {invalid_json}
    ```

    Please correct the errors and provide the valid JSON. Ensure the output is only the corrected JSON and nothing else.
    """

    try:
        client = AIClient()
        response = client.generate( prompt=correction_prompt)
        return response['response'].strip()
    except Exception as e:
        print(f"Error correcting JSON: {e}")
        return "{}"  # Return empty object if all else fails

def store_summary(file_path: str, summary: str):
    with open('code_summaries.txt', 'a') as f:
        f.write(f"File: {file_path}\n")
        f.write(f"Summary: {summary}\n")
        f.write("-" * 50 + "\n")

def preprocess_code(code: str) -> str:
    # Remove ```dart and ``` if present
    code = code.replace("```dart", "").replace("```", "")
    return code.strip()

def determine_new_files(client: AIClient, task: str, project_files: Dict[str, str]) -> Tuple[List[str], List[str]]:
    print(f"Determining new files and directories needed for task: {task}")
    file_list = "\n".join(project_files.keys())
    prompt = f"""
    Task: {task}

    Current project files:
    {file_list}

    Based on the task, determine any new files and directories that need to be created.
    Consider the Flutter app structure with screens, providers, and services.

    Respond with a JSON object containing two arrays:
    1. "directories": An array of directory paths to be created.
    2. "files": An array of file paths to be created.

    Example response:
    {{
        "directories": [
            "lib/screens",
            "lib/providers",
            "lib/services"
        ],
        "files": [
            "lib/screens/home_screen.dart",
            "lib/providers/todo_provider.dart",
            "lib/services/todo_service.dart"
        ]
    }}
    """

    try:
        response = client.generate( prompt=prompt)
        json_string = response['response'].strip()
        if json_string.startswith('```json'):
            json_string = json_string[7:-3]  # Remove ```json and ```
        result = json.loads(json_string)

        new_directories = [os.path.normpath(dir_path) for dir_path in result.get("directories", [])]
        new_files = [os.path.normpath(file_path) for file_path in result.get("files", [])]

        print(f"New directories: {new_directories}")
        print(f"New files: {new_files}")

        return new_directories, new_files
    except Exception as e:
        print(f"Error determining new files and directories: {e}")
        print(f"Full response: {response['response']}")
        return [], []

def parse_json_response_list(response: str) -> List[str]:
    """
    Parse the JSON response, handling potential formatting issues.
    """
    response = response.strip()
    if response.startswith('```json'):
        response = response[7:]
    if response.endswith('```'):
        response = response[:-3]

    try:
        parsed = json.loads(response)
        if isinstance(parsed, list):
            return [f.strip() for f in parsed if f.strip()]
        else:
            print("Error: Parsed response is not a list.")
            return []
    except json.JSONDecodeError:
        print("Error: Failed to parse JSON response.")
        paths = [line.strip() for line in response.split('\n') if line.strip().startswith('/')]
        return paths

def check_existing_files(client: AIClient, task: str, project_files: Dict[str, str]) -> List[str]:
    print(f"Checking existing files for task: {task}")
    file_list = "\n".join(project_files.keys())
    prompt = f"""
    Task: {task}

    Current project files:
    {file_list}

    Based on the task and the current project structure, which existing files (if any) need to be updated?
    Always include 'lib/main.dart' in the list.

    Respond with a JSON array of file paths.
    """

    try:
        response = client.generate( prompt=prompt)
        json_string = response['response'].strip()
        if json_string.startswith('```json'):
            json_string = json_string[7:-3]  # Remove ```json and ```
        files_to_update = json.loads(json_string)
        if 'lib/main.dart' not in files_to_update:
            files_to_update.append('lib/main.dart')
        return files_to_update
    except Exception as e:
        print(f"Error checking existing files: {e}")
        return ['lib/main.dart']

def validate_file_structure(client: AIClient, file_path: str, file_content: str) -> str:
    prompt = f"""
    Validate and correct the structure of the following Dart file:

    File: {file_path}

    Content:
    ```dart
    {file_content}
    ```

    Ensure the file follows proper Dart and Flutter conventions:
    1. Correct import statements at the top.
    2. Proper class definitions.
    3. Correct widget structure for Flutter files.
    4. Proper use of Provider if applicable.

    Respond with a JSON object containing a single key "code" with the corrected Dart code as its value.
    """

    try:
        response = client.generate( prompt=prompt)
        json_string = response['response'].strip()
        validated_code = json.loads(json_string)
        return validated_code.get("code", file_content)
    except Exception as e:
        print(f"Error validating file structure for {file_path}: {e}")
        return file_content
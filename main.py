import os
import subprocess
import time
from typing import Dict, List, Tuple, Optional, Any, Set
import json
import ollama
from project_management import select_or_create_project, get_project_structure
from flutter_integration import check_flutter_installation, enable_flutter_web_support, get_available_devices, run_flutter_app, hot_reload, full_restart
from code_generation import generate_code, validate_file_structure, apply_code_changes
from error_handling import update_project_files
from utils import run_command
from task_planning import TaskPlanner
from ensure_structure_correct import ensure_correct_structure
import logging
import pickle
import traceback
from ensure_structure_correct import ensure_correct_structure, validate_dart_code, fix_dart_code
from project_context_manager import ProjectContextManager
from flutter_project_validator import FlutterProjectValidator
from ai_client import AIClient
from config import SKIP_DART_ANALYSIS, USE_GEMINI_API, USE_DART_VALIDATOR


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def save_project_state(project_files: Dict[str, str], project_root: str):
    state_file = os.path.join(project_root, '.flutter_bot_state')
    with open(state_file, 'wb') as f:
        pickle.dump(project_files, f)
    print("Project state saved.")

def load_project_state(project_root: str) -> Dict[str, str]:
    state_file = os.path.join(project_root, '.flutter_bot_state')
    if os.path.exists(state_file):
        with open(state_file, 'rb') as f:
            return pickle.load(f)
    return {}

def ensure_directory_exists(file_path: str):
    directory = os.path.dirname(file_path)
    os.makedirs(directory, exist_ok=True)

def safe_validate_dart_code(flutter_validator, content: str, file_path: str) -> str:
    logger.info(f"\n--- Validating Dart code for {file_path} ---")
    if flutter_validator is None:
        logger.info("Dart validation is disabled, returning original content")
        return content
    try:
        validated_content = flutter_validator.validate_and_fix_dart_code(content, file_path)
        logger.info("Validation completed successfully")
        return validated_content
    except Exception as e:
        logger.error(f"Error during validation: {str(e)}")
        logger.info("Returning original content due to validation error")
        return content

def apply_code_changes(client: ollama.Client, new_directories: List[str], generated_updates: Dict[str, str], project_files: Dict[str, str], project_root: str, flutter_process: Optional[subprocess.Popen] = None):
    for dir_path in new_directories:
        full_dir_path = os.path.join(project_root, dir_path)
        os.makedirs(full_dir_path, exist_ok=True)
        print(f"Created directory: {dir_path}")

    for file_path, updated_content in generated_updates.items():
        full_path = os.path.join(project_root, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Validate and correct file structure
        validated_content = validate_file_structure(client, file_path, updated_content)

        with open(full_path, 'w') as f:
            f.write(validated_content)
        project_files[file_path] = validated_content
        print(f"Updated file: {file_path}")

    if flutter_process:
        hot_reload_success = hot_reload(flutter_process)
        if not hot_reload_success:
            print("Hot reload failed. Checking for errors...")
            error_message = check_for_errors(flutter_process)
            if error_message:
                print(f"Error detected: {error_message}")
                corrected_code = correct_code(client, error_message, file_path, validated_content)
                if corrected_code:
                    print("Applying corrected code...")
                    with open(full_path, 'w') as f:
                        f.write(corrected_code)
                    project_files[file_path] = corrected_code
                    print(f"Updated file with corrected code: {file_path}")
                    hot_reload(flutter_process)
                else:
                    print("Failed to correct the code. Manual intervention may be required.")
            else:
                print("No specific error detected. Manual intervention may be required.")
        else:
            print("Hot reload successful.")
    else:
        print("Flutter process not available. Skipping hot reload.")

def check_for_errors(flutter_process: subprocess.Popen) -> Optional[str]:
    time.sleep(2)  # Wait for potential error messages
    if flutter_process.poll() is not None:
        return "Flutter process terminated unexpectedly."

    try:
        error_output = flutter_process.stderr.read()
        if error_output:
            return error_output.decode('utf-8')
    except Exception as e:
        return f"Error checking for errors: {str(e)}"

    return None

def correct_code(client: ollama.Client, error_message: str, file_path: str, current_content: str) -> Optional[str]:
    prompt = f"""
    The following code in {file_path} produced an error:

    {current_content}

    Error message:
    {error_message}

    Please provide a corrected version of the code that resolves this error.
    Respond with a JSON object containing a single key "code" with the corrected Dart code as its value.
    """

    try:
        response = client.generate(prompt=prompt)
        generated_code = json.loads(response['response'])
        return generated_code.get("code")
    except Exception as e:
        print(f"Error generating corrected code: {e}")
        return None

def check_and_add_dependencies(project_root: str, generated_updates: Dict[str, str], installed_packages: Set[str]) -> List[str]:
    new_dependencies = set()

    for file_content in generated_updates.values():
        imports = [line.split()[1].strip("';") for line in file_content.split('\n') if line.strip().startswith('import "package:')]
        new_dependencies.update(import_path.split('/')[0] for import_path in imports if import_path.split('/')[0] not in installed_packages and import_path.split('/')[0] not in ['flutter', 'dart'])

    for dependency in new_dependencies:
        if dependency not in installed_packages:
            logger.info(f"Adding new dependency: {dependency}")
            try:
                subprocess.run(['flutter', 'pub', 'add', dependency], cwd=project_root, check=True)
                installed_packages.add(dependency)
                logger.info(f"Successfully added {dependency}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to add package {dependency}. Error: {e}")

    if new_dependencies:
        logger.info("Running flutter pub get...")
        try:
            subprocess.run(['flutter', 'pub', 'get'], cwd=project_root, check=True)
            logger.info("Successfully ran flutter pub get")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to run flutter pub get. Error: {e}")
    return list(new_dependencies)

def development_loop(client: AIClient, project_root: str, flutter_process: subprocess.Popen, selected_device: str):
    task_planner = TaskPlanner(client)
    project_context_manager = ProjectContextManager(project_root)

    logger.info(f"USE_DART_VALIDATOR setting: {USE_DART_VALIDATOR}")
    flutter_validator = FlutterProjectValidator(client) if USE_DART_VALIDATOR else None
    logger.info(f"Flutter validator initialized: {'Yes' if flutter_validator else 'No'}")

    while True:
        user_input = input("\nEnter your Flutter development task (or 'exit' to quit): ")
        logger.info(f"User input: {user_input}")

        if user_input.lower() == 'exit':
            logger.info("User chose to exit. Terminating development loop.")
            print("Thank you for using the Flutter LLM Assistant. Goodbye!")
            if flutter_process:
                flutter_process.terminate()
            break

        try:
            task_plan = task_planner.generate_task_plan(user_input, project_context_manager.file_contents)
            logger.info(f"Generated task plan: {json.dumps(task_plan, indent=2)}")
            print(f"Task plan: {json.dumps(task_plan, indent=2)}")

            if not task_plan or 'steps' not in task_plan:
                logger.error("Invalid task plan generated. Attempting to generate a simplified plan...")
                task_plan = task_planner.generate_simplified_task_plan(user_input, project_context_manager.file_contents)
                if not task_plan or 'steps' not in task_plan:
                    logger.error("Failed to generate a valid task plan.")
                    print("I'm having trouble understanding the task. Could you please rephrase it or provide more details?")
                    continue
                else:
                    print("A simplified task plan has been generated. Some complex features may be omitted.")

            for step in task_plan['steps']:
                file_path = step['file_path']
                if step['type'] in ['create_file', 'update_file']:
                    content = task_planner.generate_file_content(file_path, step['description'], project_context_manager.file_contents)
                    if SKIP_DART_ANALYSIS:
                        validated_content = content
                    else:
                        validated_content = flutter_validator.validate_and_fix_dart_code(content, file_path)

                    if file_path in project_context_manager.file_contents:
                        integrity_check = flutter_validator.verify_code_integrity(
                            project_context_manager.file_contents[file_path],
                            validated_content,
                            file_path
                        )
                        if not integrity_check['integrity_maintained']:
                            logger.warning(f"Code integrity issue in {file_path}: {integrity_check['explanation']}")
                            print(f"Warning: Potential code integrity issue in {file_path}. Please review the changes.")

                    project_context_manager.update_file(file_path, validated_content)
                    logger.info(f"{'Created' if step['type'] == 'create_file' else 'Updated'} file: {file_path}")
                elif step['type'] == 'delete_file':
                    project_context_manager.delete_file(file_path)
                    logger.info(f"Deleted file: {file_path}")

            # Handle main.dart updates
            if 'update_main_dart' in task_plan:
                main_dart_updates = task_plan['update_main_dart']
                main_dart_content = project_context_manager.get_file_content('lib/main.dart')
                updated_main_dart = task_planner.update_main_dart(main_dart_content, main_dart_updates)
                validated_main_dart = safe_validate_dart_code(
                    flutter_validator,
                    updated_main_dart,
                    'lib/main.dart'
                )
                project_context_manager.update_file('lib/main.dart', validated_main_dart)
                logger.info("Updated main.dart")

            # Handle dependencies
            if task_plan.get('dependencies'):
                task_planner.update_pubspec_yaml(project_root, task_plan['dependencies'])
                logger.info("Updated pubspec.yaml with new dependencies")
                print("Running 'flutter pub get' to fetch new dependencies...")
                subprocess.run(['flutter', 'pub', 'get'], cwd=project_root, check=True)

            # Ensure correct project structure
#             ensure_correct_structure(client, project_context_manager.file_contents, project_root)

            # Run or hot-reload the Flutter app
            if not flutter_process:
                logger.info("Flutter process is not running. Starting the app...")
                flutter_process = run_flutter_app(selected_device, client, project_context_manager.file_contents, project_root)
            else:
                logger.info("Triggering hot reload...")
                hot_reload_success = hot_reload(flutter_process)
                if not hot_reload_success:
                    logger.warning("Hot reload failed. Attempting to restart the app...")
                    flutter_process = run_flutter_app(selected_device, client, project_context_manager.file_contents, project_root)

            logger.info("All tasks completed.")
            print("\nAll tasks completed. You can now test the app or provide another development request.")

        except subprocess.CalledProcessError as e:
            logger.error(f"Error running Flutter command: {str(e)}")
            print(f"An error occurred while running a Flutter command: {str(e)}")
        except ValueError as ve:
            logger.error(f"Error in task planning: {str(ve)}")
            print(f"An error occurred while planning the task: {str(ve)}")
            print("Please try rephrasing your request or providing more details.")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
            print(f"An unexpected error occurred: {str(e)}")
            print("Please try again or seek manual intervention if the issue persists.")

    logger.info("Development loop ended.")
    print("Development loop ended.")

def execute_recovery_plan(recovery_plan: Dict[str, Any], project_context_manager: ProjectContextManager, flutter_validator: FlutterProjectValidator):
    for step in recovery_plan.get('steps', []):
        if step['type'] == 'revert_file':
            project_context_manager.revert_file(step['file_path'])
        elif step['type'] == 'fix_file':
            content = project_context_manager.get_file_content(step['file_path'])
            fixed_content = flutter_validator.fix_dart_code(content, step['file_path'])
            project_context_manager.update_file(step['file_path'], fixed_content)
    logger.info("Executed recovery plan")
    print("Recovery actions have been applied. Please check the app state and provide further instructions if needed.")


def generate_task_summary(client: ollama.Client, user_input: str) -> str:
    prompt = f"""
    Provide a brief, informative summary of the following Flutter development task:

    {user_input}

    Your summary should be one or two sentences long and capture the main objective of the task.
    """

    try:
        response = client.generate(prompt=prompt)
        return response['response'].strip()
    except Exception as e:
        logger.error(f"Error generating task summary: {e}", exc_info=True)
        return "Unable to generate summary."

def main():
    print("Welcome to the Flutter LLM Assistant!")
    print("This script will help you develop your Flutter app using AI-generated code.")

    if not check_flutter_installation():
        print("Flutter is not installed or not in PATH. Please install Flutter and try again.")
        return

    enable_flutter_web_support()

    # Create AIClient
    print("Initializing AI client...")
    client = AIClient()
    print("AI client initialized.")


    project_root = select_or_create_project()
    if not project_root:
        print("Failed to select or create a project. Exiting.")
        return

    # Ensure project_root is an absolute path
    project_root = os.path.abspath(project_root)

    if not os.path.isdir(project_root):
        print(f"Error: Project root directory '{project_root}' does not exist. Exiting.")
        return

    print(f"\nProject selected/created successfully at: {project_root}")

    # Get available devices
    devices, default_device = get_available_devices()
    if not devices:
        print("No devices found. Please ensure you have a device or simulator available.")
        return

    if default_device:
        print(f"Only Chrome is available. Automatically selecting Chrome.")
        selected_device = default_device
    else:
        print("\nAvailable devices:")
        for i, (name, id) in enumerate(devices):
            print(f"{i+1}. {name} ({id})")

        device_choice = int(input("Choose a device to run the app (enter the number): ")) - 1
        if device_choice < 0 or device_choice >= len(devices):
            print("Invalid choice. Exiting.")
            return

        selected_device = devices[device_choice][1]

    # Create ProjectContextManager
    project_context_manager = ProjectContextManager(project_root)

    # Run the Flutter app
    print(f"Attempting to run Flutter app on device {selected_device}...")
    flutter_process = run_flutter_app(selected_device, client, project_context_manager.file_contents, project_root)
    if not flutter_process:
        print("Failed to start Flutter app. Continuing without running the app...")
    else:
        print("Flutter app process started. Continuing with development.")

    development_loop(client, project_root, flutter_process, selected_device)

if __name__ == "__main__":
    main()
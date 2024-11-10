import os
import json
from typing import Dict
import ollama
from config import OLLAMA_MODEL

def update_project_files(file_updates: Dict[str, str]) -> None:
    """
    Update or create project files based on the generated code.
    """
    for file_path, content in file_updates.items():
        full_path = os.path.join(os.getcwd(), file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as file:
            file.write(content)
        print(f"File '{full_path}' has been updated/created.")

def self_correct(client: ollama.Client, error_message: str, project_files: Dict[str, str]):
    """
    Attempt to self-correct the code based on the error message.
    """
    print(f"Attempting to self-correct based on error: {error_message}")
    prompt = f"""
    The following error occurred in the Flutter app:
    {error_message}

    Analyze the error and provide a solution. If you need to update any files, specify the file path and the complete updated content for each file.
    Respond with a JSON object where keys are file paths and values are the complete updated content for each file.
    If no files need to be updated, respond with an empty JSON object {{}}.
    """
    response = client.generate(model=OLLAMA_MODEL, prompt=prompt)
    try:
        corrected_code = json.loads(response['response'])
        if corrected_code:
            print("Corrected code generated. Applying fixes...")
            update_project_files(corrected_code)
            print("Fixes applied. Flutter should hot-reload automatically.")
        else:
            print("No code changes required to fix the error.")
    except json.JSONDecodeError:
        print("Failed to parse the corrected code. Manual intervention may be required.")

def verify_changes(client: ollama.Client, task: str, project_files: Dict[str, str]) -> bool:
    """
    Verify the changes made by the LLM.
    """
    print(f"Verifying changes for task: {task}")
    file_list = "\n".join(project_files.keys())
    prompt = f"""
    Task: {task}

    Current project files:
    {file_list}

    Verify that the changes made to the project files are correct and complete for the given task.
    Respond with 'Yes' if the changes are correct and complete, or 'No' if there are issues or missing implementations.
    If responding with 'No', briefly explain what is missing or incorrect.
    """
    response = client.generate(model=OLLAMA_MODEL, prompt=prompt)
    verification = response['response'].strip().lower()
    if verification.startswith('yes'):
        print("Changes verified successfully.")
        return True
    else:
        print(f"Verification failed: {response['response']}")
        return False
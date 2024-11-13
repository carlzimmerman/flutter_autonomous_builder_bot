import os
from typing import Dict
from utils import run_command

def get_project_structure(root_dir: str) -> Dict[str, str]:
    """
    Get the structure of the Flutter project and contents of all Dart files in the lib folder.
    """
    print(f"Getting project structure for: {root_dir}")
    project_files = {}
    lib_dir = os.path.join(root_dir, 'lib')
    for root, dirs, files in os.walk(lib_dir):
        for file in files:
            if file.endswith('.dart'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    project_files[file_path] = f.read()
    print(f"Found {len(project_files)} Dart files in the project.")
    return project_files

def create_flutter_project(project_name: str) -> str:
    """
    Create a new Flutter project.
    Returns the path to the created project.
    """
    print(f"Creating new Flutter project: {project_name}")

    original_working_directory = os.getcwd()  # Store the original working directory

    output, error = run_command(f"flutter create {project_name}")
    print("Output:", output)
    print("Error:", error)
    if "Creating project" not in output:
        print(f"Error creating Flutter project. Details: {error}")
        return ""
    print(f"Flutter project '{project_name}' created successfully.")

    # Construct the project_path using the original working directory
    project_path = os.path.join(original_working_directory, project_name)

    # Replace default main.dart with our template
    template_path = os.path.join(original_working_directory, 'templates', 'default_main.dart')
    main_dart_path = os.path.join(project_path, 'lib', 'main.dart')

    try:
        with open(template_path, 'r') as template_file:
            template_content = template_file.read()
        with open(main_dart_path, 'w') as main_file:
            main_file.write(template_content)
        print("Successfully replaced main.dart with template version")
    except Exception as e:
        print(f"Error replacing main.dart template: {str(e)}")

    return project_path

def select_or_create_project() -> str:
    """
    Allow the user to select an existing project or create a new one.
    Returns the path to the selected or created project.
    """
    print("\nDo you want to use an existing Flutter project or create a new one?")
    choice = input("Enter 'existing' or 'new': ").lower()

    if choice == 'existing':
        project_path = input("Enter the full path to your existing Flutter project: ")
        if os.path.isdir(project_path):
            os.chdir(project_path)
            print(f"Changed to existing project directory: {project_path}")
            return project_path
        else:
            print("Invalid project path. Please try again.")
            return ""
    elif choice == 'new':
        project_name = input("Enter the name for your new Flutter project: ")
        if create_flutter_project(project_name):
            return os.path.join(os.getcwd(), project_name)
        else:
            return ""
    else:
        print("Invalid choice. Please try again.")
        return ""
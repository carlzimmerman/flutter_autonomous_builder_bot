import os
import json
import re
from typing import Dict, List, Any
import ollama
import tempfile
import logging
from ai_client import AIClient
from config import SKIP_DART_ANALYSIS
import subprocess
from task_context import TaskContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
def ensure_correct_structure(client: AIClient, project_files: Dict[str, str], project_root: str, task_context: TaskContext):
    logger.info("Starting project structure analysis and correction")
    try:
        # 1. Analyze current project structure
        screen_files = [path for path in project_files.keys() if path.startswith('lib/screens/')]
        widget_files = [path for path in project_files.keys() if path.startswith('lib/widgets/')]
        provider_files = [path for path in project_files.keys() if path.startswith('lib/providers/')]
        service_files = [path for path in project_files.keys() if path.startswith('lib/services/')]

        # 2. Build analysis based on existing files
        analysis = {
            "main_dart_updates": {
                "imports_to_add": [],
                "routes_to_add": {},
                "initial_route": None,
                "providers_to_initialize": []
            },
            "dependencies": []
        }

        # 3. Remove duplicate widget definitions from main.dart
        main_dart_path = 'lib/main.dart'
        if main_dart_path in project_files:
            main_content = project_files[main_dart_path]
            for widget_name, file_path in task_context.created_widgets.items():
                if widget_name in main_content and file_path != main_dart_path:
                    pattern = f"class {widget_name}.*?}}\n?"
                    main_content = re.sub(pattern, "", main_content, flags=re.DOTALL)
                    logger.info(f"Removed duplicate widget {widget_name} from main.dart")
            project_files[main_dart_path] = main_content

        # 4. Check each type of file for needed updates
        # Screen files -> routes and imports
        for screen_path in screen_files:
            screen_name = os.path.basename(screen_path).replace('.dart', '')
            screen_class = ''.join(word.capitalize() for word in screen_name.split('_'))
            route_name = f"/{screen_name.replace('_screen', '')}"

            # Add to task context
            task_context.add_widget(screen_class, screen_path)
            task_context.add_route(route_name, screen_class)

            analysis["main_dart_updates"]["imports_to_add"].append(
                f"import './{screen_path.replace('lib/', '')}'"
            )
            analysis["main_dart_updates"]["routes_to_add"][route_name] = f"{screen_class}()"

        # Provider files -> provider initialization and imports
        for provider_path in provider_files:
            provider_name = os.path.basename(provider_path).replace('.dart', '')
            provider_class = ''.join(word.capitalize() for word in provider_name.split('_'))

            analysis["main_dart_updates"]["imports_to_add"].append(
                f"import './{provider_path.replace('lib/', '')}'"
            )
            if not 'provider' in analysis["dependencies"]:
                analysis["dependencies"].append("provider: ^6.0.0")
            analysis["main_dart_updates"]["providers_to_initialize"].append(
                f"ChangeNotifierProvider(create: (_) => {provider_class}())"
            )

        # 5. Set initial route based on task context
        if task_context.routes:
            # Use the most recently added route as initial
            analysis["main_dart_updates"]["initial_route"] = list(task_context.routes.keys())[-1]

        # 6. Update main.dart if needed
        if any(analysis["main_dart_updates"].values()):
            update_main_dart(client, project_files, project_root, analysis["main_dart_updates"])

        # 7. Handle dependencies
        if analysis["dependencies"]:
            update_pubspec_yaml(client, project_files, project_root, analysis["dependencies"])

        # 8. Validate and fix Dart code
        for file_path, content in project_files.items():
            # Only validate lib/ files for now, skip tests
            if file_path.endswith('.dart') and file_path.startswith('lib/'):
                if not validate_dart_code(content):
                    logger.info(f"Fixing invalid Dart code in {file_path}")
                    fixed_content = fix_dart_code(client, content, file_path, project_files)
                    if validate_dart_code(fixed_content):
                        project_files[file_path] = fixed_content
                        with open(os.path.join(project_root, file_path), 'w') as f:
                            f.write(fixed_content)
                        logger.info(f"Fixed and updated {file_path}")

        logger.info("Project structure validation complete")
    except Exception as e:
        logger.error(f"Error in ensure_correct_structure: {str(e)}", exc_info=True)
        raise

def update_existing_files(client: AIClient, project_files: Dict[str, str], project_root: str, files_to_update: List[Dict[str, Any]]):
    for file_info in files_to_update:
        file_path = os.path.join(project_root, file_info["file_path"])
        if file_path in project_files:
            current_content = project_files[file_path]
            updated_content = update_file_content(client, file_path, current_content, file_info["changes"])
            project_files[file_path] = updated_content
            with open(file_path, 'w') as f:
                f.write(updated_content)
            logger.info(f"Updated file: {file_path}")

def create_new_files(client: AIClient, project_files: Dict[str, str], project_root: str, new_files: List[Dict[str, Any]]):
    for new_file in new_files:
        file_path = os.path.join(project_root, new_file["file_path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        content = generate_file_content(client, new_file["file_path"], new_file["content"])
        with open(file_path, 'w') as f:
            f.write(content)
        project_files[new_file["file_path"]] = content
        logger.info(f"Created new file: {file_path}")

def handle_dependencies(client: AIClient, project_files: Dict[str, str], project_root: str, dependencies: List[str]):
    if dependencies:
        update_pubspec_yaml(client, project_files, project_root, dependencies)
    else:
        logger.info("No new dependencies to add.")


def validate_and_fix_dart_code(client: AIClient, project_files: Dict[str, str], project_root: str):
    for file_path, content in project_files.items():
        if file_path.endswith('.dart'):
            if not validate_dart_code(content):
                logger.info(f"Fixing invalid Dart code in {file_path}")
                fixed_content = fix_dart_code(client, content, file_path, project_files)
                if validate_dart_code(fixed_content):
                    project_files[file_path] = fixed_content
                    with open(os.path.join(project_root, file_path), 'w') as f:
                        f.write(fixed_content)
                    logger.info(f"Fixed and updated {file_path}")
                else:
                    logger.warning(f"Failed to fix {file_path}. Manual intervention may be required.")



def parse_and_validate_json(client: AIClient, json_str: str) -> Dict[str, Any]:
    try:
        analysis = json.loads(json_str)
        if 'dependencies' not in analysis:
            analysis['dependencies'] = []
        return analysis
    except json.JSONDecodeError:
        logger.error("Invalid JSON response from LLM. Attempting to correct...")
        correction_prompt = f"""
        The following response was supposed to be a valid JSON object, but it contains errors:

        {json_str}

        Please correct the JSON and provide a valid response that matches the required structure:
        {{
            "files_to_update": [...],
            "new_files": [...],
            "files_to_delete": [...],
            "main_dart_updates": {{...}},
            "dependencies": [...]
        }}

        Ensure all keys are present, even if their values are empty lists or objects.
        """
        correction_response = client.generate(prompt=correction_prompt)
        try:
            corrected_analysis = json.loads(correction_response['response'])
            if 'dependencies' not in corrected_analysis:
                corrected_analysis['dependencies'] = []
            logger.info("JSON successfully corrected.")
            return corrected_analysis
        except json.JSONDecodeError:
            logger.error("Failed to correct JSON. Using default empty structure.")
            return {
                "files_to_update": [],
                "new_files": [],
                "files_to_delete": [],
                "main_dart_updates": {
                    "providers_to_initialize": [],
                    "routes": [],
                    "initial_route": "/"
                },
                "dependencies": []
            }


def update_project_structure(client: AIClient, project_files: Dict[str, str], project_root: str, analysis: Dict[str, Any]):
    print("\n--- Updating project structure ---")
    for file_info in analysis.get("files_to_update", []):
        file_path = os.path.join(project_root, file_info["file_path"])
        if file_path in project_files:
            updated_content = update_file_content(client, file_path, project_files[file_path], file_info["changes"])
            project_files[file_path] = updated_content
            with open(file_path, 'w') as f:
                f.write(updated_content)
            print(f"Updated file: {file_path}")
            print(f"Content:\n{updated_content}\n")

    for new_file in analysis.get("new_files", []):
        file_path = os.path.join(project_root, new_file["file_path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        content = generate_file_content(client, new_file["file_path"], new_file["content"])
        with open(file_path, 'w') as f:
            f.write(content)
        project_files[new_file["file_path"]] = content
        print(f"Created new file: {file_path}")
        print(f"Content:\n{content}\n")

    for file_to_delete in analysis.get("files_to_delete", []):
        file_path = os.path.join(project_root, file_to_delete)
        if os.path.exists(file_path):
            os.remove(file_path)
            del project_files[file_to_delete]
            print(f"Deleted file: {file_path}")
    print("--- Project structure update complete ---\n")

def update_file_content(client: AIClient, file_path: str, current_content: str, changes: List[str]) -> str:
    prompt = f"""
    Update the following file content based on these changes:
    File: {file_path}
    Current content:
    {current_content}

    Changes to make:
    {json.dumps(changes, indent=2)}

    Provide the updated file content, ensuring that existing functionality is maintained and the changes improve the overall structure and coherence of the project.
    """

    response = client.generate( prompt=prompt)
    return response['response'].strip()

def generate_file_content(client: AIClient, file_path: str, content_description: str) -> str:
    prompt = f"""
    Generate content for a new file:
    File: {file_path}
    Description: {content_description}

    Provide the complete file content, ensuring it fits well with the overall project structure and follows best practices for Flutter development.
    """

    response = client.generate(prompt=prompt)
    return response['response'].strip()

def update_main_dart(client: AIClient, project_files: Dict[str, str], project_root: str, main_dart_updates: Dict[str, Any]):
    main_dart_path = 'lib/main.dart'
    current_content = project_files.get(main_dart_path, '')

    # Handle imports first
    imports_to_add = [
        f"import '{imp}';" for imp in main_dart_updates.get('imports_to_add', [])
        if imp not in current_content
    ]
    updated_content = manage_dart_imports(main_dart_path, imports_to_add, project_files)

    # Update routes and providers
    prompt = f"""
    Update this main.dart file to add these routes and providers.
    Do NOT include any explanations or JSON, just return the Dart code.

    Routes to add: {json.dumps(main_dart_updates.get('routes_to_add', {}))}
    Initial route: {main_dart_updates.get('initial_route')}
    Providers: {json.dumps(main_dart_updates.get('providers_to_initialize', []))}

    Current content:
    {updated_content}
    """

    for attempt in range(3):
        try:
            response = client.generate(prompt=prompt)
            code = response['response']

            # Clean up any markdown or JSON
            if '```dart' in code:
                code = code.split('```dart')[-1].split('```')[0]
            elif '```' in code:
                code = code.split('```')[1]

            # Basic validation
            if ('import' in code and
                'MaterialApp' in code and
                'class MyApp' in code and
                'Widget build' in code):

                project_files[main_dart_path] = code.strip()
                with open(os.path.join(project_root, main_dart_path), 'w') as f:
                    f.write(code.strip())
                logger.info("Successfully updated main.dart")
                return

        except Exception as e:
            logger.error(f"Error updating main.dart (attempt {attempt + 1}): {str(e)}")

    logger.warning("Failed to update main.dart properly")

def generate_main_dart(client: AIClient, main_dart_updates: Dict[str, Any]) -> str:
    prompt = f"""
    Generate a new main.dart file for a Flutter project with the following requirements:
    1. Initialize these providers: {', '.join(main_dart_updates.get('providers_to_initialize', []))}
    2. Set up these routes:
    {json.dumps(main_dart_updates.get('routes', []), indent=2)}
    3. Set the initial route to: {main_dart_updates.get('initial_route', '/')}

    Ensure the file includes necessary imports, uses MaterialApp for routing, and wraps the app with necessary provider widgets.
    Follow best practices for Flutter development and provide a complete, runnable main.dart file.
    """

    response = client.generate( prompt=prompt)
    return response['response'].strip()

def update_existing_main_dart(client: AIClient, current_content: str, main_dart_updates: Dict[str, Any]) -> str:
    prompt = f"""
    Update the following main.dart file to incorporate these changes:
    1. Initialize these providers: {', '.join(main_dart_updates.get('providers_to_initialize', []))}
    2. Set up these routes:
    {json.dumps(main_dart_updates.get('routes', []), indent=2)}
    3. Set the initial route to: {main_dart_updates.get('initial_route', '/')}

    Current main.dart content:
    {current_content}

    Return a JSON object with the following structure:
    {{
        "dart_code": "the complete main.dart content",
        "imports": ["list of imports needed"],
        "routes_added": ["list of routes added"],
        "providers_added": ["list of providers added"]
    }}

    IMPORTANT:
    - The dart_code should be complete and valid Flutter/Dart syntax
    - Must include proper routing setup
    - Must preserve MaterialApp and theme configuration
    """

    for attempt in range(3):
        try:
            response = client.generate(prompt=prompt)
            response_text = response['response']

            # First try: Parse as JSON
            try:
                result = json.loads(response_text)
                code = result.get('dart_code', '')
                if code and 'MaterialApp' in code and 'build' in code:
                    return code.strip()
            except json.JSONDecodeError:
                # Second try: Check if it's direct Dart code
                if 'import' in response_text and 'MaterialApp' in response_text:
                    # Extract code from markdown if present
                    if '```dart' in response_text:
                        code = response_text.split('```dart')[-1].split('```')[0]
                    else:
                        code = response_text

                    if code and 'MaterialApp' in code and 'build' in code:
                        # Try to convert to proper JSON format
                        correction_prompt = f"""
                        Convert this Dart code into a JSON response:

                        {code}

                        Return a JSON object with this structure:
                        {{
                            "dart_code": "the complete code here",
                            "imports": ["list of imports"],
                            "routes_added": ["list of routes"],
                            "providers_added": ["list of providers"]
                        }}
                        """

                        correction_response = client.generate(prompt=correction_prompt)
                        try:
                            corrected = json.loads(correction_response['response'])
                            if corrected.get('dart_code'):
                                return corrected['dart_code'].strip()
                        except json.JSONDecodeError:
                            # If conversion fails, return the cleaned code
                            return code.strip()

                # If both attempts fail, try one more time with explicit correction
                logger.warning(f"Retrying with explicit correction (attempt {attempt + 1})")
                correction_prompt = f"""
                Convert this response into proper JSON format:

                {response_text}

                Return ONLY a JSON object with this structure:
                {{
                    "dart_code": "the complete main.dart content",
                    "imports": ["list of imports"],
                    "routes_added": ["list of routes"],
                    "providers_added": ["list of providers"]
                }}
                """

                correction_response = client.generate(prompt=correction_prompt)
                try:
                    corrected = json.loads(correction_response['response'])
                    if corrected.get('dart_code'):
                        return corrected['dart_code'].strip()
                except json.JSONDecodeError:
                    logger.error(f"Failed to correct JSON on attempt {attempt + 1}")

        except Exception as e:
            logger.error(f"Error in update_existing_main_dart (attempt {attempt + 1}): {str(e)}")

        if attempt < 2:
            logger.warning(f"Retrying main.dart update (attempt {attempt + 1})")

    logger.warning("All attempts failed, returning current content")
    return current_content

def update_pubspec_yaml(client: AIClient, project_files: Dict[str, str], project_root: str, new_dependencies: List[str]):
    print("\n--- Updating pubspec.yaml ---")
    pubspec_path = 'pubspec.yaml'
    if pubspec_path not in project_files:
        print(f"Error: {pubspec_path} not found in project files.")
        return

    current_content = project_files[pubspec_path]
    updated_content = add_dependencies_to_pubspec(client, current_content, new_dependencies)

    project_files[pubspec_path] = updated_content
    with open(os.path.join(project_root, pubspec_path), 'w') as f:
        f.write(updated_content)
    print(f"Updated pubspec.yaml content:\n{updated_content}\n")
    print("--- pubspec.yaml update complete ---\n")

def add_dependencies_to_pubspec(client: AIClient, current_content: str, new_dependencies: List[str]) -> str:
    prompt = f"""
    Update the following pubspec.yaml file to add these new dependencies:
    {', '.join(new_dependencies)}

    Current pubspec.yaml content:
    {current_content}

    Provide the updated pubspec.yaml content, ensuring all existing dependencies are preserved and new ones are added with appropriate version constraints.
    Follow best practices for pubspec.yaml file structure and dependency management in Flutter projects.
    """

    response = client.generate( prompt=prompt)
    return response['response'].strip()

# def create_missing_components(client: AIClient, project_files: Dict[str, str], project_root: str):
#     print("\n--- Creating missing components ---")
#     essential_components = [
#         'lib/screens',
#         'lib/models',
#         'lib/providers',
#         'lib/services',
#         'lib/widgets',
#         'lib/utils',
#     ]
#
#     for component in essential_components:
#         if not any(file.startswith(component) for file in project_files):
#             create_component(client, project_files, project_root, component)
#     print("--- Missing components creation complete ---\n")


def manage_dart_imports(file_path: str, imports_to_add: List[str], project_files: Dict[str, str]) -> str:
    """Manages imports at the top of Dart files"""
    content = project_files.get(file_path, '')

    # Split content into imports and rest of code
    lines = content.split('\n')
    import_lines = [line for line in lines if line.strip().startswith('import')]
    code_lines = [line for line in lines if not line.strip().startswith('import')]

    # Add new imports if they don't exist
    for import_to_add in imports_to_add:
        if not any(import_to_add in line for line in import_lines):
            import_lines.append(import_to_add)

    # Reconstruct file with sorted imports at top
    return '\n'.join(sorted(import_lines) + [''] + code_lines)


def create_component(client: AIClient, project_files: Dict[str, str], project_root: str, component: str):
    prompt = f"""
    Generate a basic structure for the {component} directory in a Flutter project.
    Provide a list of files that should be created in this directory, along with a brief description of each file's purpose.
    Follow best practices for Flutter project organization and file naming conventions.

    Respond with a JSON object where keys are file paths and values are file content descriptions.
    """

    response = client.generate( prompt=prompt)
    component_structure = parse_and_validate_json(client, response['response'])

    for file_path, content_description in component_structure.items():
        full_path = os.path.join(project_root, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        content = generate_file_content(client, file_path, content_description)
        with open(full_path, 'w') as f:
            f.write(content)
        project_files[file_path] = content
        print(f"Created new file: {file_path}")


def validate_dart_code(code: str) -> bool:
    # If code is in JSON format, extract the dart_code
    try:
        if code.strip().startswith('{'):
            json_data = json.loads(code)
            code = json_data.get('dart_code', code)
    except json.JSONDecodeError:
        pass

    # Skip validation if it's not a lib/ file
    if 'test/' in code:
        return True

    with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False) as temp_file:
        temp_file.write(code)
        temp_file.flush()

        try:
            result = subprocess.run(['dart', 'analyze', temp_file.name], capture_output=True, text=True)
            if result.returncode == 0:
                return True
            else:
                # Only log warnings for lib/ files
                if 'lib/' in temp_file.name:
                    logger.warning(f"Dart analysis found issues:\n{result.stdout}\n{result.stderr}")
                return False
        finally:
            os.unlink(temp_file.name)

def fix_dart_code(client: AIClient, invalid_code: str, file_path: str, project_context: Dict[str, str]) -> str:
    context_prompt = "\n".join([f"{path}:\n{content}\n" for path, content in project_context.items()])
    prompt = f"""
    The following Dart code for {file_path} is invalid:

    ```dart
    {invalid_code}
    ```

    Project Context:
    {context_prompt}

    Please fix the code to make it valid Dart code for a Flutter project.
    Ensure that the fixed code maintains all intended functionality and is consistent with the rest of the project.
    Pay attention to:
    1. Correct syntax and formatting
    2. Proper use of Flutter widgets and patterns
    3. Consistency with existing project structure and naming conventions
    4. Handling of any potential null safety issues

    Respond with only the fixed Dart code, nothing else.
    """

    response = client.generate(prompt=prompt)
    fixed_code = response['response'].strip()

    # Remove any markdown code block syntax if present
    fixed_code = fixed_code.replace("```dart", "").replace("```", "").strip()

    return fixed_code
#
# # Update the ensure_correct_structure function to include code validation and fixing
# def ensure_correct_structure(client: AIClient, project_files: Dict[str, str], project_root: str):
#     logger.info("Starting project structure analysis and correction")
#     try:
#         analysis = analyze_project_structure(client, project_files, project_root)
#         update_project_structure(client, project_files, project_root, analysis)
#         update_main_dart(client, project_files, project_root, analysis.get('main_dart_updates', {}))
#
#         dependencies = analysis.get('dependencies', [])
#         if dependencies:
#             update_pubspec_yaml(client, project_files, project_root, dependencies)
#         else:
#             logger.info("No new dependencies to add.")
#
#         create_missing_components(client, project_files, project_root)
#
#         # Add code validation and fixing
#         for file_path, content in project_files.items():
#             if file_path.endswith('.dart'):
#                 if not validate_dart_code(content):
#                     logger.info(f"Fixing invalid Dart code in {file_path}")
#                     fixed_content = fix_dart_code(client, content, file_path, project_files)
#                     if validate_dart_code(fixed_content):
#                         project_files[file_path] = fixed_content
#                         with open(os.path.join(project_root, file_path), 'w') as f:
#                             f.write(fixed_content)
#                         logger.info(f"Fixed and updated {file_path}")
#                     else:
#                         logger.warning(f"Failed to fix {file_path}. Manual intervention may be required.")
#
#         logger.info("Project structure has been updated and ensured for correctness.")
#     except Exception as e:
#         logger.error(f"Error in ensure_correct_structure: {str(e)}", exc_info=True)
#         raise

if __name__ == "__main__":
    # This block can be used for testing the module independently
    pass
import os
import json
import re
import logging
from typing import Dict, List, Any, Tuple
import tempfile
import subprocess
from config import SKIP_DART_ANALYSIS
from ai_client import AIClient

logger = logging.getLogger(__name__)

class FlutterProjectValidator:
    def __init__(self, client: AIClient):
        self.client = client

    def validate_and_fix_dart_code(self, content: str, file_path: str) -> str:
        if SKIP_DART_ANALYSIS:
            return content  # Return the generated content without validation if analysis is skipped

        if not self.validate_dart_code(content):
            fixed_content = self.fix_dart_code(content, file_path)
            if self.validate_dart_code(fixed_content):
                return fixed_content
            else:
                logger.warning(f"Failed to fix critical issues in Dart code for {file_path}. Returning original content.")
                return content
        return content

    def validate_dart_code(self, code: str) -> bool:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False) as temp_file:
            temp_file.write(code)
            temp_file.flush()

            try:
                result = subprocess.run(['dart', 'analyze', '--fatal-infos', '--fatal-warnings', temp_file.name], capture_output=True, text=True)
                if result.returncode == 0:
                    return True
                else:
                    # Check if the errors are critical
                    if self.has_critical_errors(result.stdout + result.stderr):
                        logger.warning(f"Critical Dart analysis issues found:\n{result.stdout}\n{result.stderr}")
                        return False
                    else:
                        logger.info(f"Non-critical Dart analysis issues found, but ignoring:\n{result.stdout}\n{result.stderr}")
                        return True
            finally:
                os.unlink(temp_file.name)



    def has_critical_errors(self, analysis_output: str) -> bool:
        critical_patterns = [
            r'Error:',
            r'Compilation failed',
            r'Undefined name',
            r'The method .* isn\'t defined',
            r'The class .* isn\'t defined',
            r'Undefined class',
            r'Invalid syntax',
            r'Expected to find'
        ]
        return any(re.search(pattern, analysis_output) for pattern in critical_patterns)


    def fix_common_dart_issues(self, code: str) -> str:
        # Add missing imports
        if 'import' not in code:
            code = "import 'package:flutter/material.dart';\n" + code
        # Fix common class issues
        code = code.replace("extends StatelessWidget", "extends StatelessWidget")
        # Ensure build method is present in StatelessWidget
        if "extends StatelessWidget" in code and "Widget build" not in code:
            code += "\n  @override\n  Widget build(BuildContext context) {\n    return Container();\n  }\n"
        # More fixes can be added here
        return code


    def fix_dart_code(self, invalid_code: str, file_path: str) -> str:
        prompt = f"""
        The following Dart code for {file_path} may have critical issues:

        ```dart
        {invalid_code}
        ```

        Please fix any critical syntax errors or structural issues that would prevent the code from compiling or running.
        Focus only on breaking changes and ignore minor style issues or non-critical warnings.
        Ensure that the fixed code is valid Dart for a Flutter project.
        Return only the fixed Dart code, without any explanations or markdown.
        """

        try:
            response = self.client.generate( prompt=prompt)
            fixed_code = response['response'].strip()
            # Remove any markdown code block syntax if present
            fixed_code = fixed_code.replace("```dart", "").replace("```", "").strip()
            return fixed_code
        except Exception as e:
            logger.error(f"Error fixing Dart code: {str(e)}")
            return invalid_code

    def verify_code_integrity(self, original_code: str, new_code: str, file_path: str) -> Dict[str, Any]:
        prompt = f"""
        Compare the following two versions of Dart code for {file_path}:

        Original code:
        ```dart
        {original_code}
        ```

        New code:
        ```dart
        {new_code}
        ```

        Verify if the new code maintains all the critical functionality of the original code and doesn't introduce any breaking changes.
        Ignore minor style differences or non-functional changes.
        Respond with a JSON object containing two keys:
        1. "integrity_maintained": A boolean indicating if the code integrity is maintained (true) or if there are breaking changes (false).
        2. "explanation": A brief explanation of your decision, focusing only on critical changes if any.

        Example response:
        {{
            "integrity_maintained": true,
            "explanation": "The new code preserves all critical functionality and doesn't introduce breaking changes."
        }}
        """

        response = self.client.generate( prompt=prompt)
        return json.loads(response['response'])

    def resolve_integrity_issues(self, original_code: str, new_code: str, file_path: str) -> str:
        prompt = f"""
        The following two versions of Dart code for {file_path} have integrity issues:

        Original code:
        ```dart
        {original_code}
        ```

        New code with potential issues:
        ```dart
        {new_code}
        ```

        Please resolve any critical integrity issues by merging the functionality of both versions.
        Ensure that all essential features from the original code are preserved while incorporating the intended changes from the new code.
        Focus only on resolving breaking changes and maintaining critical functionality.
        Return only the merged and fixed Dart code, without any explanations or markdown.
        """

        try:
            response = self.client.generate( prompt=prompt)
            resolved_code = response['response'].strip()
            # Remove any markdown code block syntax if present
            resolved_code = resolved_code.replace("```dart", "").replace("```", "").strip()
            return resolved_code
        except Exception as e:
            logger.error(f"Error resolving integrity issues: {str(e)}")
            return original_code

    def regenerate_code_if_needed(self, file_path: str, project_context: Dict[str, str]) -> str:
        prompt = f"""
        Generate complete and correct Dart code for the file {file_path} in a Flutter project.
        Ensure the code is consistent with the following project context:

        {json.dumps(project_context, indent=2)}

        Provide only the Dart code, without any markdown code block syntax.
        """

        response = self.client.generate( prompt=prompt)
        return self.remove_code_markers(response['response'])

    def remove_code_markers(self, content: str) -> str:
        content = re.sub(r'^```dart\n', '', content)
        content = re.sub(r'\n```$', '', content)
        return content.strip()

    def validate_and_connect_files(self, project_root: str, project_files: Dict[str, str], tasks: List[Dict[str, Any]]):
        logger.info("Validating and connecting Flutter project files...")

        # Analyze all tasks and subtasks to understand the overall context
        project_context = self.analyze_project_context(tasks)

        # Determine the entry point and set up routes
        entry_point, routes = self.determine_entry_point_and_routes(project_files, project_context)

        # Create or update main.dart
        self.create_or_update_main_dart(project_root, project_files, entry_point, routes, project_context)

        # Validate and update other files
        for file_path in project_files:
            if file_path.startswith('lib/') and file_path != 'lib/main.dart':
                self.validate_and_update_file(project_root, file_path, project_files, project_context)

        # Ensure proper integration between files
        self.ensure_project_integration(project_root, project_files, project_context)

        logger.info("Project validation and connection completed.")


    def analyze_project_context(self, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        prompt = f"""
        Analyze the following tasks and subtasks for a Flutter project:
        {json.dumps(tasks, indent=2)}

        Provide a high-level overview of the project structure and functionality.
        Include information about:
        1. Main screens and their purposes
        2. Key models and their relationships
        3. State management approach (if any)
        4. Any services or utilities required
        5. Potential routes for navigation

        Return the analysis as a JSON object.
        """
        response = self.client.generate( prompt=prompt)
        return self.parse_llm_json_response(response['response'])

    def determine_entry_point_and_routes(self, project_files: Dict[str, str], project_context: Dict[str, Any]) -> Tuple[str, List[str]]:
        screens = [file for file in project_files.keys() if file.startswith('lib/screens/') and file.endswith('.dart')]

        prompt = f"""
        Based on the following project context and screen files, determine the main entry point (home screen) and the necessary routes for the Flutter app:

        Project context: {json.dumps(project_context, indent=2)}
        Screen files: {json.dumps(screens, indent=2)}

        Return a JSON object with two keys:
        1. "entry_point": The file path of the main entry point (home screen)
        2. "routes": An array of route strings for other screens

        Example:
        {{
            "entry_point": "lib/screens/home_screen.dart",
            "routes": [
                "/todo_list",
                "/add_todo",
                "/edit_todo"
            ]
        }}
        """
        response = self.client.generate( prompt=prompt)
        result = self.parse_llm_json_response(response['response'])
        return result.get('entry_point', ''), result.get('routes', [])

    def create_or_update_main_dart(self, project_root: str, project_files: Dict[str, str], entry_point: str, routes: List[str], project_context: Dict[str, Any]):
        main_dart_path = os.path.join(project_root, 'lib', 'main.dart')
        main_content = project_files.get('lib/main.dart', '')

        prompt = f"""
        Create or update the main.dart file for a Flutter app with the following specifications:

        Entry point: {entry_point}
        Routes: {json.dumps(routes, indent=2)}
        Project context: {json.dumps(project_context, indent=2)}

        Ensure that:
        1. All necessary imports are included
        2. The main app structure reflects the project's needs
        3. Proper routing is set up for all specified routes
        4. State management is initialized if needed (e.g., Provider setup)
        5. The entry point is set as the home screen

        Current main.dart content (if it exists):
        ```dart
        {main_content}
        ```

        Provide the complete, updated main.dart content.
        """
        response = self.client.generate(prompt=prompt)
        updated_content = self.extract_code_from_response(response['response'])

        project_files['lib/main.dart'] = updated_content
        with open(main_dart_path, 'w') as f:
            f.write(updated_content)
        logger.info("Created or updated main.dart with project structure")

    def validate_and_update_file(self, project_root: str, file_path: str, project_files: Dict[str, str], project_context: Dict[str, Any]):
        content = project_files[file_path]

        prompt = f"""
        Validate and update the following Dart file content for {file_path}, considering this project context:
        {json.dumps(project_context, indent=2)}

        Ensure that:
        1. All necessary imports are present
        2. The class name matches the file name (converting snake_case to PascalCase)
        3. The file's functionality aligns with the overall project structure
        4. Any required integrations with other components are implemented
        5. State management is properly utilized if applicable

        Current file content:
        ```dart
        {content}
        ```

        Provide the validated and updated file content.
        """
        response = self.client.generate(prompt=prompt)
        updated_content = self.extract_code_from_response(response['response'])

        project_files[file_path] = updated_content
        full_path = os.path.join(project_root, file_path)
        with open(full_path, 'w') as f:
            f.write(updated_content)
        logger.info(f"Validated and updated: {file_path}")

    def ensure_project_integration(self, project_root: str, project_files: Dict[str, str], project_context: Dict[str, Any]):
        prompt = f"""
        Review the entire Flutter project structure and ensure proper integration between all components.
        Project context: {json.dumps(project_context, indent=2)}

        Files in the project:
        {', '.join(project_files.keys())}

        Provide a list of any necessary changes to ensure all components work together seamlessly.
        Include file paths and specific changes needed.
        Return the result as a JSON object where keys are file paths and values are the required changes.
        """
        response = self.client.generate(prompt=prompt)
        integration_changes = self.parse_llm_json_response(response['response'])

        for file_path, changes in integration_changes.items():
            if file_path in project_files:
                content = project_files[file_path]
                updated_content = self.apply_integration_changes(content, changes)
                project_files[file_path] = updated_content
                full_path = os.path.join(project_root, file_path)
                with open(full_path, 'w') as f:
                    f.write(updated_content)
                logger.info(f"Applied integration changes to: {file_path}")

    def apply_integration_changes(self, content: str, changes: str) -> str:
        prompt = f"""
        Apply the following changes to the Dart file content:
        Changes to make: {changes}

        Current file content:
        ```dart
        {content}
        ```

        Provide the updated file content with the changes applied.
        """
        response = self.client.generate( prompt=prompt)
        return self.extract_code_from_response(response['response'])

    def extract_code_from_response(self, response: str) -> str:
        code_block = re.search(r'```dart\n(.*?)```', response, re.DOTALL)
        if code_block:
            return code_block.group(1).strip()
        return response.strip()

    def parse_llm_json_response(self, response: str) -> Dict:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}|\[.*\]', response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        logger.error(f"Failed to parse JSON from LLM response: {response}")
        return {}
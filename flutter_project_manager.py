import json
import os
from typing import Dict, List, Any
from ai_client import AIClient

class FlutterProjectManager:
    def __init__(self, client: AIClient, project_root: str):
        self.client = client
        self.project_root = project_root
        self.project_structure = self._analyze_project_structure()

    def _analyze_project_structure(self) -> Dict[str, Any]:
        structure = {}
        for root, dirs, files in os.walk(os.path.join(self.project_root, 'lib')):
            for file in files:
                if file.endswith('.dart'):
                    relative_path = os.path.relpath(os.path.join(root, file), self.project_root)
                    with open(os.path.join(root, file), 'r') as f:
                        content = f.read()
                    structure[relative_path] = content
        return structure

    def update_project(self, task: Dict[str, Any]) -> None:
        decision_tree = self._generate_decision_tree(task)
        self._execute_decision_tree(decision_tree)

    def _generate_decision_tree(self, task: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""
        Given the following task and current project structure, generate a decision tree for updating the Flutter project:

        Task: {json.dumps(task)}

        Current project structure:
        {json.dumps(self.project_structure.keys(), indent=2)}

        Provide a JSON response with the following structure:
        {{
            "actions": [
                {{
                    "type": "create_file" | "update_file" | "delete_file",
                    "file_path": "path/to/file.dart",
                    "content": "File content or updates",
                    "reason": "Explanation for this action"
                }},
                // ... more actions
            ],
            "main_dart_updates": {{
                "imports": ["package:to/import.dart"],
                "route_updates": [
                    {{
                        "route": "/new_route",
                        "widget": "NewWidget()"
                    }}
                ],
                "provider_initializations": [
                    "ChangeNotifierProvider(create: (_) => NewProvider())"
                ]
            }}
        }}

        Ensure that the decision tree:
        1. Creates new files only when necessary
        2. Updates existing files without overriding important previous work
        3. Initializes new components in main.dart
        4. Follows Flutter best practices for project structure
        """

        response = self.client.generate(prompt=prompt)
        return json.loads(response['response'])

    def _execute_decision_tree(self, decision_tree: Dict[str, Any]) -> None:
        for action in decision_tree['actions']:
            if action['type'] == 'create_file':
                self._create_file(action['file_path'], action['content'])
            elif action['type'] == 'update_file':
                self._update_file(action['file_path'], action['content'])
            elif action['type'] == 'delete_file':
                self._delete_file(action['file_path'])

        self._update_main_dart(decision_tree['main_dart_updates'])

    def _create_file(self, file_path: str, content: str) -> None:
        full_path = os.path.join(self.project_root, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
        print(f"Created file: {file_path}")

    def _update_file(self, file_path: str, content: str) -> None:
        full_path = os.path.join(self.project_root, file_path)
        with open(full_path, 'w') as f:
            f.write(content)
        print(f"Updated file: {file_path}")

    def _delete_file(self, file_path: str) -> None:
        full_path = os.path.join(self.project_root, file_path)
        os.remove(full_path)
        print(f"Deleted file: {file_path}")

    def _update_main_dart(self, updates: Dict[str, Any]) -> None:
        main_dart_path = os.path.join(self.project_root, 'lib', 'main.dart')
        with open(main_dart_path, 'r') as f:
            content = f.read()

        # Add imports
        import_section = "\n".join(f"import '{imp}';" for imp in updates['imports'])
        content = import_section + "\n" + content

        # Update routes
        for route_update in updates['route_updates']:
            route_pattern = f"'{route_update['route']}': (context) =>"
            if route_pattern not in content:
                content += f"\n      '{route_update['route']}': (context) => {route_update['widget']},"

        # Initialize providers
        provider_pattern = "providers: ["
        provider_index = content.find(provider_pattern)
        if provider_index != -1:
            insert_index = content.find("]", provider_index)
            content = content[:insert_index] + ",\n        " + ",\n        ".join(updates['provider_initializations']) + content[insert_index:]

        with open(main_dart_path, 'w') as f:
            f.write(content)
        print("Updated main.dart")

def integrate_flutter_project_manager(development_loop):
    def wrapped_development_loop(client: AIClient, project_files: Dict[str, str], flutter_process: Any, selected_device: str, project_root: str):
        project_manager = FlutterProjectManager(client, project_root)

        while True:
            user_input = input("\nEnter your Flutter development task (or 'exit' to quit): ")
            print(f"You entered: {user_input}")

            if user_input.lower() == 'exit':
                print("Thank you for using the Flutter LLM Assistant. Goodbye!")
                if flutter_process:
                    flutter_process.terminate()
                break

            try:
                task = generate_task(client, user_input)
                project_manager.update_project(task)

                if flutter_process:
                    print("Triggering hot reload...")
                    hot_reload(flutter_process)

                print("\nTask completed. You can now test the app or provide another development request.")

            except Exception as e:
                print(f"An error occurred during the development process: {str(e)}")
                print("Please try again or seek manual intervention if the issue persists.")

        print("Development loop ended.")

    return wrapped_development_loop

def generate_task(client: AIClient, user_input: str) -> Dict[str, Any]:
    prompt = f"""
    Based on the following Flutter app development request, generate a task object:

    Request: {user_input}

    Provide a JSON object with the following structure:
    {{
        "main_task": "Brief description of the main task",
        "subtasks": [
            "Subtask 1 description",
            "Subtask 2 description",
            // ... more subtasks
        ]
    }}

    Ensure the task and subtasks are specific and actionable for Flutter development.
    """

    response = client.generate(prompt=prompt)
    return json.loads(response['response'])
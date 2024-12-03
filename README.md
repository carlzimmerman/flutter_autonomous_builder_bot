Flutter Autonomous Builder Bot

A proof of concept for an AI-powered Flutter application builder that autonomously generates and modifies Flutter applications based on natural language instructions.

Core Classes and Components

1. TaskPlanner (task_planning.py)
- Main orchestrator for code generation
- Analyzes task complexity and requirements
- Methods:
    - generate_task_plan: Creates structured plans from natural language
    - analyze_task_needs: Determines if task needs state management, API, etc.
    - validate_task_plan: Ensures plan meets requirements
    - generate_file_content: Generates specific file content
    - generate_simplified_task_plan: Fallback for simpler implementations

2. ProjectContextManager (project_context_manager.py)
- Manages project state and file operations
- Methods:
    - update_context: Refreshes project state
    - get_context_prompt: Provides current project structure
    - update_file: Handles file modifications
    - get_file_content: Retrieves current file content

3. FlutterProjectValidator (flutter_project_validator.py)
- Validates Dart code and project structure
- Methods:
    - validate_and_fix_dart_code: Checks and corrects Dart syntax
    - validate_dart_code: Basic syntax validation
    - fix_common_dart_issues: Automated code corrections

4. Flutter Integration (flutter_integration.py)
- Handles Flutter-specific operations
- Features:
    - Check Flutter installation
    - Enable web support
    - Handle device management
    - Control hot reload

5. AIClient (ai_client.py)
- Manages AI model interactions
- Supports:
    - Ollama models
    - Gemini API
    - Configurable model selection

Logical Flow

1. Task Input & Analysis:
   User Input -> TaskPlanner.generate_task_plan -> analyze_task_needs -> Plan Generation

2. Code Generation:
   Task Plan -> generate_file_content -> strip_const_declarations -> validate_dart_code

3. Project Updates:
   ProjectContextManager -> update_file -> FlutterProjectValidator -> Hot Reload

Project Structure

lib/
├── main.dart         # Entry point with MaterialApp/Provider setup
├── screens/          # Screen widgets (e.g., todo_list_screen.dart)
├── widgets/          # Reusable UI components
├── providers/        # State management (when needed)
├── services/         # Business logic and API calls
└── models/          # Data structures and models

Key Features
- Smart detection of state management needs
- Automatic const declaration removal
- Project structure maintenance
- Hot reload integration
- Multiple AI model support

Error Handling
1. Task Planning:
    - Multiple retry attempts via max_retries
    - Fallback to simplified plans
    - Structured error logging

2. Code Generation:
    - Dart syntax validation
    - Const declaration management
    - Code structure verification

3. Project Management:
    - Directory creation
    - File operation safety
    - Context maintenance

Prerequisites
- Flutter SDK
- Python 3.8+
- Ollama (for open source models) or Gemini API key
- Chrome browser (for Flutter web development)

Installation

1. Clone the repository:
   git clone git@github.com:yourusername/flutter-bot.git
   cd flutter-bot

2. Create config file:
   cp config.py.template config.py

3. Configure settings in config.py:
- For Ollama (default):
    - Set USE_GEMINI_API = False
    - Choose your model by uncommenting desired OLLAMA_MODEL
- For Gemini:
    - Set USE_GEMINI_API = True
    - Add your Gemini API key

4. Install Python requirements:
   pip install -r requirements.txt

Example Usage

Enter your Flutter development task (or 'exit' to quit):
> create a simple todo list screen that just shows a hardcoded list of 3 todos

Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

License

[MIT](https://choosealicense.com/licenses/mit/)
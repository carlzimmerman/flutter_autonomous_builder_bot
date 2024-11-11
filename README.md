# Flutter Autonomous Builder Bot

A proof of concept for an AI-powered Flutter application builder that autonomously generates and modifies Flutter applications based on natural language instructions.

## Features
- Natural language to Flutter code generation
- Automated project structure management
- Hot reload integration
- Support for multiple AI models (Ollama and Gemini)
- Real-time code validation and fix attempts

## Prerequisites
- Flutter SDK
- Python 3.8+
- Ollama (for open source models) or Gemini API key
- Chrome browser (for Flutter web development)

## Installation

1. Clone the repository:
git clone git@github.com:yourusername/flutter-bot.git
cd flutter-bot

2. Create config file:
cp config.py.template config.py

3. Configure settings in `config.py`:
- For Ollama (default):
  - Set `USE_GEMINI_API = False`
  - Choose your model by uncommenting desired `OLLAMA_MODEL`
- For Gemini:
  - Set `USE_GEMINI_API = True`
  - Add your Gemini API key

4. Install Python requirements:
pip install -r requirements.txt

## Running the Bot

1. Start Ollama (if using open source models):

ollama serve

2. Run the bot:
3. 
python main.py

4. Follow the prompts to:
   - Create new or select existing Flutter project
   - Input development tasks in natural language

## Example Usage

Enter your Flutter development task (or 'exit' to quit):
> update the home screen to simply say "HELLO WORLD" in the middle of the page

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)

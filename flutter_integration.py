import time
import threading
import subprocess
import os
from typing import List, Tuple, Dict, Optional
from utils import run_command
from error_handling import self_correct
from ensure_structure_correct import ensure_correct_structure
import subprocess
import logging
from ai_client import AIClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def check_flutter_installation():
    """
    Check if Flutter is installed and configured correctly.
    """
    print("Checking Flutter installation...")
    output, error = run_command("flutter doctor")
    print("Flutter Doctor Output:")
    print(output)
    print(error)
    if "Flutter is not installed" in output or "command not found" in error:
        return False
    return True

def enable_flutter_web_support():
    """
    Enable Flutter web support if it's not already enabled.
    """
    print("Checking Flutter web support...")
    output, error = run_command("flutter config")
    if "enable-web: true" not in output:
        print("Enabling Flutter web support...")
        run_command("flutter config --enable-web")
        print("Flutter web support enabled.")
    else:
        print("Flutter web support is already enabled.")

def get_available_devices() -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """
    Get a list of available devices, including simulators.
    Returns a tuple containing the list of devices and the default device ID (if only Chrome is available).
    """
    print("Getting available devices...")
    output, _ = run_command("flutter devices")
    devices = []
    default_device = None

    for line in output.split('\n'):
        if '•' in line:
            device_info = line.split('•')
            if len(device_info) >= 2:
                name = device_info[0].strip()
                device_id = device_info[1].strip()
                devices.append((name, device_id))

    if len(devices) == 1 and devices[0][0].lower().startswith('chrome'):
        default_device = devices[0][1]

    return devices, default_device

def run_flutter_app(device_id: str, client: 'AIClient', project_files: Dict[str, str], project_root: str) -> Optional[subprocess.Popen]:
    """
    Run the Flutter app on the specified device and return the process.
    """
    logger.info(f"Running Flutter app on device {device_id}...")

    # Change to the project root directory
    os.chdir(project_root)

    # Run the Flutter app
    command = f"flutter run -d {device_id}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, text=True)

    # Start a thread to handle the Flutter process output
    output_thread = threading.Thread(target=handle_flutter_output, args=(process, client, project_files))
    output_thread.start()

    # Wait for a short time to see if the app starts
    time.sleep(30)  # Wait for 30 seconds

    if process.poll() is None:
        logger.info("Flutter app process started. Continuing with the script.")
        return process
    else:
        logger.error("Flutter app process ended unexpectedly.")
        output, error = process.communicate()
        logger.error(f"Output: {output}")
        logger.error(f"Error: {error}")
        return None

def handle_flutter_output(process: subprocess.Popen, client: AIClient, project_files: Dict[str, str]) -> None:
    """
    Handle the output of the Flutter process in a separate thread.
    """
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
        if "Flutter run key commands" in output:
            print("Flutter app started successfully.")
            break
    print("Flutter process output handling ended.")

def hot_reload(flutter_process: subprocess.Popen) -> bool:
    try:
        flutter_process.stdin.write('r\n')
        flutter_process.stdin.flush()
        time.sleep(2)  # Wait for hot reload to complete
        print("Hot reload triggered.")
        return True
    except Exception as e:
        print(f"Error during hot reload: {e}")
        return False

def full_restart(flutter_process: subprocess.Popen) -> bool:
    try:
        flutter_process.stdin.write('R\n')
        flutter_process.stdin.flush()
        time.sleep(5)  # Wait for full restart to complete
        print("Full restart triggered.")
        return True
    except Exception as e:
        print(f"Error during full restart: {e}")
        return False

# Add any additional helper functions here if needed

if __name__ == "__main__":
    # This block can be used for testing the module independently
    pass
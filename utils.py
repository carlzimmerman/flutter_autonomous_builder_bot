import subprocess
from typing import Tuple, Union
import re

def run_command(command: str, capture_output: bool = True) -> Union[Tuple[str, str], subprocess.Popen]:
    """
    Run a shell command and return its output and error.
    """
    print(f"Running command: {command}")
    if capture_output:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
        output, error = process.communicate()
        print(f"Command output: {output}")
        print(f"Command error: {error}")
        return output, error
    else:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return process

def truncate_context(context: str, max_length: int) -> str:
    """
    Truncate the context to fit within the maximum length.
    """
    if len(context) <= max_length:
        return context
    truncated = context[:max_length // 2] + "\n...\n" + context[-max_length // 2:]
    print(f"Context truncated from {len(context)} to {len(truncated)} characters.")
    return truncated



def strip_const_declarations(code: str) -> str:
    """
    Remove const declarations from Dart code while preserving the rest of the code structure.
    """
    # Remove const from const constructor calls - matches "const ClassName(" or "const _ClassName("
    code = re.sub(r'const\s+([A-Z_][A-Za-z0-9_]*)\(', r'\1(', code)

    # Remove const from const variable declarations - matches "const value =" or "const List<type>"
    code = re.sub(r'const\s+([A-Za-z0-9_<>]+\s+[A-Za-z0-9_]+\s*=)', r'\1', code)

    # Remove const from const collection literals - matches "const [" or "const {"
    code = re.sub(r'const\s+(\[|\{)', r'\1', code)

    # Remove const from named constructor calls - matches "const ClassName.named("
    code = re.sub(r'const\s+([A-Z_][A-Za-z0-9_]*\.[A-Za-z0-9_]+\()', r'\1', code)

    return code
import os
from typing import Dict, List
from utils import strip_const_declarations

class ProjectContextManager:
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.file_contents: Dict[str, str] = {}
        self.project_structure: List[str] = []
        self.update_context()

    def update_context(self):
        self.file_contents.clear()
        self.project_structure.clear()
        for root, dirs, files in os.walk(self.project_root):
            for file in files:
                if file.endswith('.dart'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.project_root)
                    self.project_structure.append(relative_path)
                    with open(file_path, 'r') as f:
                        self.file_contents[relative_path] = f.read()

    def get_context_prompt(self) -> str:
        context = "Project Structure:\n"
        context += "\n".join(self.project_structure)
        context += "\n\nFile Contents:\n"
        for file_path, content in self.file_contents.items():
            context += f"\n--- {file_path} ---\n{content}\n"
        return context

    def update_file(self, file_path: str, content: str):
        full_path = os.path.join(self.project_root, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        clean_content = strip_const_declarations(content)
        with open(full_path, 'w') as f:
            f.write(content)
        self.update_context()


    def delete_file(self, file_path: str):
        """
        Delete a file from the project and update the context.
        """
        try:
            full_path = os.path.join(self.project_root, file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                if file_path in self.file_contents:
                    del self.file_contents[file_path]
                logger.info(f"Successfully deleted file: {file_path}")
            else:
                logger.warning(f"File not found for deletion: {file_path}")
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            raise
        finally:
            self.update_context()

    def get_file_content(self, file_path: str) -> str:
        """
        Get the content of a file. If the file doesn't exist, return an empty string.
        """
        return self.file_contents.get(file_path, "")
# task_context.py
from typing import Dict, List, Optional

class TaskContext:
    def __init__(self):
        self.current_task: str = ""
        self.affected_files: List[str] = []
        self.created_widgets: Dict[str, str] = {}  # widget_name -> file_path
        self.routes: Dict[str, str] = {}  # route -> widget_name

    def update_task(self, task: str):
        self.current_task = task

    def add_widget(self, widget_name: str, file_path: str):
        self.created_widgets[widget_name] = file_path

    def add_route(self, route: str, widget_name: str):
        self.routes[route] = widget_name

    def get_widget_location(self, widget_name: str) -> Optional[str]:
        return self.created_widgets.get(widget_name)

import os
from pathlib import Path
from typing import List, Optional

from langchain.tools import tool


def _get_todo_file() -> Path:
    repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
    return repo_root / ".todo"


@tool
def write_todos(task: str, status: str = "todo", task_id: Optional[int] = None) -> str:
    """
    Manage a to-do list for organizing agent tasks.
    
    Args:
        task: The description of the task.
        status: The status of the task ('todo', 'done', 'in-progress').
        task_id: The ID of the task to update (leave empty to add a new task).
    """
    todo_file = _get_todo_file()
    lines = []
    if todo_file.exists():
        lines = todo_file.read_text(encoding="utf-8").splitlines()

    if task_id is not None:
        # Update existing task
        if 0 <= task_id < len(lines):
            lines[task_id] = f"[{status}] {task}"
            todo_file.write_text("\n".join(lines), encoding="utf-8")
            return f"Updated task {task_id}: {lines[task_id]}"
        else:
            return f"Error: Task ID {task_id} out of range."
    else:
        # Add new task
        new_task = f"[{status}] {task}"
        lines.append(new_task)
        todo_file.write_text("\n".join(lines), encoding="utf-8")
        return f"Added new task: {new_task} (ID: {len(lines)-1})"


@tool
def list_todos() -> str:
    """List all tasks in the to-do list."""
    todo_file = _get_todo_file()
    if not todo_file.exists():
        return "No tasks found."
    
    lines = todo_file.read_text(encoding="utf-8").splitlines()
    if not lines:
        return "To-do list is empty."
    
    numbered = [f"{i}: {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered)


__all__ = ["write_todos", "list_todos"]

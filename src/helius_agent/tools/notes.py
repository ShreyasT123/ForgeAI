import os
import re
from pathlib import Path
from typing import List

from langchain.tools import tool


def _get_repo_root() -> Path:
    return Path(os.getenv("REPO_ROOT", ".")).resolve()


def _get_notes_dir() -> Path:
    return _get_repo_root() / ".helius-code"


def _sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name)
    name = name.strip("-.")
    return name or "note"


def _resolve_note_path(title: str) -> Path:
    filename = _sanitize_filename(title)
    if not filename.lower().endswith(".md"):
        filename += ".md"
    return _get_notes_dir() / filename


@tool
def create_note(title: str, content: str, overwrite: bool = False) -> str:
    """Create a markdown note in .helius-code/ for repo instructions/patterns."""
    if not title or not title.strip():
        return "Error: title is required"
    if content is None:
        return "Error: content is required"

    notes_dir = _get_notes_dir()
    notes_dir.mkdir(parents=True, exist_ok=True)

    path = _resolve_note_path(title)
    if path.exists() and not overwrite:
        return f"Error: note already exists at {path.name}"

    path.write_text(content, encoding="utf-8")
    return f"Saved note: {path}"


@tool
def read_note(title: str) -> str:
    """Read a markdown note from .helius-code/."""
    if not title or not title.strip():
        return "Error: title is required"
    path = _resolve_note_path(title)
    if not path.exists():
        return f"Error: note not found at {path.name}"
    return path.read_text(encoding="utf-8")


@tool
def list_notes() -> str:
    """List notes in .helius-code/."""
    notes_dir = _get_notes_dir()
    if not notes_dir.exists():
        return "No notes found"
    notes = sorted(p.name for p in notes_dir.glob("*.md") if p.is_file())
    return "\n".join(notes) if notes else "No notes found"


@tool
def update_note(title: str, content: str, create_if_missing: bool = False) -> str:
    """Update an existing note (or create if create_if_missing=True)."""
    if not title or not title.strip():
        return "Error: title is required"
    if content is None:
        return "Error: content is required"
    notes_dir = _get_notes_dir()
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = _resolve_note_path(title)
    if not path.exists() and not create_if_missing:
        return f"Error: note not found at {path.name}"
    path.write_text(content, encoding="utf-8")
    return f"Updated note: {path}"


@tool
def delete_note(title: str) -> str:
    """Delete a note from .helius-code/."""
    if not title or not title.strip():
        return "Error: title is required"
    path = _resolve_note_path(title)
    if not path.exists():
        return f"Error: note not found at {path.name}"
    path.unlink()
    return f"Deleted note: {path.name}"


def load_all_notes() -> List[str]:
    """Return all notes content in a stable order (utility for middleware)."""
    notes_dir = _get_notes_dir()
    if not notes_dir.exists():
        return []
    contents = []
    for path in sorted(notes_dir.glob("*.md")):
        if path.is_file():
            contents.append(path.read_text(encoding="utf-8"))
    return contents


__all__ = [
    "create_note",
    "read_note",
    "list_notes",
    "update_note",
    "delete_note",
    "load_all_notes",
]

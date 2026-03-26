import os
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- Security and Configuration ---
WORKSPACE_ROOT = Path.cwd().resolve()
MAX_OUTPUT_LENGTH = 50_000
IGNORE_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}

def _resolve_path(filepath: str) -> Path:
    """Secure path resolution to prevent directory traversal attacks."""
    target = (WORKSPACE_ROOT / filepath).resolve()
    if not target.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(f"Security Error: Path '{filepath}' is outside the workspace.")
    return target


# --- 1. LS TOOL ---
class LsArgs(BaseModel):
    path: str = Field(default=".", description="Directory path to list.")

@tool(args_schema=LsArgs)
def ls(path: str = ".") -> str:
    """List files and directories in the given path."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Error: Path '{path}' does not exist."
        if not target.is_dir():
            return f"Error: '{path}' is not a directory."

        lines =[]
        for item in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name)):
            if item.name in IGNORE_DIRS:
                continue
            
            prefix = "      " if item.is_file() else "[DIR] "
            size_str = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
            lines.append(f"{prefix}{item.name}{size_str}")

        output = "\n".join(lines) or "Directory is empty."
        return output[:MAX_OUTPUT_LENGTH] + ("\n...[TRUNCATED]" if len(output) > MAX_OUTPUT_LENGTH else "")
    except Exception as e:
        return f"Error listing directory: {e}"


# --- 2. READ FILE TOOL ---
class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path to the file to read.")
    start_line: Optional[int] = Field(default=None, description="Starting line number (1-indexed).")
    end_line: Optional[int] = Field(default=None, description="Ending line number (1-indexed).")

@tool(args_schema=ReadFileArgs)
def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Read content of a file, optionally within a line range. Outputs with line numbers."""
    try:
        target = _resolve_path(path)
        if not target.is_file():
            return f"Error: File '{path}' does not exist."
        if target.stat().st_size > 5 * 1024 * 1024:
            return "Error: File is too large (> 5MB)."

        with open(target, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        s_idx = max(0, start_line - 1) if start_line else 0
        e_idx = min(len(lines), end_line) if end_line else len(lines)
        
        # Add line numbers to help the agent with context
        numbered_lines =[f"{i + s_idx + 1:4d} | {line}" for i, line in enumerate(lines[s_idx:e_idx])]
        output = "".join(numbered_lines)
        
        return output[:MAX_OUTPUT_LENGTH] + ("\n...[TRUNCATED]" if len(output) > MAX_OUTPUT_LENGTH else "")
    except UnicodeDecodeError:
        return f"Error: '{path}' appears to be a binary file."
    except Exception as e:
        return f"Error reading file: {e}"


# --- 3. WRITE FILE TOOL ---
class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path to the new file.")
    content: str = Field(..., description="Complete content to write to the file.")

@tool(args_schema=WriteFileArgs)
def write_file(path: str, content: str) -> str:
    """Write content to a new file. Fails if the file already exists."""
    try:
        target = _resolve_path(path)
        if target.exists():
            return f"Error: File '{path}' already exists. Use edit_file to modify it."

        # Automatically create missing parent directories
        target.parent.mkdir(parents=True, exist_ok=True)
        
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return f"Successfully wrote new file to '{path}'."
    except Exception as e:
        return f"Error writing file: {e}"


# --- 4. EDIT FILE TOOL (Surgical Diff) ---
class EditFileArgs(BaseModel):
    path: str = Field(..., description="Path of the file to edit.")
    old_string: str = Field(..., description="Exact string to find and replace. Must match perfectly.")
    new_string: str = Field(..., description="The new string to insert.")
    replace_all: bool = Field(default=False, description="If True, replaces all occurrences. If False, fails if not unique.")

@tool(args_schema=EditFileArgs)
def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replace a specific block of text in a file. Requires an exact match of the old_string."""
    try:
        target = _resolve_path(path)
        if not target.is_file():
            return f"Error: File '{path}' does not exist."

        with open(target, 'r', encoding='utf-8') as f:
            content = f.read()

        # Normalize line endings to avoid OS-level mismatches (CRLF vs LF)
        content_norm = content.replace('\r\n', '\n')
        old_norm = old_string.replace('\r\n', '\n')
        new_norm = new_string.replace('\r\n', '\n')

        occurrences = content_norm.count(old_norm)
        
        if occurrences == 0:
            return "Error: `old_string` not found in the file. Make sure you included exact whitespace and indentation."
        if occurrences > 1 and not replace_all:
            return f"Error: Found {occurrences} occurrences of `old_string`. It must be unique, or set replace_all=True."

        new_content = content_norm.replace(old_norm, new_norm)
        
        with open(target, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)
            
        return f"Successfully updated '{path}' ({occurrences} occurrences replaced)."
    except Exception as e:
        return f"Error editing file: {e}"


# --- 5. DELETE FILE TOOL ---
class DeleteFileArgs(BaseModel):
    path: str = Field(..., description="Path to the file or directory to delete.")

@tool(args_schema=DeleteFileArgs)
def delete_file(path: str) -> str:
    """Delete a file or an empty directory."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Error: Path '{path}' does not exist."
            
        if target.is_dir():
            try:
                target.rmdir()
                return f"Successfully deleted empty directory '{path}'."
            except OSError:
                return f"Error: Directory '{path}' is not empty. Manual deletion required."
        else:
            target.unlink()
            return f"Successfully deleted file '{path}'."
    except Exception as e:
        return f"Error deleting: {e}"


# --- 6. GREP SEARCH TOOL ---
class GrepSearchArgs(BaseModel):
    pattern: str = Field(..., description="Regex pattern to search for.")
    path: str = Field(default=".", description="Directory to search within.")

@tool(args_schema=GrepSearchArgs)
def grep_search(pattern: str, path: str = ".") -> str:
    """Search for a regex pattern across all files in a directory."""
    try:
        target = _resolve_path(path)
        if not target.is_dir():
            return f"Error: '{path}' is not a directory."

        regex = re.compile(pattern)
        matches =[]
        
        for root, dirs, files in os.walk(target):
            # Ignore hidden/build directories to speed up search
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                file_path = Path(root) / file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = file_path.relative_to(WORKSPACE_ROOT)
                                matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                                if len(matches) >= 100:  # Cap results early
                                    break
                except UnicodeDecodeError:
                    continue  # Skip binary files seamlessly
                    
            if len(matches) >= 100:
                matches.append("... [More than 100 matches found, truncating]")
                break

        return "\n".join(matches) if matches else "No matches found."
    except re.error as e:
        return f"Error: Invalid regex pattern - {e}"
    except Exception as e:
        return f"Error searching files: {e}"


# Bundled List for Agent Integration
FS_TOOLS =[ls, read_file, write_file, edit_file, delete_file, grep_search]
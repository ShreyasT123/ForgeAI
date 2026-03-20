
import logging
from typing import Optional

from langchain.tools import tool
from helius_agent.tools.vfs import BackendProtocol, LocalDiskBackend

logger = logging.getLogger(__name__)

# Global backend reference for the prototype
# In a full implementation, this would be part of the Agent's runtime/context
_CURRENT_BACKEND: BackendProtocol = LocalDiskBackend(root_dir=".", virtual_mode=True)


def set_backend(backend: BackendProtocol):
    global _CURRENT_BACKEND
    _CURRENT_BACKEND = backend


@tool
def ls(path: str = ".") -> str:
    """List files and directories in the given path."""
    try:
        infos = _CURRENT_BACKEND.ls_info(path)
        if not infos:
            return "No files found."
        
        lines = []
        for info in infos:
            prefix = "[DIR] " if info.is_dir else "      "
            size_str = f" ({info.size} bytes)" if info.size is not None else ""
            lines.append(f"{prefix}{info.path}{size_str}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing directory: {e}"


@tool
def read_file(path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """Read content of a file, optionally within a line range (1-indexed)."""
    try:
        limit = (end_line - start_line + 1) if end_line else 2000
        return _CURRENT_BACKEND.read(path, offset=start_line - 1, limit=limit)
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a new file. Fails if the file already exists."""
    try:
        result = _CURRENT_BACKEND.write(path, content)
        if result.error:
            return f"Error: {result.error}"
        return f"Successfully wrote to {result.path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool
def edit_file(
    path: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    """
    Replace text in a file. 
    By default, fails if 'old_string' is not unique in the file.
    """
    try:
        result = _CURRENT_BACKEND.edit(path, old_string, new_string, replace_all)
        if result.error:
            return f"Error: {result.error}"
        return f"Successfully updated {result.path} ({result.occurrences} occurrences replaced)."
    except Exception as e:
        return f"Error editing file: {e}"


@tool
def delete_file(path: str) -> str:
    """Delete a file or directory from the filesystem."""
    try:
        return _CURRENT_BACKEND.delete(path)
    except Exception as e:
        return f"Error deleting: {e}"


@tool
def insert_at_line(path: str, line_number: int, content: str) -> str:
    """
    Insert content at a specific line number (1-indexed).
    This is implemented as a surgical edit for safety.
    """
    try:
        # Read the entire file to find context
        # In a real system, we might only read a window
        full_content_numbered = _CURRENT_BACKEND.read(path, offset=0, limit=10000)
        if full_content_numbered.startswith("Error"):
            return full_content_numbered
            
        lines = [line.split("|", 1)[1][1:] if "|" in line else "" for line in full_content_numbered.splitlines()]
        
        if line_number < 1 or line_number > len(lines) + 1:
            return f"Error: Line {line_number} is out of range (1-{len(lines)+1})"
        
        if line_number <= len(lines):
            # Replacing a line with (new_content + original_line)
            # We use the original line as anchor
            anchor = lines[line_number - 1]
            new_val = content + ("\n" if not content.endswith("\n") else "") + anchor
            result = _CURRENT_BACKEND.edit(path, old_string=anchor, new_string=new_val)
        else:
            # Appending to end
            anchor = lines[-1]
            new_val = anchor + ("\n" if not anchor.endswith("\n") else "") + content
            result = _CURRENT_BACKEND.edit(path, old_string=anchor, new_string=new_val)
            
        if result.error:
            return f"Error applying insertion: {result.error}"
        return f"Successfully inserted content at line {line_number}"
    except Exception as e:
        return f"Error inserting at line: {e}"


@tool
def edit_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    Replace a range of lines (1-indexed, inclusive) with new content.
    Uses surgical edit for safety.
    """
    try:
        # Read the specific range to get the 'old_string'
        old_block_raw = _CURRENT_BACKEND.read(path, offset=start_line - 1, limit=end_line - start_line + 1)
        if old_block_raw.startswith("Error"):
            return old_block_raw
            
        # Strip the line numbers added by read()
        old_lines = [line.split("|", 1)[1][1:] if "|" in line else "" for line in old_block_raw.splitlines()]
        old_string = "\n".join(old_lines)
        
        result = _CURRENT_BACKEND.edit(path, old_string=old_string, new_string=new_content)
        if result.error:
            return f"Error applying line edit: {result.error}"
        return f"Successfully edited lines {start_line}-{end_line}"
    except Exception as e:
        return f"Error editing lines: {e}"


@tool
def grep_search(pattern: str, path: str = ".", glob: Optional[str] = None) -> str:
    """Search for a regex pattern in file contents."""
    try:
        results = _CURRENT_BACKEND.grep_raw(pattern, path, glob)
        if isinstance(results, str):
            return results  # Error message
        
        if not results:
            return "No matches found."
        
        lines = []
        for m in results:
            lines.append(f"{m.path}:{m.line}: {m.text}")
        return "\n".join(lines[:100])  # Limit output
    except Exception as e:
        return f"Error searching files: {e}"


__all__ = [
    "ls", 
    "read_file", 
    "write_file", 
    "edit_file", 
    "delete_file", 
    "insert_at_line", 
    "edit_lines", 
    "grep_search", 
    "set_backend"
]

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


@dataclass
class FileInfo:
    path: str
    is_dir: bool = False
    size: Optional[int] = None
    modified_at: Optional[str] = None


@dataclass
class GrepMatch:
    path: str
    line: int
    text: str


@dataclass
class WriteResult:
    path: str
    error: Optional[str] = None
    files_update: Optional[Dict[str, Any]] = None


@dataclass
class EditResult:
    path: str
    occurrences: int = 0
    error: Optional[str] = None
    files_update: Optional[Dict[str, Any]] = None


class BackendProtocol(ABC):
    @abstractmethod
    def ls_info(self, path: str) -> List[FileInfo]:
        pass

    @abstractmethod
    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        pass

    @abstractmethod
    def grep_raw(
        self, pattern: str, path: Optional[str] = None, glob: Optional[str] = None
    ) -> Union[List[GrepMatch], str]:
        pass

    @abstractmethod
    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        pass

    @abstractmethod
    def write(self, file_path: str, content: str) -> WriteResult:
        pass

    @abstractmethod
    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        pass


    @abstractmethod
    def delete(self, file_path: str) -> str:
        pass


class LocalDiskBackend(BackendProtocol):
    def __init__(self, root_dir: str = ".", virtual_mode: bool = True):
        self.root_dir = Path(root_dir).resolve()
        self.virtual_mode = virtual_mode

    def delete(self, file_path: str) -> str:
        p = self._safe_path(file_path)
        if not p.exists():
            return f"Error: '{file_path}' not found"
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
            return f"Deleted directory {file_path}"
        p.unlink()
        return f"Deleted file {file_path}"

    def _safe_path(self, path: str) -> Path:
        # Simplified safe path logic for prototype
        p = Path(path)
        if p.is_absolute():
            # If absolute, it must be within root_dir if virtual_mode is on
            if self.virtual_mode:
                try:
                    p.relative_to(self.root_dir)
                except ValueError:
                    # Not under root, join with root
                    return self.root_dir / p.relative_to(p.anchor)
            return p
        return (self.root_dir / p).resolve()

    def ls_info(self, path: str) -> List[FileInfo]:
        p = self._safe_path(path)
        if not p.exists():
            return []
        results = []
        for entry in p.iterdir():
            results.append(
                FileInfo(
                    path=str(entry.relative_to(self.root_dir)),
                    is_dir=entry.is_dir(),
                    size=entry.stat().st_size if entry.is_file() else None,
                )
            )
        return sorted(results, key=lambda x: x.path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        p = self._safe_path(file_path)
        if not p.exists() or not p.is_file():
            return f"Error: File '{file_path}' not found"
        
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        # Number the lines
        numbered = [f"{i+1:4} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered[offset : offset + limit])

    def grep_raw(
        self, pattern: str, path: Optional[str] = None, glob: Optional[str] = None
    ) -> Union[List[GrepMatch], str]:
        # Minimal implementation
        search_path = self._safe_path(path or ".")
        matches = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        for p in search_path.rglob("*"):
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8")
                    for i, line in enumerate(content.splitlines()):
                        if regex.search(line):
                            matches.append(
                                GrepMatch(
                                    path=str(p.relative_to(self.root_dir)),
                                    line=i + 1,
                                    text=line,
                                )
                            )
                except Exception:
                    continue
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        search_path = self._safe_path(path)
        results = []
        for p in search_path.glob(pattern):
            results.append(
                FileInfo(
                    path=str(p.relative_to(self.root_dir)),
                    is_dir=p.is_dir(),
                    size=p.stat().st_size if p.is_file() else None,
                )
            )
        return results

    def write(self, file_path: str, content: str) -> WriteResult:
        p = self._safe_path(file_path)
        if p.exists():
            return WriteResult(path=file_path, error="File already exists")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        p = self._safe_path(file_path)
        if not p.exists():
            return EditResult(path=file_path, error="File not found")
        
        content = p.read_text(encoding="utf-8")
        count = content.count(old_string)
        
        if count == 0:
            return EditResult(path=file_path, error="old_string not found")
        if count > 1 and not replace_all:
            return EditResult(path=file_path, error="old_string is ambiguous")
        
        new_content = content.replace(old_string, new_string)
        p.write_text(new_content, encoding="utf-8")
        return EditResult(path=file_path, occurrences=count)


class StateBackend(BackendProtocol):
    """Ephemeral backend stored in agent state."""
    def __init__(self, state_ref: Dict[str, str]):
        self.files = state_ref  # path -> content

    def ls_info(self, path: str) -> List[FileInfo]:
        path = path.rstrip("/") + "/" if path != "/" else "/"
        results = {}
        for fpath in self.files:
            if fpath.startswith(path):
                relative = fpath[len(path):].split("/")[0]
                if relative not in results:
                    results[relative] = FileInfo(
                        path=path + relative,
                        is_dir="/" in fpath[len(path):]
                    )
        return sorted(results.values(), key=lambda x: x.path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        if file_path not in self.files:
            return f"Error: File '{file_path}' not found"
        content = self.files[file_path]
        lines = content.splitlines()
        numbered = [f"{i+1:4} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered[offset : offset + limit])

    def grep_raw(self, pattern: str, path: Optional[str] = None, glob: Optional[str] = None) -> Union[List[GrepMatch], str]:
        matches = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        for fpath, content in self.files.items():
            if path and not fpath.startswith(path):
                continue
            for i, line in enumerate(content.splitlines()):
                if regex.search(line):
                    matches.append(GrepMatch(path=fpath, line=i+1, text=line))
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        # Very limited glob support for prototype
        import fnmatch
        results = []
        for fpath in self.files:
            if fnmatch.fnmatch(fpath, pattern):
                results.append(FileInfo(path=fpath, is_dir=False))
        return results

    def write(self, file_path: str, content: str) -> WriteResult:
        if file_path in self.files:
            return WriteResult(path=file_path, error="File already exists")
        self.files[file_path] = content
        return WriteResult(path=file_path, files_update={file_path: content})

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        if file_path not in self.files:
            return EditResult(path=file_path, error="File not found")
        content = self.files[file_path]
        count = content.count(old_string)
        if count == 0: return EditResult(path=file_path, error="not found")
        if count > 1 and not replace_all: return EditResult(path=file_path, error="ambiguous")
        
        new_content = content.replace(old_string, new_string)
        self.files[file_path] = new_content
        return EditResult(path=file_path, occurrences=count, files_update={file_path: new_content})


    def delete(self, file_path: str) -> str:
        if file_path in self.files:
            del self.files[file_path]
            return f"Deleted {file_path}"
        
        # Check if it's a "directory" (prefix)
        prefix = file_path.rstrip("/") + "/"
        to_delete = [f for f in self.files if f.startswith(prefix)]
        if to_delete:
            for f in to_delete:
                del self.files[f]
            return f"Deleted directory {file_path} and {len(to_delete)} files"
            
        return f"Error: {file_path} not found"


class StoreBackend(BackendProtocol):
    """
    Durable backend that persists across threads.
    In a real system, this uses LangGraph Store (Redis/Postgres).
    Here we use a JSON file for persistence.
    """
    def __init__(self, store_path: str = ".agent_store.json"):
        self.store_path = Path(store_path)
        self._load()

    def _load(self):
        if self.store_path.exists():
            import json
            try:
                self.files = json.loads(self.store_path.read_text(encoding="utf-8"))
            except:
                self.files = {}
        else:
            self.files = {}

    def _save(self):
        import json
        self.store_path.write_text(json.dumps(self.files, indent=2), encoding="utf-8")

    def ls_info(self, path: str) -> List[FileInfo]:
        # Reuse StateBackend logic for hierarchy
        temp_state = StateBackend(self.files)
        return temp_state.ls_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        if file_path not in self.files:
            return f"Error: File '{file_path}' not found"
        content = self.files[file_path]
        lines = content.splitlines()
        numbered = [f"{i+1:4} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered[offset : offset + limit])

    def grep_raw(self, pattern: str, path: Optional[str] = None, glob: Optional[str] = None) -> Union[List[GrepMatch], str]:
        temp_state = StateBackend(self.files)
        return temp_state.grep_raw(pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        temp_state = StateBackend(self.files)
        return temp_state.glob_info(pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        if file_path in self.files:
            return WriteResult(path=file_path, error="File already exists")
        self.files[file_path] = content
        self._save()
        return WriteResult(path=file_path)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        if file_path not in self.files:
            return EditResult(path=file_path, error="File not found")
        content = self.files[file_path]
        count = content.count(old_string)
        if count == 0: return EditResult(path=file_path, error="not found")
        if count > 1 and not replace_all: return EditResult(path=file_path, error="ambiguous")
        
        new_content = content.replace(old_string, new_string)
        self.files[file_path] = new_content
        self._save()
        return EditResult(path=file_path, occurrences=count)

    def delete(self, file_path: str) -> str:
        if file_path in self.files:
            del self.files[file_path]
            self._save()
            return f"Deleted {file_path}"
        return f"Error: {file_path} not found"


class CompositeBackend(BackendProtocol):
    def __init__(self, default: BackendProtocol, routes: Dict[str, BackendProtocol]):
        self.default = default
        self.routes = routes # prefix -> backend

    def delete(self, file_path: str) -> str:
        backend, p = self._get_backend(file_path)
        return backend.delete(p)

    def _get_backend(self, path: str) -> Tuple[BackendProtocol, str]:
        for prefix, backend in sorted(self.routes.items(), key=lambda x: len(x[0]), reverse=True):
            if path.startswith(prefix):
                # Optionally strip prefix if the backend expects relative paths
                return backend, path
        return self.default, path

    def ls_info(self, path: str) -> List[FileInfo]:
        backend, p = self._get_backend(path)
        return backend.ls_info(p)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        backend, p = self._get_backend(file_path)
        return backend.read(p, offset, limit)

    def grep_raw(self, pattern: str, path: Optional[str] = None, glob: Optional[str] = None) -> Union[List[GrepMatch], str]:
        if path:
            backend, p = self._get_backend(path)
            return backend.grep_raw(pattern, p, glob)
        # Aggregated search across all backends
        all_matches = []
        # Simplified: just search default for now
        return self.default.grep_raw(pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        backend, p = self._get_backend(path)
        return backend.glob_info(pattern, p)

    def write(self, file_path: str, content: str) -> WriteResult:
        backend, p = self._get_backend(file_path)
        return backend.write(p, content)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        backend, p = self._get_backend(file_path)
        return backend.edit(p, old_string, new_string, replace_all)

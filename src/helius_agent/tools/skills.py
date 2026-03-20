"""skills_tools.py — Thread-safe skill registry for a coding agent.

A "skill" is a named prompt snippet the agent can load into its context
to gain specialised guidance (e.g. "write idiomatic Rust", "follow project
conventions", "generate OpenAPI specs").
"""


import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    content: str
    tags: Tuple[str, ...] = field(default_factory=tuple)
    source_path: Optional[str] = None

    def summary(self) -> str:
        return f"- {self.name}: {self.description}"

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        description: str,
        content: str,
        tags: Optional[List[str]] = None,
        source_path: Optional[str] = None,
        overwrite: bool = False,
    ) -> None:
        with self._lock:
            if name in self._skills and not overwrite:
                return
            self._skills[name] = Skill(
                name=name,
                description=description,
                content=str(content),
                tags=tuple(tags or []),
                source_path=source_path,
            )

    def get(self, name: str) -> Optional[Skill]:
        with self._lock:
            return self._skills.get(name)

    def list_all(self) -> List[Skill]:
        with self._lock:
            return list(self._skills.values())

    def available_names(self) -> str:
        with self._lock:
            return ", ".join(sorted(self._skills.keys()))

_REGISTRY = SkillRegistry()

def _get_repo_root() -> Path:
    return Path(os.getenv("REPO_ROOT", ".")).resolve()

def _parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Extremely simple frontmatter parser (--- ... ---)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}, content
    
    fm_raw = match.group(1)
    body = content[match.end():]
    data = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
    return data, body

def load_skills_from_directory(directory: Path, overwrite: bool = False):
    if not directory.is_dir():
        return
    
    # Track which paths we've processed as subdirectories to avoid duplicate loading
    processed_subdirs = set()

    for p in directory.rglob("*"):
        if not p.is_file():
            continue
            
        if p.suffix.lower() not in [".md", ".txt"]:
            continue

        skill_name = p.stem
        raw = p.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(raw)
        
        # Determine skill name and description
        if "name" in fm:
            skill_name = fm["name"]
        elif p.name.lower() in ["skill.md", "readme.md", "agents.md"]:
            # Use parent directory name if it's a generic file name
            skill_name = p.parent.name
            if p.parent in processed_subdirs and p.name.lower() != "agents.md":
                # Favor AGENTS.md if multiple are present in same dir
                continue
            processed_subdirs.add(p.parent)

        if "description" in fm:
            description = fm["description"]
        else:
            description = next((ln.lstrip("#").strip() for ln in body.splitlines() if ln.strip()), f"Skill: {skill_name}")

        _REGISTRY.register(
            name=skill_name, 
            description=description, 
            content=raw, 
            source_path=str(p), 
            overwrite=overwrite
        )

# Auto-load from skills/ and agent-skills/skills/
repo_root = _get_repo_root()
load_skills_from_directory(repo_root / "skills")
load_skills_from_directory(repo_root / "agent-skills" / "skills")

# ---------------------------------------------------------------------------
# LangChain tools
# ---------------------------------------------------------------------------

@tool("list_skills")
def list_skills(query: Optional[str] = None) -> str:
    """List all available specialized skills (prompts) that can be loaded."""
    skills = _REGISTRY.list_all()
    if not skills: return "No skills registered."
    return "Available Skills:\n" + "\n".join(s.summary() for s in sorted(skills, key=lambda s: s.name))

@tool("load_skill")
def load_skill(skill_name: str) -> str:
    """
    Load a specialized skill's prompt and context into memory.
    Use this to get expert guidance on specific domains (SQL, React, etc).
    """
    skill = _REGISTRY.get(skill_name)
    if not skill:
        return f"Skill '{skill_name}' not found. Available: {_REGISTRY.available_names()}"
    return f"--- SKILL LOADED: {skill.name} ---\n{skill.content}\n--- END SKILL ---"

@tool("register_skill")
def register_skill(name: str, description: str, content: str) -> str:
    """Register a new specialized skill for future use."""
    try:
        _REGISTRY.register(name, description, content, overwrite=True)
        # Also persist to skills/ dir
        repo_root = _get_repo_root()
        skills_dir = repo_root / "skills"
        skills_dir.mkdir(exist_ok=True)
        (skills_dir / f"{name}.md").write_text(f"# {name}\n{description}\n\n{content}", encoding="utf-8")
        return f"Skill '{name}' registered and persisted successfully."
    except Exception as e:
        return f"Error registering skill: {e}"

__all__ = ["list_skills", "load_skill", "register_skill", "load_skills_from_directory"]

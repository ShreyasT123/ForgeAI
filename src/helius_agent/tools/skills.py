import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- Configuration & Security ---
WORKSPACE_ROOT = Path.cwd().resolve()
DEFAULT_SKILLS_DIR = WORKSPACE_ROOT / "skills"

# Search paths for progressive disclosure skills
SKILL_SEARCH_DIRS =[
    DEFAULT_SKILLS_DIR,
    WORKSPACE_ROOT / "agent-skills" / "skills",
    WORKSPACE_ROOT / ".helius-code" / "skills"
]

def _sanitize_name(name: str) -> str:
    """Sanitize skill names to prevent path traversal (e.g., ../../etc/passwd)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip()).strip("-")

def _get_skill_description(content: str, default_name: str) -> str:
    """Extract a brief description from the first non-empty line of the file."""
    for line in content.splitlines():
        line = line.strip()
        # Skip generic markdown headers or frontmatter delimiters
        if line and not line.startswith("---") and not line.startswith("# " + default_name):
            return line.lstrip("#").strip()
    return f"Domain knowledge for {default_name}"


# --- 1. LIST SKILLS TOOL ---
class ListSkillsArgs(BaseModel):
    query: Optional[str] = Field(default=None, description="Optional search query to filter skills.")

@tool(args_schema=ListSkillsArgs)
def list_skills(query: Optional[str] = None) -> str:
    """
    List all available specialized skills (prompts) that can be loaded.
    Use this to discover available domain expertise (e.g., SQL, React, Rust conventions).
    """
    found_skills =[]
    processed_names = set()

    for directory in SKILL_SEARCH_DIRS:
        if not directory.is_dir():
            continue
            
        for p in directory.rglob("*.md"):
            if not p.is_file():
                continue
                
            skill_name = p.stem
            if skill_name in processed_names:
                continue
                
            content = p.read_text(encoding="utf-8", errors="ignore")
            description = _get_skill_description(content, skill_name)
            
            # Filter if query is provided
            if query and query.lower() not in skill_name.lower() and query.lower() not in description.lower():
                continue
                
            processed_names.add(skill_name)
            found_skills.append(f"- {skill_name}: {description[:100]}...")

    if not found_skills:
        return "No skills currently registered or found."
        
    return "Available Specialized Skills:\n" + "\n".join(sorted(found_skills))


# --- 2. LOAD SKILL TOOL ---
class LoadSkillArgs(BaseModel):
    skill_name: str = Field(..., description="The exact name of the skill to load (without .md extension).")

@tool(args_schema=LoadSkillArgs)
def load_skill(skill_name: str) -> str:
    """
    Load a specialized skill's instructions into memory.
    Use this to gain strict project guidelines BEFORE generating code.
    """
    safe_name = _sanitize_name(skill_name)
    
    for directory in SKILL_SEARCH_DIRS:
        target = directory / f"{safe_name}.md"
        if target.is_file():
            try:
                content = target.read_text(encoding="utf-8")
                return f"--- SKILL LOADED: {safe_name} ---\n{content}\n--- END SKILL ---"
            except Exception as e:
                return f"Error reading skill file: {str(e)}"
                
    return f"Error: Skill '{skill_name}' not found. Run `list_skills` to see available options."


# --- 3. REGISTER SKILL TOOL ---
class RegisterSkillArgs(BaseModel):
    name: str = Field(..., description="A short, slugified name for the skill (e.g., 'react-hooks').")
    description: str = Field(..., description="A 1-sentence summary of what this skill teaches.")
    content: str = Field(..., description="The full markdown instructions/prompt for the skill.")

@tool(args_schema=RegisterSkillArgs)
def register_skill(name: str, description: str, content: str) -> str:
    """
    Register a new specialized skill for future use.
    Saves domain knowledge to the repository so you (and future agents) can reload it later.
    """
    try:
        safe_name = _sanitize_name(name)
        if not safe_name:
            return "Error: Invalid skill name provided."

        DEFAULT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        target = DEFAULT_SKILLS_DIR / f"{safe_name}.md"
        
        # Format the file with a clear header so list_skills can parse it cleanly
        formatted_content = f"# {safe_name}\n{description}\n\n{content}"
        
        target.write_text(formatted_content, encoding="utf-8")
        return f"Successfully registered and persisted skill '{safe_name}' at {target.relative_to(WORKSPACE_ROOT)}."
        
    except Exception as e:
        return f"Error registering skill: {str(e)}"

# Bundle for DeepAgents
SKILLS_TOOLS =[list_skills, load_skill, register_skill]
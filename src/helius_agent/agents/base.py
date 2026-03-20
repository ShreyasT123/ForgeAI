from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from helius_agent.agents.notes_middleware import NotesSystemPromptMiddleware


class Provider(str, Enum):
    MISTRAL = "mistral"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class AgentMode(str, Enum):
    FAST = "fast"
    DEEP = "deep"


class TodoListMiddleware:
    """Injects the current todo list into the system prompt."""
    def apply_to_system_prompt(self, system_prompt: str) -> str:
        from helius_agent.tools.planning import list_todos
        todos = list_todos.invoke({})
        if "No tasks found" in todos or "empty" in todos:
            return system_prompt
            
        planning_block = (
            "\n\n--- CURRENT PLANNING STATE ---\n"
            "The following is your current to-do list. Use 'write_todos' to update it as you progress.\n"
            f"{todos}\n"
            "------------------------------\n"
        )
        return system_prompt + planning_block


@dataclass
class ThinkingConfig:
    type: str = "enabled"
    budget_tokens: int = 1024


@dataclass
class SubAgentConfig:
    name: str
    description: str
    system_prompt: str
    tools: Sequence = field(default_factory=list)
    model: Optional[str] = None


def default_system_prompt() -> str:
    return (
        "You are a careful coding assistant with access to a library of specialized skills. "
        "Use 'list_skills' to discover available expertise (e.g., SQL, React, etc.) "
        "and 'load_skill' to ingest specialized guidelines and domain knowledge only when needed. "
        "This keeps your context window focused and efficient (Progressive Disclosure). "
        "Make minimal, well-scoped changes and explain your intent."
    )


@dataclass
class AgentConfig:
    model: str
    provider: Provider = Provider.MISTRAL
    mode: AgentMode = AgentMode.FAST
    temperature: float = 0.0
    tools: Sequence = field(default_factory=list)
    middleware: List[Any] = field(default_factory=list)
    subagents: List[SubAgentConfig] = field(default_factory=list)
    thinking: Optional[ThinkingConfig] = None
    system_prompt: str = field(default_factory=default_system_prompt)
    include_notes_in_system_prompt: bool = True
    provider_kwargs: Dict[str, Any] = field(default_factory=dict)


def _get_llm(config: AgentConfig):
    """Factory to get the appropriate LLM based on provider."""
    kwargs = config.provider_kwargs.copy()
    if config.thinking and config.provider == Provider.ANTHROPIC:
        kwargs["thinking"] = {
            "type": config.thinking.type,
            "budget_tokens": config.thinking.budget_tokens,
        }

    if config.provider == Provider.MISTRAL:
        from langchain_mistralai import ChatMistralAI
        return ChatMistralAI(
            model=config.model, 
            temperature=config.temperature, 
            **kwargs
        )
    elif config.provider == Provider.OPENAI:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.model, 
            temperature=config.temperature, 
            **kwargs
        )
    elif config.provider == Provider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=config.model, 
            temperature=config.temperature, 
            **kwargs
        )
    elif config.provider == Provider.GEMINI:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.model, 
            temperature=config.temperature, 
            **kwargs
        )
    else:
        raise ValueError(f"Unsupported provider: {config.provider}")


def build_agent(config: AgentConfig):
    """Build a LangChain agent from a minimal config.

    This is a thin wrapper to keep agent wiring centralized as the codebase evolves.
    """
    from langchain.agents import create_agent
    
    # In a real deepagents implementation, we would use create_deep_agent
    # Since we are building our own harness, we emulate the middleware injection
    
    llm = _get_llm(config)
    system_prompt = config.system_prompt
    
    if config.include_notes_in_system_prompt:
        system_prompt = NotesSystemPromptMiddleware().apply_to_system_prompt(
            system_prompt
        )
        
    middleware = list(config.middleware)
    
    if config.mode == AgentMode.DEEP:
        # Apply planning middleware
        system_prompt = TodoListMiddleware().apply_to_system_prompt(system_prompt)
        
        # Add planning and subagent tools if not already present
        from helius_agent.tools.planning import write_todos, list_todos
        from helius_agent.tools.subagents import task
        
        extra_tools = [write_todos, list_todos, task]
        current_tool_names = {getattr(t, "name", str(t)) for t in config.tools}
        for t in extra_tools:
            if getattr(t, "name", str(t)) not in current_tool_names:
                config.tools = list(config.tools) + [t]

    return create_agent(
        model=llm,
        tools=list(config.tools),
        system_prompt=system_prompt,
        middleware=middleware,
    )


__all__ = [
    "AgentConfig", 
    "build_agent", 
    "default_system_prompt", 
    "Provider", 
    "AgentMode", 
    "ThinkingConfig",
    "SubAgentConfig"
]

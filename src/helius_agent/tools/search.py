"""
search_tools.py

Provides agent-invokable search tools with support for:
- Tavily API
- SerpAPI
- Optionally call both

Features:
- Normalizes arguments for tool calls
- Returns structured search results
- Can be used directly in LangChain agent tools list
"""

import os
import requests
from typing import Dict, Any, List

def _get_tool():
    try:
        from langchain_core.tools import tool as lc_tool
        return lc_tool
    except Exception:
        try:
            from langchain.tools import tool as lc_tool  # type: ignore
            return lc_tool
        except Exception:
            def _noop_tool(*_args, **_kwargs):
                def decorator(func):
                    return func
                return decorator
            return _noop_tool

tool = _get_tool()

def _toolify(func, args_schema=None, name: str | None = None):
    try:
        t = tool(name=name, args_schema=args_schema)(func)
        if not hasattr(t, "invoke"):
            raise AttributeError("tool has no invoke")
        func.invoke = t.invoke  # type: ignore[attr-defined]
        func.name = getattr(t, "name", func.__name__)  # type: ignore[attr-defined]
        func.description = getattr(t, "description", "")  # type: ignore[attr-defined]
        return t
    except Exception:
        class _SimpleTool:
            def __init__(self, f, tool_name: str):
                self._f = f
                self.name = tool_name
                self.description = f.__doc__ or ""
            def invoke(self, inputs):
                if isinstance(inputs, dict):
                    return self._f(**inputs)
                return self._f(inputs)
            def __call__(self, *args, **kwargs):
                return self._f(*args, **kwargs)
        t = _SimpleTool(func, name or func.__name__)
        func.invoke = t.invoke  # type: ignore[attr-defined]
        func.name = t.name  # type: ignore[attr-defined]
        func.description = t.description  # type: ignore[attr-defined]
        return t


# ==================== Helper functions ====================


def _tavily_search(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set in environment")

    url = "https://api.tavily.com/v1/search"
    payload = {"query": query, "limit": limit}
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("results", [])[:limit]:
        results.append(
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet"),
            }
        )
    return results


def _serpapi_search(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        raise RuntimeError("SERPAPI_KEY not set in environment")

    url = "https://serpapi.com/search"
    params = {"q": query, "num": limit, "api_key": api_key}

    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("organic_results", [])[:limit]:
        results.append(
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet", ""),
            }
        )
    return results


# ==================== Agent-invokable tool ====================


def search(query: str, engine: str = "all", limit: int = 3) -> str:
    """Search the web using Tavily, SerpAPI, or both.

    Args:
        query: Search query string
        engine: "tavily", "serpapi", or "all" (default: all)
        limit: Number of results per engine (default: 3)

    Returns:
        JSON string of results, each result contains title, link, snippet
    """
    engines = []
    engine = engine.lower()
    if engine == "all":
        engines = ["tavily", "serpapi"]
    elif engine in ["tavily", "serpapi"]:
        engines = [engine]
    else:
        return (
            f"Error: Unsupported engine '{engine}'. Use 'tavily', 'serpapi', or 'all'."
        )

    combined_results = {}

    for eng in engines:
        try:
            if eng == "tavily":
                combined_results["tavily"] = _tavily_search(query, limit)
            elif eng == "serpapi":
                combined_results["serpapi"] = _serpapi_search(query, limit)
        except Exception as e:
            combined_results[eng] = f"Error: {str(e)}"

    import json

    return json.dumps(combined_results, indent=2)


search_tool = _toolify(search, name="search")


# ==================== Example usage ====================
if __name__ == "__main__":
    # Example: search with both engines
    q = "LangChain observability tools"
    print(search(q, engine="all", limit=2))

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
from typing import Optional, Dict, Any, List
from langchain.tools import tool


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


@tool
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


# ==================== Example usage ====================
if __name__ == "__main__":
    # Example: search with both engines
    q = "LangChain observability tools"
    print(search(q, engine="all", limit=2))

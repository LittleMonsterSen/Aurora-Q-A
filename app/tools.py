import json
from typing import Any, Dict, List
import os
from mem0 import MemoryClient
from app.name_index import load_names_index, resolve_with_index
# from .memory_agent import resolve_user_id_indexed, MemoryAgent, list_users
# from .name_index import load_names_index, norm_name



def tool_defs() -> List[Dict[str, Any]]:
    """
    Return two function tools for LLM tool-calling:
    1) search_user_memory: resolve full/partial name and search mem0-backed memory for a specific user_id.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "search_user_memory",
                "description": "Search a member's mem0-backed memory for relevant snippets.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Target user's name"},
                        "query": {"type": "string", "description": "Natural-language question"},
                        "top_k": {"type": "integer", "description": "Number of results", "default": 12},
                    },
                    "required": ["name", "query"],
                },
            },
        },
    ]


class ToolsDispatcher:
    def __init__(self) -> None:
        self.agent = MemoryClient(api_key = os.getenv("MEM0_API_KEY"))

    async def call(self, name: str, arguments_json: str, original_question: str = "") -> str:
        args = json.loads(arguments_json or "{}")
                
        if name == "search_user_memory":
            user_name = args.get("name") or ""
            if not user_name:
                return json.dumps({"error": "Please provide user name"})
            idx = load_names_index()
            if not idx:
                return json.dumps({"error": "Names index not available"})
            user_id = resolve_with_index(user_name, idx)
            if not user_id:
                return json.dumps({"error": "user cannot be found in database, please use another name"})
            # Ensure user_id is a string (resolve_with_index might return tuple per type hint, but actually returns str)
            if isinstance(user_id, tuple):
                user_id = user_id[0] if user_id else ""
            if not isinstance(user_id, str) or not user_id:
                return json.dumps({"error": "Invalid user_id resolved from name"})
            # Use the original question as the search query
            query = original_question or args.get("query") or ""
            top_k = int(args.get("top_k") or 10)
            if not query:
                return json.dumps({"error": "query is required"})
            try:
                filters = {
                    "OR": [
                        {"user_id": user_id}
                    ]
                }
                results = self.agent.search(
                    query,
                    version="v2",
                    filters=filters,
                    top_k=50,
                    rerank=True,
                )
            except Exception as e:
                error_msg = str(e)
                if "400" in error_msg or "Bad Request" in error_msg:
                    return json.dumps({"error": f"API request invalid: {error_msg}"})
                return json.dumps({"error": f"Search failed: {error_msg}"})
            
            # Extract results list from response: {'results': [...]}
            results_list = results.get("results", []) if isinstance(results, dict) else []
            if results_list:
                results_list.sort(key=lambda x: x.get("metadata", {}).get("timestamp", 0), reverse=True)
                results_list = results_list[:top_k]
            
            items: List[Dict[str, Any]] = []
            for r in results_list:
                text = r.get("memory", "")
                meta = r.get("metadata", {})
                # Include score and categories if available
                # if "score" in r:
                #     meta["score"] = r["score"]
                # if "categories" in r:
                #     meta["categories"] = r["categories"]
                items.append({"messages": text, "metadata": meta.get("timestamp")})
            
            return json.dumps({"items": items})

        return json.dumps({"error": f"unknown tool {name}"})

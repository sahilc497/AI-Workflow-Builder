"""
Remaining node plugins:
  WebSearchNode  – Tavily web search
  LLMNode        – Mistral / any LiteLLM prompt
  ExtractDataNode – pull a key from a previous node's dict/list result
  TimeNode        – return current timestamp
"""
import json
import os
import urllib.request
from .base import BaseNode


# ── WEB_SEARCH ─────────────────────────────────────────────────────────────

class WebSearchNode(BaseNode):
    node_type = "WEB_SEARCH"

    def validate(self, params: dict) -> None:
        if not os.getenv("TAVILY_API_KEY"):
            raise ValueError("TAVILY_API_KEY environment variable is not set.")

    def execute(self, params: dict, context: dict) -> str:
        api_key = os.getenv("TAVILY_API_KEY")
        query = params.get("query")
        if not query:
            ref = params.get("query_ref")
            if ref and ref in context:
                query = str(context[ref])
        if not query:
            return "WEB_SEARCH: 'query' parameter is required."

        payload = json.dumps({
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "include_answer": True
        }).encode("utf-8")
        req = urllib.request.Request("https://api.tavily.com/search", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results", [])
        if not results:
            return f"No search results found for: '{query}'"
        lines = [f"Search Results for '{query}':"]
        for r in results[:8]:
            lines.append(f"- {r.get('title')} ({r.get('url')}):\n  {r.get('content')}")
        return "\n\n".join(lines)


# ── LLM_PROMPT ─────────────────────────────────────────────────────────────

class LLMNode(BaseNode):
    node_type = "LLM_PROMPT"

    def execute(self, params: dict, context: dict) -> str:
        try:
            from backend.agents import get_llm
            llm = get_llm()
            prompt = params.get("prompt") or params.get("prompt_template", "")

            # Replace {{key}} placeholders from context
            input_key = params.get("input_data_key")
            if input_key and input_key in context:
                prompt = prompt.replace(f"{{{{{input_key}}}}}", str(context[input_key]))
                prompt += f"\n\nContext Data:\n{context[input_key]}"

            for key, val in context.items():
                prompt = prompt.replace(f"{{{{{key}.output}}}}", str(val))
                prompt = prompt.replace(f"{{{{{key}}}}}", str(val))

            response = llm.call(messages=[{"role": "user", "content": prompt}])
            return response
        except Exception as e:
            return f"LLM Error: {str(e)}"


# ── EXTRACT_DATA ───────────────────────────────────────────────────────────

class ExtractDataNode(BaseNode):
    node_type = "EXTRACT_DATA"

    def execute(self, params: dict, context: dict):
        data_ref = params.get("data_ref") or params.get("input_data_key")
        key = params.get("key_to_extract") or params.get("key")

        # Auto-detect the first dict/list in context if ref not given
        if not data_ref or data_ref not in context:
            for k, v in context.items():
                if isinstance(v, (dict, list)):
                    data_ref = k
                    break

        if not data_ref or data_ref not in context:
            return f"EXTRACT_DATA: source '{data_ref}' not found in context."

        data = context[data_ref]

        # If data is a string, try to parse as JSON first
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                if isinstance(parsed, (dict, list)):
                    data = parsed
            except:
                pass

        if isinstance(data, list):
            item = data[0] if data else None
            if isinstance(item, dict) and key:
                return item.get(key, "Key not found")
            return item if item is not None else "Empty list"
        if isinstance(data, dict):
            if key:
                return data.get(key, "Key not found")
            return data
        return data


# ── TIME ────────────────────────────────────────────────────────────────────

class TimeNode(BaseNode):
    node_type = "TIME"

    def execute(self, params: dict, context: dict) -> str:
        from datetime import datetime
        return f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

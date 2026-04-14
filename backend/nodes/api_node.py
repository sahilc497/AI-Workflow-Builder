"""
APINode  – Performs an HTTP GET to verify a URL / call a REST endpoint.
"""
import urllib.request
import urllib.error
from .base import BaseNode


class APINode(BaseNode):
    node_type = "API_CALL"

    def execute(self, params: dict, context: dict) -> str:
        url = params.get("endpoint") or params.get("url")
        if not url:
            return "API_CALL: no URL provided."
        if not url.startswith("http"):
            url = "https://" + url
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return f"Website {url} is Online (Status: {resp.status})"
        except urllib.error.URLError as e:
            return f"Website {url} is DOWN! (Error: {getattr(e, 'reason', str(e))})"
        except Exception as e:
            return f"API_CALL to {url} failed: {str(e)}"

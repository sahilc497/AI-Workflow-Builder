"""
NODE_REGISTRY – Maps action type strings → node plugin classes.

To add a new node type:
  1. Create your class in a new file (inherit from BaseNode)
  2. Import it here
  3. Add an entry to NODE_REGISTRY

That's it — the execution engine picks it up automatically.
"""
from .base import BaseNode
from .api_node import APINode
from .email_node import EmailNode
from .github_node import GitHubPRNode, GitHubAPICallNode, GitHubActionNode
from .misc_nodes import WebSearchNode, LLMNode, ExtractDataNode, TimeNode
from .desktop_nodes import (DesktopAppNode, CreateDocumentNode,
                            CreateSpreadsheetNode, CreatePresentationNode,
                            BrowserActionNode)
from .whatsapp_node import WhatsAppNode
from .gui_node import GUIAutomationNode, AppControlNode

NODE_REGISTRY: dict[str, type[BaseNode]] = {
    # HTTP / API
    "API_CALL":               APINode,

    # Messaging
    "EMAIL":                  EmailNode,
    "EMAIL_MESSAGE":          EmailNode,          # alias

    # GitHub
    "GITHUB_PR":              GitHubPRNode,
    "GITHUB_API_CALL":        GitHubAPICallNode,
    "GITHUB_ACTION":          GitHubActionNode,

    # Search & AI
    "WEB_SEARCH":             WebSearchNode,
    "LLM_PROMPT":             LLMNode,

    # Utilities
    "EXTRACT_DATA":           ExtractDataNode,
    "TIME":                   TimeNode,
    "GET_TIME":               TimeNode,           # alias
    "SYSTEM_CALL":            TimeNode,           # alias

    # Desktop / Office
    "DESKTOP_APP":            DesktopAppNode,
    "CREATE_DOCUMENT":        CreateDocumentNode,
    "CREATE_SPREADSHEET":     CreateSpreadsheetNode,
    "CREATE_PRESENTATION":    CreatePresentationNode,
    "BROWSER_ACTION":         BrowserActionNode,

    # WhatsApp
    "WHATSAPP_MESSAGE":       WhatsAppNode,

    # GUI / PC Automation
    "GUI_AUTOMATION":         GUIAutomationNode,
    "APP_CONTROL":            AppControlNode,
}


def get_node(action: str) -> BaseNode | None:
    """
    Look up and instantiate a node plugin from the registry.

    Returns:
        An instantiated BaseNode subclass, or None if action is unknown.
    """
    # Direct match first
    cls = NODE_REGISTRY.get(action.upper()) or NODE_REGISTRY.get(action)
    if cls:
        return cls()
        
    # Handle composite actions passed by the LLM (e.g. "TIME/GET_TIME")
    for part in action.upper().split("/"):
        part = part.strip()
        cls = NODE_REGISTRY.get(part)
        if cls:
            return cls()
            
    return None

__all__ = ["BaseNode", "NODE_REGISTRY", "get_node"]

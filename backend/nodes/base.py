"""
Plugin Node Architecture – Base class and registry loader.

Every node plugin must:
  1. Inherit from BaseNode
  2. Implement execute(self, params: dict, context: dict) -> str
  3. Register itself in NODE_REGISTRY

Adding a new node type = create a new file in backend/nodes/ and add it to NODE_REGISTRY.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseNode(ABC):
    """Abstract base class for all workflow node plugins."""

    # Subclasses may set a human-readable name for logging
    node_type: str = "UNKNOWN"
    
    # Risk level: LOW, MEDIUM, or HIGH
    risk_level: str = "LOW"

    @abstractmethod
    def execute(self, params: dict, context: dict) -> Any:
        """
        Execute the node action.

        Args:
            params:  The node's own param dict from the DAG JSON.
            context: Results of all previously executed nodes,
                     keyed by node_id.

        Returns:
            Any serialisable result (str, dict, list, …).
        """

    # ── Optional hooks ────────────────────────────────────────────────────

    def validate(self, params: dict) -> None:
        """
        Called before execute(). Raise ValueError to abort the node
        with a clean error message rather than a raw exception.
        Override in subclasses to add param validation.
        """

    def __repr__(self) -> str:
        return f"<Node:{self.node_type}>"

"""Dependency-free RAG agent with HTTP and MCP interfaces."""

from .agent import KnowledgeAgent
from .store import KnowledgeStore

__all__ = ["KnowledgeAgent", "KnowledgeStore"]
__version__ = "0.1.0"

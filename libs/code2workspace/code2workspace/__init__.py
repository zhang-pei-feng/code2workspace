"""Code2Workspace package."""

from code2workspace._version import __version__
from code2workspace.graph import create_workspace_agent
from code2workspace.middleware.async_subagents import AsyncSubAgent, AsyncSubAgentMiddleware
from code2workspace.middleware.filesystem import FilesystemMiddleware
from code2workspace.middleware.memory import MemoryMiddleware
from code2workspace.middleware.permissions import FilesystemPermission
from code2workspace.middleware.subagents import CompiledSubAgent, SubAgent, SubAgentMiddleware

__all__ = [
    "AsyncSubAgent",
    "AsyncSubAgentMiddleware",
    "CompiledSubAgent",
    "FilesystemMiddleware",
    "FilesystemPermission",
    "MemoryMiddleware",
    "SubAgent",
    "SubAgentMiddleware",
    "__version__",
    "create_workspace_agent",
]

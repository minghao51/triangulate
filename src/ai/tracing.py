"""LangSmith tracing configuration for LangGraph workflows.

Enable tracing by setting environment variables:
    LANGSMITH_API_KEY=<your-api-key>
    LANGSMITH_TRACING=true
    LANGSMITH_PROJECT=triangulate  # optional
"""

import os
from functools import wraps
from typing import Any, Callable

logger = __import__("logging").getLogger(__name__)

_tracing_enabled = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
_has_api_key = bool(os.getenv("LANGSMITH_API_KEY"))


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is configured and enabled."""
    return _tracing_enabled and _has_api_key


def init_tracing(project_name: str = "triangulate") -> None:
    """Initialize LangSmith tracing.
    
    This is called automatically when the module is imported.
    LangGraph automatically picks up LANGSMITH_* environment variables.
    """
    if is_tracing_enabled():
        logger.info(
            f"LangSmith tracing enabled for project: "
            f"{os.getenv('LANGSMITH_PROJECT', project_name)}"
        )
    else:
        if not _has_api_key:
            logger.debug("LANGSMITH_API_KEY not set - tracing disabled")
        if not _tracing_enabled:
            logger.debug("LANGSMITH_TRACING not set to 'true' - tracing disabled")


def traceable(
    name: str | None = None,
    tags: list[str] | None = None,
) -> Callable:
    """Decorator to mark a function as a traceable LangSmith span.
    
    Usage:
        @traceable(name="custom_span")
        async def my_agent(...):
            ...
    
    Note: LangGraph nodes are automatically traced when tracing is enabled.
    This decorator is useful for custom functions outside the graph.
    """
    try:
        from langsmith import traceable as langsmith_traceable
        return langsmith_traceable(name=name, tags=tags)
    except ImportError:
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                return await func(*args, **kwargs)
            return wrapper
        return decorator


init_tracing()

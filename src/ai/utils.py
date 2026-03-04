"""Utility functions for LLM API calls with retry logic.

Implements Alibaba Model Studio best practices for 2026:
- Exponential backoff for rate limiting (429)
- Retry for 408, 500, 502, 503, 504
- Fail-fast for 401, 403 (auth errors)
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine
import os

logger = logging.getLogger(__name__)


# Status codes that should trigger retry
RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Status codes that should fail immediately (no retry)
FAIL_FAST_STATUS_CODES = {401, 403}


async def call_with_retry(
    func: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    **kwargs: Any,
) -> Any:
    """Call an async function with exponential backoff retry logic.

    Implements Alibaba Model Studio best practices for retry logic:
    - Retries on 408, 429, 500, 502, 503, 504 with exponential backoff
    - Fails immediately on 401, 403 (authentication errors)
    - Uses exponential backoff: initial_delay * (2 ** attempt)

    Args:
        func: Async function to call
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        Exception: If all retries fail or fail-fast error occurs
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Check for fail-fast errors (authentication)
            if any(
                code in error_str
                for code in ["401", "403", "unauthorized", "forbidden"]
            ):
                logger.error(f"Authentication error - failing fast: {e}")
                raise

            # Check for retryable errors
            is_retryable = any(
                str(code) in error_str for code in RETRY_STATUS_CODES
            ) or any(
                phrase in error_str
                for phrase in [
                    "rate limit",
                    "timeout",
                    "server error",
                    "service unavailable",
                ]
            )

            if is_retryable and attempt < max_retries - 1:
                # Exponential backoff
                wait_time = initial_delay * (2**attempt)
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}/{max_retries}: {e}. "
                    f"Retrying in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                # Not retryable or out of retries
                logger.error(f"Error in API call after {attempt + 1} attempts: {e}")
                raise

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected error in retry logic")


def get_llm_config() -> dict[str, Any]:
    """Get LLM configuration from environment variables.

    Returns:
        Dictionary with model, api_key, base_url, and provider settings
    """
    model = os.getenv("LLM_MODEL", "qwen-plus")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")

    if not api_key:
        logger.warning("LLM_API_KEY not set")

    config = {
        "model": model,
        "api_key": api_key,
    }

    # Add base_url and provider if using custom endpoint
    if base_url:
        config["base_url"] = base_url
        config["custom_llm_provider"] = "openai"

    return config


def build_completion_params(
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    **kwargs,
) -> dict[str, Any]:
    """Build completion parameters with best practices defaults.

    Args:
        messages: Chat messages for the LLM
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens in response
        **kwargs: Additional parameters

    Returns:
        Dictionary of completion parameters
    """
    params = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **kwargs,
    }

    # Add auth and endpoint config
    params.update(get_llm_config())

    return params

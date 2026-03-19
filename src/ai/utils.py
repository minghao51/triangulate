"""Utility functions for LLM API calls with retry logic.

Implements Alibaba Model Studio best practices for 2026:
- Exponential backoff for rate limiting (429)
- Retry for 408, 500, 502, 503, 504
- Fail-fast for 401, 403 (auth errors)
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Type
import os
from dotenv import load_dotenv
from litellm import acompletion
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# Load local .env early so LLM settings are available in scripts/CLI runs.
load_dotenv()

# Status codes that should trigger retry
RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Status codes that should fail immediately (no retry)
FAIL_FAST_STATUS_CODES = {401, 403}

# Retryable error phrases
RETRYABLE_PHRASES = {
    "rate limit",
    "timeout",
    "server error",
    "service unavailable",
    "too many requests",
    "request failed",
    "connection error",
    "empty response",
}


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
            fail_fast_markers = [
                *(str(code) for code in FAIL_FAST_STATUS_CODES),
                "unauthorized",
                "forbidden",
            ]
            if any(code in error_str for code in fail_fast_markers):
                logger.error(f"Authentication error - failing fast: {e}")
                raise

            # Check for retryable errors
            is_retryable = any(
                str(code) in error_str for code in RETRY_STATUS_CODES
            ) or any(
                phrase in error_str
                for phrase in RETRYABLE_PHRASES
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
    llm_config: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Build completion parameters with best practices defaults.

    Args:
        messages: Chat messages for the LLM
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens in response
        llm_config: Optional config overrides for model/provider/auth settings
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
    if llm_config:
        params.update({key: value for key, value in llm_config.items() if value is not None})

    return params


def extract_json_payload(content: str) -> Any:
    """Extract a JSON payload from raw model content."""
    if not isinstance(content, str):
        return content

    stripped = content.strip()
    if not stripped:
        raise json.JSONDecodeError("Empty content", stripped, 0)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    for fence in ("```json", "```"):
        if fence in stripped:
            try:
                json_str = stripped.split(fence, 1)[1].split("```", 1)[0].strip()
                return json.loads(json_str)
            except (IndexError, json.JSONDecodeError):
                continue

    start_index = -1
    for marker in ("{", "["):
        idx = stripped.find(marker)
        if idx != -1 and (start_index == -1 or idx < start_index):
            start_index = idx
    if start_index != -1:
        candidate = stripped[start_index:]
        for end_char in ("}", "]"):
            end_index = candidate.rfind(end_char)
            if end_index != -1:
                try:
                    return json.loads(candidate[: end_index + 1])
                except json.JSONDecodeError:
                    continue

    raise json.JSONDecodeError("Unable to extract JSON", stripped, 0)


async def call_structured_llm(
    prompt: str,
    schema: Type[BaseModel],
    *,
    config: dict[str, Any] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    fallback: Callable[[], Any] | None = None,
    system_prompt: str | None = None,
    completion_func: Callable[..., Coroutine[Any, Any, Any]] | None = None,
) -> dict[str, Any]:
    """Call the LLM and parse the response into a typed schema by default."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {
            "role": "user",
            "content": (
                f"{prompt}\n\nReturn a JSON object that matches this schema exactly:\n"
                f"{json.dumps(schema.model_json_schema(), indent=2)}"
            ),
        }
    )

    params = build_completion_params(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        llm_config=config,
        response_format={"type": "json_object"},
    )

    raw_content = ""
    parse_status = "ok"
    fallback_used = False
    try:
        response = await call_with_retry(completion_func or acompletion, **params)
        raw_content = response.get("choices", [{}])[0].get("message", {}).get(
            "content", ""
        )
        payload = extract_json_payload(raw_content)
        parsed = schema.model_validate(payload)
        return {
            "output": parsed.model_dump(),
            "parse_status": parse_status,
            "structured_output_used": True,
            "fallback_used": fallback_used,
            "raw_response_excerpt": raw_content[:400],
        }
    except (json.JSONDecodeError, ValidationError, Exception) as exc:
        logger.warning("Structured LLM call failed for %s: %s", schema.__name__, exc)
        parse_status = "fallback"
        if fallback is None:
            raise
        fallback_used = True
        fallback_output = fallback()
        if isinstance(fallback_output, BaseModel):
            fallback_output = fallback_output.model_dump()
        return {
            "output": fallback_output,
            "parse_status": parse_status,
            "structured_output_used": True,
            "fallback_used": fallback_used,
            "raw_response_excerpt": raw_content[:400],
        }


def make_agent_envelope(
    output: Any,
    *,
    parse_status: str = "ok",
    structured_output_used: bool = True,
    fallback_used: bool = False,
    raw_response_excerpt: str = "",
) -> dict[str, Any]:
    """Create a normalized agent result envelope."""
    return {
        "output": output,
        "parse_status": parse_status,
        "structured_output_used": structured_output_used,
        "fallback_used": fallback_used,
        "raw_response_excerpt": raw_response_excerpt,
    }


async def call_llm(
    prompt: str,
    response_format: str = "text",
    config: dict[str, Any] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> Any:
    """Call LLM with a prompt and return response.

    This is a convenience wrapper around build_completion_params and call_with_retry.

    Args:
        prompt: The prompt to send to the LLM
        response_format: Expected response format ("text" or "json")
        config: Optional configuration dictionary (uses defaults if None)
        temperature: Sampling temperature
        max_tokens: Maximum tokens in response

    Returns:
        LLM response (text string or parsed JSON object)
    """
    from litellm import acompletion

    if config is None:
        config = {}

    messages = [{"role": "user", "content": prompt}]

    # Build parameters
    params = build_completion_params(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        llm_config=config,
    )

    # Add response format if specified
    if response_format == "json":
        params["response_format"] = {"type": "json_object"}

    # Call LLM with retry
    response = await call_with_retry(acompletion, **params)

    # Extract content
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    # Parse JSON if requested
    if response_format == "json":
        try:
            return extract_json_payload(content)
        except json.JSONDecodeError:
            return content

    return content

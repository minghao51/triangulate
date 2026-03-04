"""Test script for Qwen model configuration."""

import os
import asyncio
import pytest
from litellm import acompletion
import dotenv

# Load environment variables
dotenv.load_dotenv()


@pytest.mark.asyncio
async def test_qwen_model():
    """Test the Qwen model configuration."""
    model = os.getenv("LLM_MODEL", "qwen-plus")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv(
        "LLM_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )

    print(f"Testing model: {model}")
    print(f"Base URL: {base_url}")
    print(f"API Key present: {bool(api_key)}")
    print("-" * 50)

    try:
        response = await acompletion(
            model=model,
            messages=[
                {"role": "user", "content": "Say 'Hello from Qwen!' in one sentence."}
            ],
            api_key=api_key,
            base_url=base_url,
            custom_llm_provider="openai",
            temperature=0.7,
            max_tokens=100,
        )

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        print("✅ SUCCESS!")
        print(f"Response: {content}")
        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_qwen_model())
    exit(0 if success else 1)

# Qwen Model Configuration Update - 2026-03-04

## Summary
Updated the triangulate application to use Qwen models through Alibaba Cloud's Singapore workspace endpoint instead of Gemini.

## Changes Made

### 1. Environment Configuration (.env)
- Changed `LLM_PROVIDER` from `gemini` to `openai` (for OpenAI-compatible API)
- Updated `LLM_MODEL` to `qwen-plus`
- Added `LLM_BASE_URL` pointing to `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`

### 2. Application Configuration (config.toml)
- Updated `[ai]` section:
  - `model`: Changed from `gemini/gemini-2.0-flash-exp` to `qwen-plus`
  - Added `base_url`: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`

### 3. Agent Updates
Updated two agent files to support custom base URLs:

#### src/ai/agents/collector.py
- Added support for `LLM_BASE_URL` environment variable
- Added `custom_llm_provider="openai"` parameter when using custom endpoint
- Dynamically builds completion parameters based on whether base_url is present

#### src/ai/agents/narrator.py
- Same updates as collector.py for consistency

## Technical Details

### Why OpenAI Provider?
The Singapore workspace endpoint (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`) provides an OpenAI-compatible API. Using litellm's `openai` provider with a custom `base_url` allows seamless integration.

### Model Information
- **Model**: qwen-plus
- **Provider**: Alibaba Cloud Dashscope (Singapore workspace)
- **API Type**: OpenAI-compatible
- **Context Window**: Up to 1M tokens (depending on specific model version)

## Testing
Created test script `test_qwen.py` that verifies:
1. Model connection
2. API key authentication
3. Basic completion functionality

Test passed successfully with response: "Hello from Qwen!"

## API Key Format
The API key follows the format: `sk-08da884ac31f40e9bfae350ca84f37de`

## Next Steps
- Test with actual article processing workflow
- Monitor performance and token usage
- Consider adding more Qwen model variants (qwen-turbo, qwen-max) if needed

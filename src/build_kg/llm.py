"""
LLM provider abstraction for build-kg.

Supports Anthropic (default) and OpenAI as alternative.
Switch providers via the LLM_PROVIDER environment variable.
"""
from typing import Tuple


def get_provider_config() -> Tuple[str, str, str]:
    """Return (provider, api_key, model) from config."""
    from build_kg.config import (
        ANTHROPIC_API_KEY,
        ANTHROPIC_MODEL,
        LLM_PROVIDER,
        OPENAI_API_KEY,
        OPENAI_MODEL,
    )
    if LLM_PROVIDER == 'anthropic':
        return LLM_PROVIDER, ANTHROPIC_API_KEY, ANTHROPIC_MODEL
    return LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL


def create_client(provider: str, api_key: str):
    """Create an LLM client for the given provider."""
    if provider == 'anthropic':
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    elif provider == 'openai':
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    raise ValueError(f"Unknown LLM provider: {provider}")


def chat_parse(client, provider: str, model: str, system_message: str, user_prompt: str) -> str:
    """Send a chat completion request and return the raw response text.

    Args:
        client: Anthropic or OpenAI client instance
        provider: 'anthropic' or 'openai'
        model: Model identifier
        system_message: System prompt
        user_prompt: User prompt with text to parse

    Returns:
        Raw response text (should be JSON)
    """
    if provider == 'anthropic':
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_message,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.1,
        )
        return response.content[0].text
    else:  # openai
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return response.choices[0].message.content


def build_batch_request(provider: str, model: str, custom_id: str,
                        system_message: str, user_prompt: str) -> dict:
    """Build a single batch request line in the provider's format.

    Args:
        provider: 'anthropic' or 'openai'
        model: Model identifier
        custom_id: Unique ID for this request (fragment_id)
        system_message: System prompt
        user_prompt: User prompt

    Returns:
        Dict ready to be serialized as a JSONL line
    """
    if provider == 'anthropic':
        return {
            "custom_id": custom_id,
            "params": {
                "model": model,
                "max_tokens": 4096,
                "system": system_message,
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0.1,
            }
        }
    else:  # openai
        return {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            }
        }


def extract_batch_response_text(provider: str, result_line: dict) -> str:
    """Extract the LLM response text from a batch result line.

    Args:
        provider: 'anthropic' or 'openai'
        result_line: Parsed JSON from the results JSONL file

    Returns:
        Raw response text (should be JSON)
    """
    if provider == 'anthropic':
        return result_line['result']['message']['content'][0]['text']
    else:  # openai
        return result_line['response']['body']['choices'][0]['message']['content']

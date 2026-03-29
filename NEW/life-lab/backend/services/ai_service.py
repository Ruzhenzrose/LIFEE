"""
Async AI service with retry logic and structured logging.
"""
import json
import logging
from typing import Any, Optional

from openai import AsyncOpenAI, RateLimitError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from config import API_KEY, BASE_URL, MODEL_NAME

logger = logging.getLogger("life-simulator.ai")

# --- Async client (non-blocking in FastAPI) ---
client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)


def _clean_json_content(content: str) -> str:
    """Strip markdown code-fence wrappers from AI responses."""
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((RateLimitError,)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def call_ai(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = True,
) -> Optional[Any]:
    """
    Call the AI model asynchronously with automatic retry on rate-limit errors.

    Returns parsed JSON (dict/list) when json_mode=True, raw string otherwise.
    Raises on persistent failures after 3 attempts.
    """
    response = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        response_format={"type": "json_object"} if json_mode else None,
    )

    content = response.choices[0].message.content

    if not json_mode:
        return content

    cleaned = _clean_json_content(content)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error: %s | Raw output: %.200s", exc, cleaned)
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc

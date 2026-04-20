"""Web search tool — backed by Gemini Flash's native google_search grounding.

The calling LLM (DeepSeek, Claude, etc.) sees a single `web_search(query)` tool.
Internally we POST the Gemini REST API directly (bypassing google-genai SDK
since its default httpx config gives spurious ConnectTimeout on some networks).
Gemini 2.5 Flash with `googleSearch` tool runs a real Google query and returns
a grounded summary + citations.

Why Gemini-as-backend:
  - Gemini 2.5 Flash free tier is ~1500 req/day (enough for multi-user beta)
  - Google search quality >>> DDG scrape
  - Built-in grounding citations
  - DeepSeek/most providers have no native search, so we need a backend anyway

Env:
  - GOOGLE_API_KEY    (required; same key used for Gemini LLM + RAG embeddings)
  - WEB_SEARCH_MODEL  (optional; default "gemini-2.5-flash")
"""
import os

import httpx

from .base import ToolDefinition


TOOL_NAME = "web_search"

DEFINITION = ToolDefinition(
    name=TOOL_NAME,
    description=(
        "Search the web for current, factual information. "
        "Returns a grounded summary with source links. "
        "Use when you need recent data, verifiable facts, or information "
        "that likely postdates your training."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query in natural language.",
            },
        },
        "required": ["query"],
    },
)


def _format_response(data: dict, query: str) -> str:
    """Extract answer text and citations from Gemini's generateContent response."""
    candidates = data.get("candidates") or []
    if not candidates:
        return f"No useful results for: {query}"

    c0 = candidates[0]
    parts = (c0.get("content") or {}).get("parts") or []
    text = "".join((p.get("text") or "") for p in parts).strip()

    citations = []
    gm = c0.get("groundingMetadata") or {}
    chunks = gm.get("groundingChunks") or []
    for i, chunk in enumerate(chunks[:6], 1):
        web = chunk.get("web") or {}
        uri = web.get("uri", "") or ""
        title = web.get("title", "") or uri
        if uri:
            citations.append(f"[{i}] {title}  —  {uri}")

    if citations:
        text = f"{text}\n\nSources:\n" + "\n".join(citations)
    return text or f"No useful results for: {query}"


async def execute(tool_input: dict) -> str:
    """Tool entry point. POSTs Gemini REST API with google_search enabled."""
    query = (tool_input.get("query") or "").strip()
    if not query:
        return "Error: empty query"

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return "Web search unavailable: GOOGLE_API_KEY not configured."

    model = os.getenv("WEB_SEARCH_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    prompt = (
        "Search the web and answer the query concisely in plain prose. "
        "Prefer recent sources. If the query is time-sensitive, state the date. "
        f"\n\nQuery: {query}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {"temperature": 0.2},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return _format_response(data, query)
    except httpx.HTTPStatusError as e:
        # API-level errors (rate limit, bad key, etc.) — keep quiet with the model
        code = e.response.status_code if e.response is not None else "??"
        return f"Web search returned HTTP {code}. Answer from existing knowledge and flag uncertainty."
    except Exception as e:
        return (
            f"Web search temporarily unavailable ({type(e).__name__}). "
            "Answer from existing knowledge and flag uncertainty."
        )

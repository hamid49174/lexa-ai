"""Lexa AI — KI Engine (Production Grade, Phase 40: Native Tool Use)
Gemini-only (gemini-3.5-flash / 3.1-flash-lite / 3.1-pro) ueber die
OpenAI-kompatible Schnittstelle, inkl. nativem Function Calling.
Singleton clients, exponential backoff, thread-safe, token budget awareness.

Hinweis: Die Multi-Provider-Gerueste (Groq/OpenAI/Anthropic) existieren nur noch
als Legacy/Reserve und sind durch das Gemini-only-Registry derzeit inaktiv.
"""

try:
    import keyring
except ImportError:
    keyring = None
import functools
import hashlib
import json
import logging
import os
import re
import requests
import threading
import concurrent.futures
import time as _time
from collections import OrderedDict
from datetime import datetime
from typing import Generator, Optional

from backend.conversation_summary import extract_keywords as _extract_keywords  # noqa: F401
from backend.conversation_summary import summarize_messages_local as _summarize_messages_local
from backend.i18n import t
from backend.lexa_voice import LEXA_SYSTEM_PROMPT_CORE, lexa_user_error

logger = logging.getLogger("lexa.ai")

# ── Groq Client Singleton ──────────────────────────
_groq_client = None
_groq_client_lock = threading.Lock()
_groq_client_key_hash: Optional[str] = None

_openai_client = None
_openai_client_lock = threading.Lock()
_openai_client_key_hash: Optional[str] = None

_gemini_client = None
_gemini_client_lock = threading.Lock()
_gemini_client_key_hash: Optional[str] = None

_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"
_ANTHROPIC_MAX_TOKENS = 4096
_GROQ_MAX_TOKENS = 4096
# Gemini laeuft sonst mit Provider-Defaults (ungedeckelt) — gedeckelt, aber grosszuegig:
# 4096 schnitt lange Code-/Analyse-Antworten ab. Gemini Flash kann bis 8192 Output-Tokens.
_GEMINI_MAX_TOKENS = 8192
_GEMINI_TEMPERATURE = 0.7


try:
    from groq import Groq as _Groq
except ImportError:
    _Groq = None

try:
    from openai import OpenAI as _OpenAI
except ImportError:
    _OpenAI = None


def _get_keyring_secret(secret_name: str, provider_label: str, env_var: str | None = None) -> Optional[str]:
    """Read an API key from keyring, with optional env fallback for dev builds."""
    secret = None
    if keyring is None:
        logger.warning(f"keyring nicht installiert - {provider_label} API-Key nicht abrufbar. Installiere: pip install keyring")
    else:
        try:
            secret = keyring.get_password("lexa-ai", secret_name)
        except Exception as e:
            logger.error(t("error.keyringProviderError", provider=provider_label, error=str(e)))
    if secret:
        return secret
    if env_var:
        return os.environ.get(env_var) or None
    return None


def _get_groq_client():
    """Return cached Groq client singleton. Recreates only if API key changes.
    Thread-safe: keyring read + client creation inside lock (no TOCTOU)."""
    global _groq_client, _groq_client_key_hash
    if _Groq is None:
        logger.warning("groq package nicht installiert. Installiere: pip install groq")
        return None
    with _groq_client_lock:
        api_key = _get_keyring_secret("groq_api_key", "Groq", "GROQ_API_KEY")
        if not api_key:
            logger.debug("Kein Groq API-Key in Keyring oder Environment gespeichert.")
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        if _groq_client is not None and _groq_client_key_hash == key_hash:
            return _groq_client
        _groq_client = _Groq(api_key=api_key)
        _groq_client_key_hash = key_hash
        logger.info("Groq client (re-)created")
        return _groq_client


def _get_openai_client():
    """Return cached OpenAI client singleton."""
    global _openai_client, _openai_client_key_hash
    if _OpenAI is None:
        logger.warning("openai package nicht installiert. Installiere: pip install openai")
        return None
    with _openai_client_lock:
        api_key = _get_keyring_secret("openai_api_key", "OpenAI", "OPENAI_API_KEY")
        if not api_key:
            logger.debug("Kein OpenAI API-Key in Keyring gespeichert.")
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        if _openai_client is not None and _openai_client_key_hash == key_hash:
            return _openai_client
        _openai_client = _OpenAI(api_key=api_key)
        _openai_client_key_hash = key_hash
        logger.info("OpenAI client (re-)created")
        return _openai_client


def _get_gemini_client():
    """Return cached Gemini OpenAI-compatible client singleton."""
    global _gemini_client, _gemini_client_key_hash
    if _OpenAI is None:
        logger.warning("openai package nicht installiert. Installiere: pip install openai")
        return None
    with _gemini_client_lock:
        api_key = _get_keyring_secret("gemini_api_key", "Gemini", "GEMINI_API_KEY")
        if not api_key:
            logger.debug("Kein Gemini API-Key in Keyring gespeichert.")
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        if _gemini_client is not None and _gemini_client_key_hash == key_hash:
            return _gemini_client
        _gemini_client = _OpenAI(
            api_key=api_key,
            base_url=_GEMINI_OPENAI_BASE_URL,
        )
        _gemini_client_key_hash = key_hash
        logger.info("Gemini client (re-)created")
        return _gemini_client


def _get_anthropic_api_key() -> Optional[str]:
    """Return Claude/Anthropic API key from keyring or ANTHROPIC_API_KEY."""
    api_key = _get_keyring_secret("anthropic_api_key", "Anthropic", "ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("Kein Anthropic API-Key in Keyring oder Environment gespeichert.")
    return api_key


# ── Response cache removed in Phase 40 (counterproductive with tool use) ──


# ── Cached System Prompt (rebuilt every 60s, not every call, thread-safe) ──
_cached_system_prompt: Optional[str] = None
_system_prompt_ts: float = 0.0
_system_prompt_hash: str = ""
_system_prompt_lock = threading.Lock()
_SYSTEM_PROMPT_TTL = 60  # seconds

# ── Productivity Stats Cache (avoid DB queries on every message) ──
_productivity_cache = {"data": None, "ts": 0}
_productivity_cache_lock = threading.Lock()
_PRODUCTIVITY_CACHE_TTL = 5  # seconds

# ── Memory-Search Executor (langlebig, statt pro Request neu erzeugen) ──
# Begrenzt die Hintergrund-Threads fuer die 0.5s-getimeoutete Memory-Suche:
# ein haengender search_memory-Call belegt hoechstens diese Worker, statt bei
# jeder Nachricht einen neuen Executor zu erzeugen/zu verwerfen.
_memory_search_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="lexa-memsearch"
)


# ── Error Categories ──
class _ErrorCategory:
    RATE_LIMIT = "rate_limit"
    MODEL_ERROR = "model_error"
    NETWORK_ERROR = "network_error"
    AUTH_ERROR = "auth_error"
    TOOL_USE_FAILED = "tool_use_failed"
    UNKNOWN = "unknown"


def _categorize_error(e: Exception) -> str:
    """Categorize an exception for retry strategy decisions."""
    err_str = str(e).lower()
    err_type = type(e).__name__.lower()

    # Tool use failed (400) — retry without tools
    if "tool_use_failed" in err_str or "failed to call a function" in err_str:
        return _ErrorCategory.TOOL_USE_FAILED

    # Rate limit
    if "429" in str(e) or "rate_limit" in err_str or "ratelimit" in err_type:
        return _ErrorCategory.RATE_LIMIT

    # Auth errors — never retry
    if "401" in str(e) or "403" in str(e) or "auth" in err_str or "invalid_api_key" in err_str:
        return _ErrorCategory.AUTH_ERROR

    # Model errors — try fallback model
    if any(kw in err_str for kw in [
        "503",
        "service unavailable",
        "temporarily unavailable",
        "capacity",
        "overloaded",
        "context_length",
        "model_not_found",
        "decommissioned",
    ]):
        return _ErrorCategory.MODEL_ERROR

    # Network errors — retry with backoff
    if any(kw in err_type for kw in ["connection", "timeout", "socket"]):
        return _ErrorCategory.NETWORK_ERROR
    if any(kw in err_str for kw in ["connection", "timeout", "timed out", "network"]):
        return _ErrorCategory.NETWORK_ERROR

    return _ErrorCategory.UNKNOWN


# ── Token Budget ──
# Gemini 3.5 Flash hat ~1M Token Kontext. Der alte 6000er-Cap (GPT-3.5-Aera) trimmte
# den Verlauf staendig weg und verschenkte Geminis groessten Vorteil. Jetzt nur noch
# Notbremse gegen Runaway-Kontext; normale Gespraeche bleiben vollstaendig erhalten.
_TOKEN_WARN_THRESHOLD = 200000  # rough token limit for system + history (Gemini 1M context)


def _estimate_tokens(char_count: int) -> int:
    """Rough token estimation (chars / 4)."""
    return char_count // 4


def _check_token_budget(system_content: str, messages: list[dict]) -> list[dict]:
    """Check token budget and trim history if needed. Returns (possibly trimmed) messages."""
    message_snapshot = list(messages or [])
    system_tokens = _estimate_tokens(len(system_content))
    total_tokens = system_tokens

    for msg in message_snapshot:
        total_tokens += _estimate_tokens(len(msg.get("content") or ""))

    if total_tokens <= _TOKEN_WARN_THRESHOLD:
        return message_snapshot

    # Actively trim history from the front until under budget
    trimmed = list(message_snapshot)
    while len(trimmed) > 2 and total_tokens > _TOKEN_WARN_THRESHOLD:
        removed = trimmed.pop(0)
        total_tokens -= _estimate_tokens(len(removed.get("content") or ""))

    logger.warning(
        f"Token budget trimmed: ~{total_tokens} tokens "
        f"(removed {len(message_snapshot) - len(trimmed)} older messages, "
        f"threshold: {_TOKEN_WARN_THRESHOLD})"
    )
    return trimmed


# ══════════════════════════════════════════════════
#  SYSTEM PROMPT (Phase 40: Slim — personality only)
#  Tool definitions are now sent via native function calling,
#  NOT listed in the system prompt.
# ══════════════════════════════════════════════════

SYSTEM_PROMPT_CORE = LEXA_SYSTEM_PROMPT_CORE

# Backward compatibility alias — other modules may reference SYSTEM_PROMPT
SYSTEM_PROMPT = SYSTEM_PROMPT_CORE


# ══════════════════════════════════════════════════
# ══════════════════════════════════════════════════
#  CONVERSATION CONTEXT HELPERS
# ══════════════════════════════════════════════════

# Keyword extraction and old-history summarization live in
# backend.conversation_summary. The underscored imports above preserve
# compatibility for tests and older modules that import from ai_engine.


#  SHARED RESPONSE PROCESSING (DRY — used by all providers)
# ══════════════════════════════════════════════════

def _parse_tool_arguments(raw_arguments):
    if raw_arguments in (None, ""):
        return {}
    try:
        return json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        return raw_arguments


def _parse_tool_calls_from_message(msg) -> list[dict]:
    """Extract tool calls from an API response message object.
    Shared by Groq, OpenAI, and Gemini response processing."""
    tool_calls = []
    for tc in msg.tool_calls:
        args = _parse_tool_arguments(tc.function.arguments)
        tool_calls.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": args,
        })
    return tool_calls


def _process_chat_response(result, provider_label: str) -> Optional[dict]:
    """Process a non-streaming API response into a unified result dict.
    Shared by _chat_groq() and _chat_openai_compatible().

    Returns:
        {"type": "text", "content": "..."} for plain text
        {"type": "tool_call", "tool_calls": [...], "content": "..."} for tool calls
        None on failure
    """
    choice = result.choices[0] if result.choices else None
    if not choice or not choice.message:
        logger.warning(f"{provider_label} returned malformed response (no message)")
        return None

    msg = choice.message

    # Check for native tool calls first
    if getattr(msg, "tool_calls", None):
        tool_calls = _parse_tool_calls_from_message(msg)
        logger.info(f"{provider_label} tool call: {[tc['name'] for tc in tool_calls]}")
        return {
            "type": "tool_call",
            "tool_calls": tool_calls,
            "content": msg.content or "",
        }

    # Plain text response
    reply = (msg.content or "").strip()
    if not reply:
        logger.warning(f"{provider_label} returned empty content")
        return None
    logger.info(f"{provider_label} response ({len(reply)} chars)")
    return {"type": "text", "content": reply}


def _retry_api_call(
    api_call_fn,
    provider_label: str,
    fallback_fn=None,
) -> object:
    """Shared retry logic with exponential backoff and error categorization.

    Args:
        api_call_fn: Callable that performs the API call. Returns result or None.
        provider_label: For logging (e.g. "Groq", "OpenAI").
        fallback_fn: Optional callable for model fallback (e.g. Groq smaller model).

    Returns the API result object, or None on failure.
    """
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            result = api_call_fn()
            if result is None:
                return None  # no client available
            return result
        except Exception as e:
            last_error = e
            category = _categorize_error(e)
            logger.warning(f"{provider_label} attempt {attempt + 1}/{_MAX_RETRIES} failed [{category}]: {e}")

            if category == _ErrorCategory.AUTH_ERROR:
                logger.error(f"{provider_label} auth error — not retrying")
                return None

            if category == _ErrorCategory.TOOL_USE_FAILED:
                # Deterministischer 400 — identischer Retry mit Tools schlaegt
                # garantiert erneut fehl. Sofort an den Aufrufer zurueck, der den
                # Tools-freien Retry uebernimmt.
                logger.info(f"{provider_label} tool_use_failed — not retrying with tools")
                return None

            if category == _ErrorCategory.MODEL_ERROR:
                break

            if category in (_ErrorCategory.RATE_LIMIT, _ErrorCategory.NETWORK_ERROR):
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_BASE * (2 ** attempt)
                    logger.info(f"Backoff: waiting {delay}s before retry...")
                    _time.sleep(delay)
                continue

            if attempt >= 1:
                break
            _time.sleep(_BACKOFF_BASE)

    # Try fallback if provided
    if fallback_fn is not None and last_error is not None:
        category = _categorize_error(last_error)
        if category in (_ErrorCategory.MODEL_ERROR, _ErrorCategory.RATE_LIMIT, _ErrorCategory.UNKNOWN):
            return fallback_fn()

    if last_error:
        logger.warning(f"{provider_label} failed after all retries: {last_error}")
    return None


# ══════════════════════════════════════════════════
#  GROQ (PRIMARY)
# ══════════════════════════════════════════════════

_MAX_RETRIES = 3
_BACKOFF_BASE = 1  # 1s -> 2s -> 4s


def _provider_tool_payload(tools: list[dict] | None) -> list[dict]:
    """Return provider-safe OpenAI tool definitions without Lexa metadata."""
    payload: list[dict] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict) or not function.get("name"):
            continue
        clean_function = {
            key: function[key]
            for key in ("name", "description", "parameters")
            if key in function
        }
        payload.append({"type": tool.get("type") or "function", "function": clean_function})
    return payload


def _groq_api_call(
    messages: list[dict],
    model: str,
    stream: bool = False,
    timeout: int = 30,
    tools: list[dict] | None = None,
) -> object:
    """Execute a single Groq API call. Returns response or stream object.

    If `tools` is provided, native function calling is used.
    """
    client = _get_groq_client()
    if not client:
        return None
    kwargs = dict(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=_GROQ_MAX_TOKENS,
        stream=stream,
        timeout=timeout,
    )
    provider_tools = _provider_tool_payload(tools)
    if provider_tools:
        kwargs["tools"] = provider_tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def _groq_with_retry(
    messages: list[dict],
    model: str,
    stream: bool = False,
    tools: list[dict] | None = None,
) -> object:
    """Groq API call with exponential backoff and model fallback."""
    def _call():
        return _groq_api_call(messages, model, stream=stream, tools=tools, timeout=45)

    def _fallback():
        if model == "llama-3.1-8b-instant":
            return None
        logger.warning(f"Groq model '{model}' unavailable — trying llama-3.1-8b-instant fallback")
        try:
            # 8B model is too weak for reliable tool calling — send without tools
            # The router layer will detect tool descriptions in text as fallback
            result = _groq_api_call(messages, "llama-3.1-8b-instant", stream=stream, tools=None, timeout=45)
            if result is not None:
                logger.info("Groq fallback erfolgreich: llama-3.1-8b-instant")
                return result
        except Exception as fb_err:
            logger.warning(f"Groq fallback also failed: {fb_err}")
        return None

    return _retry_api_call(_call, "Groq", fallback_fn=_fallback)


def _chat_groq(
    messages: list[dict],
    model: str,
    tools: list[dict] | None = None,
) -> Optional[dict]:
    """Try Groq API with retry and fallback. Returns unified result dict or None."""
    result = _groq_with_retry(messages, model=model, stream=False, tools=tools)
    if result is None:
        return None
    return _process_chat_response(result, "Groq")


def _get_openai_compatible_client(provider: str):
    """Return the cached client for an OpenAI-compatible provider."""
    if provider == "openai":
        return _get_openai_client()
    if provider == "gemini":
        return _get_gemini_client()
    raise ValueError(f"Unsupported OpenAI-compatible provider: {provider}")


def _openai_compatible_api_call(
    provider: str,
    messages: list[dict],
    model: str,
    stream: bool = False,
    timeout: int = 30,
    tools: list[dict] | None = None,
) -> object:
    """Execute a single chat.completions call for OpenAI or Gemini."""
    client = _get_openai_compatible_client(provider)
    if not client:
        return None
    kwargs = dict(
        model=model,
        messages=messages,
        temperature=_GEMINI_TEMPERATURE,
        max_tokens=_GEMINI_MAX_TOKENS,
        stream=stream,
        timeout=timeout,
    )
    provider_tools = _provider_tool_payload(tools)
    if provider_tools:
        kwargs["tools"] = provider_tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def _openai_compatible_with_retry(
    provider: str,
    messages: list[dict],
    model: str,
    stream: bool = False,
    tools: list[dict] | None = None,
) -> object:
    """Retry wrapper for OpenAI-compatible providers."""
    def _call():
        return _openai_compatible_api_call(provider, messages, model, stream=stream, tools=tools)

    return _retry_api_call(_call, provider.title())


def _chat_openai_compatible(
    provider: str,
    messages: list[dict],
    model: str,
    tools: list[dict] | None = None,
) -> Optional[dict]:
    """Try OpenAI or Gemini via the OpenAI-compatible Chat Completions API."""
    result = _openai_compatible_with_retry(provider, messages, model=model, stream=False, tools=tools)
    if result is None:
        return None
    return _process_chat_response(result, provider.title())


class _AnthropicStreamFunction:
    def __init__(self, name: str = "", arguments: str = ""):
        self.name = name
        self.arguments = arguments


class _AnthropicStreamToolCallDelta:
    def __init__(self, index: int, tool_id: str = "", name: str = "", arguments: str = ""):
        self.index = index
        self.id = tool_id
        self.function = _AnthropicStreamFunction(name=name, arguments=arguments)


class _AnthropicStreamDelta:
    def __init__(self, content: str | None = None, tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls


class _AnthropicStreamChoice:
    def __init__(self, delta: _AnthropicStreamDelta):
        self.delta = delta


class _AnthropicStreamChunk:
    def __init__(self, delta: _AnthropicStreamDelta):
        self.choices = [_AnthropicStreamChoice(delta)]


def _anthropic_text_chunk(text: str) -> _AnthropicStreamChunk:
    return _AnthropicStreamChunk(_AnthropicStreamDelta(content=text))


def _anthropic_tool_chunk(index: int, tool_id: str = "", name: str = "", arguments: str = "") -> _AnthropicStreamChunk:
    return _AnthropicStreamChunk(
        _AnthropicStreamDelta(
            tool_calls=[_AnthropicStreamToolCallDelta(index, tool_id=tool_id, name=name, arguments=arguments)]
        )
    )


def _anthropic_message_text(content) -> str:
    """Normalize internal chat content into plain text for Claude's Messages API."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def _anthropic_convert_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI-style messages into Anthropic system + messages format."""
    system_parts: list[str] = []
    converted: list[dict] = []

    for msg in messages or []:
        role = msg.get("role", "user")
        text = _anthropic_message_text(msg.get("content", "")).strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
            continue

        anthropic_role = "assistant" if role == "assistant" else "user"
        if converted and converted[-1]["role"] == anthropic_role:
            converted[-1]["content"] = converted[-1]["content"] + "\n\n" + text
        else:
            converted.append({"role": anthropic_role, "content": text})

    if not converted:
        converted.append({"role": "user", "content": "Hallo"})

    return ("\n\n".join(system_parts).strip() or None), converted


def _anthropic_convert_tools(tools: list[dict] | None) -> list[dict]:
    """Convert OpenAI function-tool definitions into Anthropic client tools."""
    converted = []
    for tool in tools or []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not name:
            continue
        converted.append(
            {
                "name": name,
                "description": function.get("description") or "",
                "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return converted


def _anthropic_api_call(
    messages: list[dict],
    model: str,
    stream: bool = False,
    timeout: int = 45,
    tools: list[dict] | None = None,
) -> object:
    """Execute a direct Anthropic Messages API call."""
    api_key = _get_anthropic_api_key()
    if not api_key:
        return None

    system, anthropic_messages = _anthropic_convert_messages(messages)
    payload = {
        "model": model,
        "max_tokens": _ANTHROPIC_MAX_TOKENS,
        "messages": anthropic_messages,
    }
    if system:
        payload["system"] = system
    anthropic_tools = _anthropic_convert_tools(tools)
    if anthropic_tools:
        payload["tools"] = anthropic_tools
        payload["tool_choice"] = {"type": "auto"}
    if stream:
        payload["stream"] = True

    response = requests.post(
        _ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        },
        json=payload,
        timeout=timeout,
        stream=stream,
    )
    response.raise_for_status()
    if stream:
        return _anthropic_iter_lines_closing(response)
    return response.json()


def _anthropic_iter_lines_closing(response) -> Generator[str, None, None]:
    """Yield SSE lines and guarantee the HTTP response is closed.

    Bei vorzeitigem Abbruch des Generators (Client-Disconnect/Exception) wird
    response.close() im finally aufgerufen, damit der Socket nicht leakt.
    """
    try:
        for line in response.iter_lines(decode_unicode=True):
            yield line
    finally:
        response.close()


def _anthropic_with_retry(
    messages: list[dict],
    model: str,
    stream: bool = False,
    tools: list[dict] | None = None,
) -> object:
    """Retry wrapper for Claude/Anthropic."""
    def _call():
        return _anthropic_api_call(messages, model, stream=stream, tools=tools)

    return _retry_api_call(_call, "Anthropic")


def _process_anthropic_response(result: dict) -> Optional[dict]:
    """Convert Anthropic Messages API JSON into Lexa's unified response dict."""
    if not isinstance(result, dict):
        return None

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for block in result.get("content") or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text") or ""
            if text:
                text_parts.append(text)
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id") or "",
                    "name": block.get("name") or "",
                    "arguments": block["input"] if "input" in block else {},
                }
            )

    content = "\n".join(text_parts).strip()
    if tool_calls:
        logger.info(f"Anthropic tool call: {[tc['name'] for tc in tool_calls]}")
        return {"type": "tool_call", "tool_calls": tool_calls, "content": content}
    if content:
        logger.info(f"Anthropic response ({len(content)} chars)")
        return {"type": "text", "content": content}
    logger.warning("Anthropic returned empty content")
    return None


def _chat_anthropic(
    messages: list[dict],
    model: str,
    tools: list[dict] | None = None,
) -> Optional[dict]:
    """Try Claude/Anthropic API with retry. Returns unified result dict or None."""
    result = _anthropic_with_retry(messages, model=model, stream=False, tools=tools)
    if result is None:
        return None
    return _process_anthropic_response(result)


def _anthropic_stream_to_openai_chunks(lines) -> Generator[object, None, None]:
    """Adapt Anthropic SSE events to the OpenAI-like stream shape used by Lexa."""
    for raw_line in lines:
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            logger.debug(f"Skipping malformed Anthropic stream event: {data[:120]}")
            continue

        event_type = event.get("type")
        if event_type == "error":
            err = event.get("error") or {}
            raise RuntimeError(err.get("message") or err.get("type") or "Anthropic stream error")

        if event_type == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                yield _anthropic_tool_chunk(
                    int(event.get("index") or 0),
                    tool_id=block.get("id") or "",
                    name=block.get("name") or "",
                )
            continue

        if event_type != "content_block_delta":
            continue

        index = int(event.get("index") or 0)
        delta = event.get("delta") or {}
        delta_type = delta.get("type")
        if delta_type == "text_delta" and delta.get("text"):
            yield _anthropic_text_chunk(delta["text"])
        elif delta_type == "input_json_delta" and delta.get("partial_json") is not None:
            yield _anthropic_tool_chunk(index, arguments=delta.get("partial_json") or "")


# ══════════════════════════════════════════════════
#  MESSAGE BUILDER (shared by chat + stream)
# ══════════════════════════════════════════════════

_MAX_CONVERSATION_HISTORY = 20  # truncate to prevent context overflow

_PENDING_PARAM_VALUE_MAX = 100  # max chars per pending-confirmation param value


def _sanitize_pending_param_value(value) -> str:
    """Sanitize a pending-confirmation param value before system-prompt injection.

    Werte stammen aus modellgenerierten Tool-Calls und koennen unvertrauenswuerdigen
    Kontext (Web-/Datei-Inhalte) enthalten. Steuerzeichen/Zeilenumbrueche entfernen und
    hart kuerzen, damit keine fremden Instruktionen in die SYSTEM-Rolle gelangen.
    """
    text = str(value)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > _PENDING_PARAM_VALUE_MAX:
        text = text[:_PENDING_PARAM_VALUE_MAX] + "…"
    return text


def _build_system_content_cached() -> tuple[str, str]:
    """Build and cache the static parts of the system prompt.

    Refreshes every 60s to avoid expensive DB/import calls on every chat message.
    Returns (system_content, content_hash).

    Phase 40: The prompt is now slim (~200 tokens). Command descriptions are sent
    via native tool definitions, not in the prompt.
    """
    global _cached_system_prompt, _system_prompt_ts, _system_prompt_hash
    now_ts = _time.time()

    with _system_prompt_lock:
        if _cached_system_prompt is not None and (now_ts - _system_prompt_ts) < _SYSTEM_PROMPT_TTL:
            return _cached_system_prompt, _system_prompt_hash

    parts = [SYSTEM_PROMPT_CORE]

    # User profile (rarely changes, safe to cache 60s)
    try:
        from backend.memory import get_user_profile
        profile = get_user_profile()
        if profile:
            parts.append(f"\n\nUSER-PROFIL: {profile}")
    except Exception as e:
        logger.debug(f"Profile context skipped: {e}")

    system_content = "".join(parts)
    content_hash = hashlib.sha256(system_content.encode()).hexdigest()[:16]

    with _system_prompt_lock:
        _cached_system_prompt = system_content
        _system_prompt_ts = now_ts
        _system_prompt_hash = content_hash
    return system_content, content_hash


def _detect_conversation_mood(conversation_history: Optional[list], user_message: str) -> str:
    """Detect the current conversation mood/energy from recent messages.

    Returns a short mood hint for the AI to adapt its tone.
    """
    hints = []

    # Phase 46: user_message can be None in agent mode
    if not user_message:
        return ""

    # Analyze user message style
    if (
        len(user_message) > 5
        and any(c.isalpha() for c in user_message)
        and user_message == user_message.upper()
    ):
        hints.append("User schreibt in CAPS → möglicherweise aufgeregt/frustriert")
    if user_message.count("!") >= 2:
        hints.append("User nutzt viele Ausrufezeichen → aufgeregt oder enthusiastisch")
    if user_message.endswith("..."):
        hints.append("User endet mit '...' → denkt nach oder ist unsicher")
    if len(user_message.split()) <= 3 and not user_message.endswith("?"):
        hints.append("Kurzer Befehl → User ist im Flow, sei extra effizient")
    if user_message.count("?") >= 2:
        hints.append("Mehrere Fragen → User braucht Orientierung")

    # Check conversation pattern (last 4 messages)
    if conversation_history and len(conversation_history) >= 4:
        recent_user_msgs = [
            m["content"] for m in conversation_history[-4:]
            if m.get("role") == "user" and m.get("content")
        ]
        if recent_user_msgs:
            avg_len = sum(len(m) for m in recent_user_msgs) / len(recent_user_msgs)
            if avg_len < 20:
                hints.append("User sendet kurze Nachrichten → Quick-Chat-Modus")
            elif avg_len > 200:
                hints.append("User schreibt ausführlich → gib detaillierte Antworten")

    # Check for frustration indicators in recent history
    if conversation_history:
        recent = conversation_history[-6:] if len(conversation_history) >= 6 else conversation_history
        frustration_words = {"funktioniert nicht", "geht nicht", "klappt nicht", "fehler",
                             "kaputt", "nervt", "scheiße", "mist", "fuck", "wtf", "warum geht"}
        for m in recent:
            content = (m.get("content") or "").lower()
            if m.get("role") == "user" and any(fw in content for fw in frustration_words):
                hints.append("User war kürzlich frustriert → sei besonders lösungsorientiert und geduldig")
                break

    return " | ".join(hints) if hints else ""


def _detect_conversation_topic(conversation_history: Optional[list]) -> str:
    """Detect the current conversation topic from recent messages for continuity."""
    if not conversation_history or len(conversation_history) < 2:
        return ""

    recent = conversation_history[-6:] if len(conversation_history) >= 6 else conversation_history
    topic_indicators = {
        "musik": ["spotify", "song", "musik", "lied", "playlist", "album", "artist"],
        "system": ["cpu", "ram", "speicher", "prozess", "system", "pc", "computer", "langsam"],
        "dateien": ["datei", "ordner", "file", "folder", "download", "dokument", "pdf"],
        "produktivität": ["todo", "aufgabe", "pomodoro", "timer", "fokus", "habit"],
        "entwicklung": ["git", "code", "docker", "api", "server", "debug", "error"],
        "kommunikation": ["email", "mail", "telegram", "discord", "nachricht"],
        "web": ["youtube", "browser", "website", "suche", "google"],
    }

    topic_scores: dict[str, int] = {}
    for m in recent:
        content = (m.get("content") or "").lower()
        for topic, keywords in topic_indicators.items():
            for kw in keywords:
                if kw in content:
                    topic_scores[topic] = topic_scores.get(topic, 0) + 1

    if topic_scores:
        top_topic = max(topic_scores, key=topic_scores.get)
        if topic_scores[top_topic] >= 2:
            return f"Aktuelles Gesprächsthema: {top_topic}"
    return ""


_QUALITY_MODE_TOP_TIER_MARKERS = (
    "chatgpt",
    "chagbt",
    "gpt",
    "claude",
    "niveau",
    "niviu",
    "level",
    "top",
    "premium",
)

_QUALITY_MODE_COMPLEX_MARKERS = (
    "verbesser",
    "verbessere",
    "verbessern",
    "verbesserung",
    "verbesserungen",
    "verbessert",
    "upgrade",
    "feature",
    "features",
    "feture",
    "futere",
    "futeres",
    "ausbau",
    "ausbauen",
    "weiterentwickeln",
    "weiterentwicklung",
    "weiterentwickle",
    "weiterentwickelt",
    "funktion",
    "funktionen",
    "funktionalitaet",
    "intelligenz",
    "intelligen",
    "intilegnz",
    "antwortqualitaet",
    "antwort qualitaet",
    "answer quality",
    "memory",
    "gedaechtnis",
    "erinnerung",
    "erinnerungen",
    "context",
    "kontext",
    "kontextfenster",
    "personalization",
    "personalisierung",
    "personalisiert",
    "conversation",
    "conversation flow",
    "konversation",
    "gespraech",
    "gespraechsverlauf",
    "dialog",
    "follow up",
    "followup",
    "follow ups",
    "followups",
    "folgenfrage",
    "folgenfragen",
    "intent",
    "intention",
    "intent recognition",
    "intent erkennung",
    "reasoning",
    "schlussfolgern",
    "planung",
    "priorisierung",
    "automatisierung",
    "automatiersung",
    "autoamtion",
    "reliability",
    "stability",
    "robust",
    "robuster",
    "robustheit",
    "robustness",
    "stabil",
    "stabilitaet",
    "ux",
    "user experience",
    "usability",
    "bedienbarkeit",
    "accessibility",
    "a11y",
    "barrierefreiheit",
    "zugaenglichkeit",
    "performance",
    "speed",
    "schnell",
    "schneller",
    "geschwindigkeit",
    "latency",
    "latenz",
    "reaktionszeit",
    "response time",
    "ladezeit",
    "startzeit",
    "professionell",
    "produkt",
    "release",
    "internalrc",
    "publicrc",
    "strategie",
    "roadmap",
    "entscheidung",
    "architektur",
    "security",
    "sicherheit",
    "audit",
    "review",
    "debug",
    "fehler",
    "implement",
    "code",
    "komplex",
    "senior",
    "erfahrung",
    "profi",
    "advanced",
    "production",
    "best practice",
    "test",
    "tests",
    "testing",
    "fokustest",
    "fokustests",
    "guardrail",
    "guardrails",
    "refactor",
    "qualitaet",
    "quality",
)

_QUALITY_MODE_LEXA_PRODUCT_MARKERS = (
    "chat",
    "intelligenz",
    "intelligen",
    "intilegnz",
    "antwortqualitaet",
    "antwort qualitaet",
    "answer quality",
    "memory",
    "gedaechtnis",
    "erinnerung",
    "erinnerungen",
    "context",
    "kontext",
    "kontextfenster",
    "personalization",
    "personalisierung",
    "personalisiert",
    "conversation",
    "conversation flow",
    "konversation",
    "gespraech",
    "gespraechsverlauf",
    "dialog",
    "follow up",
    "followup",
    "follow ups",
    "followups",
    "folgenfrage",
    "folgenfragen",
    "intent",
    "intention",
    "intent recognition",
    "intent erkennung",
    "reasoning",
    "schlussfolgern",
    "planung",
    "priorisierung",
    "feature",
    "features",
    "feture",
    "futere",
    "futeres",
    "funktion",
    "funktionen",
    "funktionalitaet",
    "ux",
    "user experience",
    "automatisierung",
    "automatiersung",
    "autoamtion",
    "test",
    "tests",
    "testing",
    "fokustest",
    "fokustests",
    "guardrail",
    "guardrails",
    "zuverlaessigkeit",
    "reliability",
    "stability",
    "robust",
    "robuster",
    "robustheit",
    "robustness",
    "stabil",
    "stabilitaet",
    "usability",
    "bedienbarkeit",
    "performance",
    "speed",
    "schnell",
    "schneller",
    "geschwindigkeit",
    "latency",
    "latenz",
    "reaktionszeit",
    "response time",
    "ladezeit",
    "startzeit",
    "accessibility",
    "a11y",
    "barrierefreiheit",
    "zugaenglichkeit",
)

_QUALITY_MODE_PRODUCT_ACTION_MARKERS = (
    "verbesser",
    "verbessere",
    "verbessern",
    "verbesserung",
    "verbesserungen",
    "verbessert",
    "upgrade",
    "polish",
    "optimieren",
    "optimierung",
    "optimize",
    "optimise",
    "ausbau",
    "ausbauen",
    "weiterentwickeln",
    "weiterentwicklung",
    "weiterentwickle",
    "weiterentwickelt",
)

_QUALITY_MODE_SOURCE_MARKERS = (
    "quelle",
    "quellen",
    "source",
    "sources",
    "reference",
    "references",
    "referenz",
    "referenzen",
    "citation",
    "citations",
    "beleg",
    "belege",
    "evidence",
    "literatur",
    "study",
    "studies",
    "studie",
    "studien",
    "paper",
    "papers",
    "research",
    "recherche",
)

_QUALITY_MODE_VERIFICATION_MARKERS = (
    "claim",
    "claims",
    "aussage",
    "aussagen",
    "unbelegt",
    "unsupported",
    "unverified",
    "verify",
    "verification",
    "validate",
    "validation",
    "validiere",
    "validieren",
    "validiert",
    "verifizier",
    "verifiziere",
    "verifizieren",
    "verifiziert",
    "faktencheck",
    "fact check",
    "fact-check",
    "cross check",
    "cross-check",
    "gegencheck",
    "gegenpruef",
    "gegenpruefe",
    "gegenpruefen",
    "plausibilitaet",
    "plausibilitaetscheck",
    "source backed",
    "source-backed",
    "research brief",
    "pruef",
    "pruefe",
    "pruefen",
    "geprueft",
    "ueberpruef",
    "ueberpruefe",
    "ueberpruefen",
)

_QUALITY_MODE_DIRECT_ANSWER_VERIFICATION_MARKERS = (
    "verify answer",
    "verify this answer",
    "verify the answer",
    "verify my answer",
    "fact check answer",
    "fact check this answer",
    "fact check my answer",
    "fact-check answer",
    "fact-check this answer",
    "fact-check my answer",
    "double check answer",
    "double check this answer",
    "double check my answer",
    "verify claim",
    "verify this claim",
    "check claim",
    "check this claim",
    "fact check claim",
    "fact check this claim",
    "fact-check claim",
    "fact-check this claim",
    "double check claim",
    "double check this claim",
    "verify statement",
    "verify this statement",
    "check statement",
    "check this statement",
    "fact check statement",
    "fact check this statement",
    "fact-check statement",
    "fact-check this statement",
    "double check statement",
    "double check this statement",
    "verify assertion",
    "verify this assertion",
    "check assertion",
    "check this assertion",
    "fact check assertion",
    "fact check this assertion",
    "fact-check assertion",
    "fact-check this assertion",
    "double check assertion",
    "double check this assertion",
    "check answer",
    "check the answer",
    "check this answer",
    "check my answer",
    "antwort pruefen",
    "diese antwort pruefen",
    "die antwort pruefen",
    "meine antwort pruefen",
    "pruef die antwort",
    "pruef diese antwort",
    "pruef meine antwort",
    "pruefe die antwort",
    "pruefe diese antwort",
    "pruefe meine antwort",
    "ueberpruef die antwort",
    "ueberpruef diese antwort",
    "ueberpruef meine antwort",
    "ueberpruefe die antwort",
    "ueberpruefe diese antwort",
    "ueberpruefe meine antwort",
    "aussage pruefen",
    "diese aussage pruefen",
    "pruef diese aussage",
    "pruefe diese aussage",
    "behauptung pruefen",
    "diese behauptung pruefen",
    "pruef diese behauptung",
    "pruefe diese behauptung",
    "faktencheck antwort",
    "faktencheck diese antwort",
    "faktencheck meine antwort",
    "faktencheck aussage",
    "faktencheck diese aussage",
    "faktencheck behauptung",
    "faktencheck diese behauptung",
    "antwort verifizieren",
    "meine antwort verifizieren",
)

_QUALITY_MODE_DECISION_INTENT_MARKERS = (
    "decision",
    "decide",
    "choose",
    "choice",
    "rank",
    "ranking",
    "entscheidung",
    "entscheiden",
    "wahl",
    "waehle",
    "prioritaet",
    "prioritaeten",
    "priority",
    "priorities",
    "prioritize",
    "prioritise",
    "prioritization",
    "prioritisation",
    "priorisieren",
    "priorisierung",
    "rangfolge",
    "strategy",
    "strategie",
    "roadmap",
    "plan",
    "plane",
    "planen",
    "planung",
    "abwaegung",
    "abwaegen",
    "abwaeg",
)

_QUALITY_MODE_DECISION_STRUCTURE_MARKERS = (
    "option",
    "options",
    "optionen",
    "alternative",
    "alternatives",
    "alternativen",
    "choice",
    "choices",
    "wahl",
    "auswahl",
    "tradeoff",
    "tradeoffs",
    "trade off",
    "trade offs",
    "pros",
    "cons",
    "pro",
    "contra",
    "risiko",
    "risiken",
    "risk",
    "risks",
    "vorteil",
    "vorteile",
    "nachteil",
    "nachteile",
    "reversibilitaet",
    "reversible",
    "irreversible",
    "recommendation",
    "empfehlung",
    "confidence",
    "konfidenz",
    "offene fragen",
    "open questions",
    "naechste schritte",
    "next steps",
)

_QUALITY_MODE_DIRECT_DECISION_MARKERS = (
    "decision brief",
    "entscheidungsbrief",
    "which option is better",
    "which option should i choose",
    "which option should i pick",
    "which option should i take",
    "which should i choose",
    "which should i pick",
    "welche option ist besser",
    "welche option soll ich waehlen",
    "welche option soll ich nehmen",
    "welche soll ich waehlen",
    "welche soll ich nehmen",
    "rank these options",
    "rank the options",
    "rank these choices",
    "prioritize these options",
    "prioritise these options",
    "score these options",
    "rate these options",
    "evaluate these options",
    "evaluate the options",
    "weighted decision matrix",
    "bewerte diese optionen",
    "bewerte die optionen",
    "bewertungsmatrix",
    "entscheidungsmatrix",
    "scoring matrix",
    "scoring tabelle",
    "priorisiere diese optionen",
    "priorisiere die optionen",
    "ordne die optionen",
    "mach eine rangfolge",
    "help me decide",
    "hilf mir entscheiden",
    "hilf mir bei der entscheidung",
    "make the call",
    "triff die entscheidung",
    "triff eine entscheidung",
    "entscheide fuer mich",
    "entscheid fuer mich",
    "deep think",
    "deepthink",
    "extended thinking",
    "strategy review",
    "strategie review",
    "roadmap review",
)

_QUALITY_MODE_DECISION_ASK_MARKERS = (
    "soll ich",
    "was soll ich",
    "should i",
    "which should i",
    "welche soll ich",
    "welchen soll ich",
    "welches soll ich",
)

_QUALITY_MODE_DECISION_BETTER_MARKERS = (
    "was ist besser",
    "welche ist besser",
    "welcher ist besser",
    "welches ist besser",
    "which is better",
    "which one is better",
    "what is better",
    "besser fuer",
    "better for",
    "empfiehlst du",
    "would you recommend",
    "what would you do",
    "what would you pick",
    "what would you choose",
    "was wuerdest du machen",
    "was wuerdest du tun",
    "was wuerdest du nehmen",
    "was wuerdest du waehlen",
)

_QUALITY_MODE_DECISION_COMPARE_MARKERS = (
    "vergleiche",
    "vergleich",
    "vergleichs",
    "gegenueberstellen",
    "gegenueberstellung",
    "compare",
    "comparison",
    "compare options",
)

_QUALITY_MODE_DECISION_TRADEOFF_MARKERS = (
    "pros and cons",
    "pros cons",
    "pro und contra",
    "vor und nachteile",
    "vorteile und nachteile",
    "tradeoff",
    "tradeoffs",
    "trade off",
    "trade offs",
    "risks and benefits",
    "risiken und vorteile",
)

_QUALITY_MODE_DECISION_TRADEOFF_CONTEXT_MARKERS = (
    "of",
    "for",
    "between",
    "von",
    "fuer",
    "zwischen",
    "ueber",
    "about",
)

_QUALITY_MODE_DECISION_SCORING_MARKERS = (
    "criteria",
    "criterion",
    "kriterium",
    "kriterien",
    "score",
    "scores",
    "scoring",
    "bewerte",
    "bewerten",
    "bewertung",
    "bewertungsmatrix",
    "entscheidungsmatrix",
    "matrix",
    "weighted",
    "gewichtet",
    "gewichtung",
    "punkte",
    "punktezahl",
)

_QUALITY_MODE_DECISION_PLANNING_MARKERS = (
    "roadmap",
    "fahrplan",
    "umsetzungsplan",
    "execution plan",
    "action plan",
    "rollout plan",
    "release plan",
    "plan of attack",
    "projektplan",
    "project plan",
    "plan",
    "plane",
    "planen",
)

_QUALITY_MODE_DECISION_PLANNING_STRUCTURE_MARKERS = (
    "meilenstein",
    "meilensteine",
    "milestone",
    "milestones",
    "phase",
    "phases",
    "phasen",
    "timeline",
    "zeitplan",
    "quartal",
    "quarter",
    "schritt",
    "schritte",
    "step",
    "steps",
    "owner",
    "owners",
    "abhaengigkeit",
    "abhaengigkeiten",
    "dependency",
    "dependencies",
)

_QUALITY_MODE_DECISION_CONSTRAINT_MARKERS = (
    "constraint",
    "constraints",
    "einschraenkung",
    "einschraenkungen",
    "bedingung",
    "bedingungen",
    "deadline",
    "frist",
    "termin",
    "budget",
    "timebox",
    "zeitlimit",
    "limit",
    "limited",
    "begrenzt",
    "resource",
    "resources",
    "ressource",
    "ressourcen",
    "kapazitaet",
    "kapazitaeten",
    "stunden",
    "hours",
    "tage",
    "days",
    "wochen",
    "weeks",
)

_QUALITY_MODE_DECISION_RISK_MARKERS = (
    "risk assessment",
    "risk analysis",
    "risk register",
    "risk plan",
    "mitigation plan",
    "rollback plan",
    "contingency plan",
    "failure mode",
    "failure modes",
    "abort criteria",
    "go no go",
    "go/no-go",
    "ship risk",
    "release risk",
    "risikoanalyse",
    "risikoplan",
    "risikobewertung",
    "risikoregister",
    "mitigationsplan",
    "notfallplan",
    "abbruchkriterien",
)

_QUALITY_MODE_DIRECT_RISK_MARKERS = (
    "risk register",
    "risk plan",
    "mitigation plan",
    "rollback plan",
    "contingency plan",
    "abort criteria",
    "go no go",
    "go/no-go",
    "risikoplan",
    "risikoregister",
    "mitigationsplan",
    "notfallplan",
    "abbruchkriterien",
)

_QUALITY_MODE_DECISION_RISK_CONTEXT_MARKERS = (
    "for",
    "fuer",
    "von",
    "before",
    "vor",
    "release",
    "ship",
    "launch",
    "lexa",
    "create",
    "make",
    "run",
    "erstelle",
    "mach",
    "pruefe",
    "check",
    "bewerte",
)

_QUALITY_MODE_SECURITY_PRIVACY_MARKERS = (
    "threat model",
    "threat modeling",
    "security review",
    "security audit",
    "privacy review",
    "privacy audit",
    "privacy impact assessment",
    "permission review",
    "permissions review",
    "least privilege",
    "data loss",
    "data-loss",
    "data loss risk",
    "data exfiltration",
    "exfiltration",
    "secret leak",
    "secret leakage",
    "prompt injection",
    "datenschutz review",
    "datenschutz audit",
    "bedrohungsmodell",
    "berechtigungsreview",
    "berechtigungspruefung",
    "berechtigungen pruefen",
    "datenverlust",
    "datenabfluss",
)

_QUALITY_MODE_SECURITY_PRIVACY_CONTEXT_MARKERS = (
    "for",
    "fuer",
    "von",
    "before",
    "vor",
    "lexa",
    "memory",
    "tool",
    "tools",
    "hermes",
    "agent",
    "release",
    "launch",
    "run",
    "create",
    "make",
    "erstelle",
    "mach",
    "pruefe",
    "check",
    "bewerte",
)

_QUALITY_MODE_ACCESSIBILITY_MARKERS = (
    "accessibility",
    "a11y",
    "accessibility review",
    "accessibility audit",
    "barrierefreiheit",
    "barrierefrei",
    "zugaenglichkeit",
    "screen reader",
    "screenreader",
    "sr label",
    "aria",
    "keyboard navigation",
    "keyboard access",
    "tastaturbedienung",
    "tastaturnavigation",
    "focus order",
    "focus trap",
    "fokusreihenfolge",
    "fokusfalle",
    "contrast",
    "kontrast",
    "reduced motion",
    "motion sensitivity",
)

_QUALITY_MODE_ACCESSIBILITY_CONTEXT_MARKERS = (
    "for",
    "fuer",
    "von",
    "before",
    "vor",
    "lexa",
    "app",
    "chat",
    "ui",
    "ux",
    "frontend",
    "settings",
    "modal",
    "button",
    "buttons",
    "page",
    "run",
    "create",
    "make",
    "pruefe",
    "check",
    "bewerte",
)

_QUALITY_MODE_PERFORMANCE_MARKERS = (
    "performance review",
    "performance audit",
    "performance budget",
    "latency budget",
    "latency review",
    "startup time",
    "startup performance",
    "load time",
    "loading time",
    "response time",
    "throughput",
    "profiling",
    "profile performance",
    "bottleneck",
    "bottlenecks",
    "memory footprint",
    "cpu usage",
    "bundle size",
    "render performance",
    "streaming latency",
    "perf review",
    "perf audit",
    "latenz review",
    "latenzbudget",
    "startzeit",
    "ladezeit",
    "reaktionszeit",
    "flaschenhals",
    "flaschenhaelse",
)

_QUALITY_MODE_PERFORMANCE_CONTEXT_MARKERS = (
    "for",
    "fuer",
    "von",
    "before",
    "vor",
    "lexa",
    "app",
    "chat",
    "streaming",
    "frontend",
    "backend",
    "startup",
    "release",
    "launch",
    "run",
    "create",
    "make",
    "measure",
    "benchmark",
    "profile",
    "optimize",
    "optimise",
    "improve",
    "erstelle",
    "mach",
    "miss",
    "messe",
    "benchmarke",
    "optimiere",
    "verbessere",
    "pruefe",
    "check",
    "bewerte",
)

_QUALITY_MODE_TESTING_MARKERS = (
    "test plan",
    "testing plan",
    "qa checklist",
    "qa plan",
    "quality checklist",
    "acceptance criteria",
    "acceptance test",
    "regression test plan",
    "regression tests",
    "smoke test plan",
    "smoke tests",
    "test matrix",
    "testmatrix",
    "test coverage review",
    "eval plan",
    "evaluation plan",
    "abnahmekriterien",
    "abnahmetest",
    "testplan",
    "qa checkliste",
    "qualitaetscheckliste",
    "regressionstestplan",
    "smoketest",
)

_QUALITY_MODE_TESTING_CONTEXT_MARKERS = (
    "for",
    "fuer",
    "von",
    "before",
    "vor",
    "lexa",
    "app",
    "chat",
    "agent",
    "release",
    "launch",
    "feature",
    "workflow",
    "streaming",
    "memory",
    "create",
    "make",
    "write",
    "run",
    "build",
    "review",
    "erstelle",
    "mach",
    "schreibe",
    "pruefe",
    "baue",
)

_QUALITY_MODE_MEMORY_CONTEXT_MARKERS = (
    "memory review",
    "memory audit",
    "memory hygiene",
    "memory cleanup",
    "memory clean up",
    "memory pruning",
    "context pack",
    "context brief",
    "context review",
    "context audit",
    "context window review",
    "stable memory",
    "draft memory",
    "save this memory",
    "save to memory",
    "remember this",
    "what should lexa remember",
    "what should you remember",
    "personalization review",
    "personalisation review",
    "profile review",
    "gedaechtnis review",
    "gedaechtnis audit",
    "gedaechtnis hygiene",
    "gedaechtnis bereinigen",
    "gedaechtnis pruefen",
    "kontextpaket",
    "kontext brief",
    "kontext review",
    "kontextfenster review",
    "was soll lexa speichern",
    "was sollst du speichern",
    "merk dir",
    "speicher das",
    "speichere das",
    "personalisierung review",
    "profil review",
)

_QUALITY_MODE_MEMORY_CONTEXT_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "personal os",
    "conversation",
    "chat",
    "profile",
    "user",
    "task",
    "tasks",
    "project",
    "decision",
    "decisions",
    "facts",
    "assumptions",
    "preference",
    "preferences",
    "privacy",
    "consent",
    "write",
    "writes",
    "build",
    "create",
    "make",
    "save",
    "remember",
    "prune",
    "delete",
    "correct",
    "konversation",
    "gespraech",
    "profil",
    "nutzer",
    "aufgabe",
    "aufgaben",
    "projekt",
    "entscheidung",
    "entscheidungen",
    "fakten",
    "annahmen",
    "praeferenz",
    "praeferenzen",
    "datenschutz",
    "einwilligung",
    "schreibe",
    "baue",
    "erstelle",
    "mach",
    "speicher",
    "speichere",
    "merk",
    "bereinige",
    "loesche",
    "loeschen",
    "korrigiere",
)

_QUALITY_MODE_AGENT_TOOL_MARKERS = (
    "agent run",
    "agent task",
    "agent workflow",
    "agent execution",
    "agent plan",
    "agent handoff",
    "tool workflow",
    "tool plan",
    "tool execution",
    "tool execution plan",
    "tool run",
    "tool use plan",
    "toolchain",
    "workspace handoff",
    "handoff plan",
    "desktop action",
    "local action",
    "os agent runtime",
    "background task",
    "hermes worker",
    "multi step agent",
    "multistep agent",
    "run tools",
    "use tools",
    "agent lauf",
    "agent aufgabe",
    "agent ausfuehrung",
    "agent plan",
    "agent uebergabe",
    "werkzeug workflow",
    "werkzeug plan",
    "tool ausfuehrung",
    "werkzeug ausfuehrung",
    "tool lauf",
    "workspace uebergabe",
    "arbeitsuebergabe",
    "desktop aktion",
    "lokale aktion",
    "hintergrundaufgabe",
)

_QUALITY_MODE_AGENT_TOOL_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "workspace",
    "repository",
    "repo",
    "project",
    "file",
    "files",
    "desktop",
    "browser",
    "os",
    "personal os",
    "hermes",
    "automation",
    "release",
    "chat",
    "memory",
    "permissions",
    "approval",
    "rollback",
    "verification",
    "verify",
    "safe",
    "dry run",
    "read only",
    "read-only",
    "background",
    "create",
    "build",
    "start",
    "execute",
    "projekt",
    "datei",
    "dateien",
    "desktop",
    "browser",
    "automatisierung",
    "freigabe",
    "berechtigungen",
    "verifikation",
    "verifiziere",
    "sicher",
    "nur lesend",
    "lesend",
    "hintergrund",
    "erstelle",
    "baue",
    "starte",
    "fuehre aus",
)

_QUALITY_MODE_SHIP_CHECK_MARKERS = (
    "ship check",
    "production ship check",
    "release check",
    "release readiness",
    "readiness check",
    "launch readiness",
    "launch blocker",
    "launch blockers",
    "publish check",
    "pre publish check",
    "pre release checklist",
    "release checklist",
    "release quality",
    "ship readiness",
    "go live check",
    "go-live check",
    "deployment readiness",
    "deployment check",
    "production readiness",
    "produktreife",
    "release pruefung",
    "release pruefen",
    "publish pruefung",
    "vor publish",
    "vor release",
    "go live pruefung",
    "deployment pruefung",
)

_QUALITY_MODE_SHIP_CHECK_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "app",
    "product",
    "production",
    "user facing",
    "user-facing",
    "ux",
    "accessibility",
    "performance",
    "reliability",
    "security",
    "privacy",
    "data loss",
    "docs",
    "onboarding",
    "tests",
    "migration",
    "rollback",
    "publish",
    "deploy",
    "go live",
    "go-live",
    "before",
    "for",
    "produkt",
    "produktion",
    "nutzerseitig",
    "barrierefreiheit",
    "zuverlaessigkeit",
    "datenschutz",
    "datenverlust",
    "dokumentation",
    "tests",
    "migration",
    "rollback",
    "veroeffentlichen",
    "deployen",
    "vor",
    "fuer",
)

_QUALITY_MODE_DATA_SAFETY_MARKERS = (
    "delete files",
    "delete data",
    "delete memory",
    "delete memories",
    "delete old memories",
    "cleanup old memories",
    "clean up old memories",
    "cleanup downloads",
    "clean up downloads",
    "overwrite file",
    "overwrite files",
    "reset database",
    "reset settings",
    "wipe data",
    "purge data",
    "drop table",
    "truncate table",
    "restore backup",
    "migrate database",
    "apply migration",
    "migration apply",
    "rebuild index",
    "mass delete",
    "bulk delete",
    "destructive action",
    "dangerous change",
    "data loss risk",
    "dateien loeschen",
    "daten loeschen",
    "memory loeschen",
    "erinnerungen loeschen",
    "alte erinnerungen loeschen",
    "erinnerungen aufraeumen",
    "downloads aufraeumen",
    "datei ueberschreiben",
    "dateien ueberschreiben",
    "datenbank zuruecksetzen",
    "einstellungen zuruecksetzen",
    "daten loeschen",
    "backup wiederherstellen",
    "migration anwenden",
    "datenbank migrieren",
    "index neu aufbauen",
    "massenloeschung",
    "destruktive aktion",
    "gefaehrliche aenderung",
    "datenverlust risiko",
)

_QUALITY_MODE_DATA_SAFETY_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "app",
    "workspace",
    "project",
    "repo",
    "database",
    "sqlite",
    "memory",
    "memories",
    "settings",
    "downloads",
    "files",
    "folder",
    "folders",
    "backup",
    "migration",
    "index",
    "local",
    "dry run",
    "read only",
    "read-only",
    "restore",
    "rollback",
    "confirm",
    "confirmation",
    "projekt",
    "datenbank",
    "erinnerung",
    "erinnerungen",
    "einstellungen",
    "datei",
    "dateien",
    "ordner",
    "backup",
    "migration",
    "lokal",
    "nur lesend",
    "wiederherstellen",
    "rollback",
    "bestaetigen",
    "bestaetigung",
)

_QUALITY_MODE_DEBUG_TRIAGE_MARKERS = (
    "bug triage",
    "incident triage",
    "debug plan",
    "debugging plan",
    "debug this",
    "debug lexa",
    "debug the error",
    "debug error",
    "root cause analysis",
    "root-cause analysis",
    "root cause",
    "rca",
    "crash report",
    "crash investigation",
    "error investigation",
    "error log analysis",
    "log analysis",
    "analyze logs",
    "analyse logs",
    "failing test",
    "failing tests",
    "test failure",
    "regression investigation",
    "production incident",
    "outage",
    "broken workflow",
    "bug report",
    "reproduce bug",
    "repro steps",
    "triage fehler",
    "fehler triage",
    "incident triage",
    "stoerung analysieren",
    "stoerung triage",
    "absturzbericht",
    "absturz analysieren",
    "fehler analysieren",
    "logs analysieren",
    "log analyse",
    "ursachenanalyse",
    "root cause analyse",
    "fehlgeschlagener test",
    "fehlgeschlagene tests",
    "regression untersuchen",
    "bug report",
    "bug reproduzieren",
    "repro schritte",
)

_QUALITY_MODE_DEBUG_TRIAGE_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "app",
    "chat",
    "frontend",
    "backend",
    "agent",
    "tool",
    "memory",
    "release",
    "startup",
    "streaming",
    "workflow",
    "user",
    "production",
    "local",
    "logs",
    "log",
    "stack trace",
    "traceback",
    "error",
    "crash",
    "failure",
    "failing",
    "reproduce",
    "repro",
    "fix",
    "verify",
    "rollback",
    "projekt",
    "lokal",
    "benutzer",
    "fehler",
    "absturz",
    "fehlermeldung",
    "stacktrace",
    "traceback",
    "reproduzieren",
    "repro",
    "beheben",
    "fix",
    "verifizieren",
    "rollback",
)

_QUALITY_MODE_STATUS_HANDOFF_MARKERS = (
    "status update",
    "progress update",
    "project status",
    "work status",
    "implementation summary",
    "change summary",
    "verification summary",
    "handoff summary",
    "handoff note",
    "handoff brief",
    "handoff",
    "where are we",
    "what changed",
    "what was changed",
    "what have we done",
    "what did we accomplish",
    "what is done",
    "what remains",
    "recap progress",
    "summarize progress",
    "summarize the work",
    "statusbericht",
    "fortschrittsbericht",
    "projektstatus",
    "arbeitsstand",
    "zwischenstand",
    "uebergabe",
    "uebergabe summary",
    "uebergabe notiz",
    "wie weit sind wir",
    "wo stehen wir",
    "was hast du erreicht",
    "was haben wir erreicht",
    "was wurde geaendert",
    "was wurde umgesetzt",
    "was ist erledigt",
    "was ist offen",
    "fortschritt zusammenfassen",
    "arbeit zusammenfassen",
)

_QUALITY_MODE_STATUS_HANDOFF_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "project",
    "workspace",
    "repo",
    "repository",
    "implementation",
    "changes",
    "tests",
    "verified",
    "verification",
    "next",
    "risk",
    "risks",
    "done",
    "open",
    "remaining",
    "we",
    "wir",
    "projekt",
    "arbeitsstand",
    "aenderungen",
    "umsetzung",
    "tests",
    "verifiziert",
    "naechste",
    "risiko",
    "risiken",
    "erledigt",
    "offen",
    "rest",
)

_QUALITY_MODE_CLARIFICATION_MARKERS = (
    "ask clarifying questions",
    "ask clarification questions",
    "clarifying questions",
    "clarification questions",
    "clarify requirements",
    "clarify the requirements",
    "clarify scope",
    "missing context",
    "missing information",
    "missing info",
    "state assumptions",
    "list assumptions",
    "call out assumptions",
    "assumption check",
    "ambiguity check",
    "ambiguous requirements",
    "if unclear",
    "when unclear",
    "before proceeding",
    "blocker questions",
    "ask only if needed",
    "frage nach wenn unklar",
    "rueckfragen stellen",
    "rueckfrage stellen",
    "klaerungsfragen",
    "klaerungsfrage",
    "anforderungen klaeren",
    "umfang klaeren",
    "fehlender kontext",
    "fehlende informationen",
    "fehlende infos",
    "annahmen nennen",
    "annahmen auflisten",
    "annahmen pruefen",
    "unklarheiten",
    "unklare anforderungen",
    "falls unklar",
    "wenn unklar",
    "bevor du fortfaehrst",
    "blockierende fragen",
)

_QUALITY_MODE_CLARIFICATION_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "task",
    "project",
    "feature",
    "implementation",
    "plan",
    "decision",
    "requirements",
    "scope",
    "user",
    "workflow",
    "answer",
    "before",
    "proceed",
    "build",
    "create",
    "write",
    "do",
    "aufgabe",
    "projekt",
    "feature",
    "umsetzung",
    "plan",
    "entscheidung",
    "anforderungen",
    "umfang",
    "nutzer",
    "workflow",
    "antwort",
    "bevor",
    "fortfahren",
    "bauen",
    "erstellen",
    "schreiben",
    "machen",
)

_QUALITY_MODE_FEATURE_SPEC_MARKERS = (
    "feature spec",
    "feature specification",
    "product spec",
    "product specification",
    "technical spec",
    "technical specification",
    "requirements spec",
    "requirements document",
    "product requirements",
    "prd",
    "write a spec",
    "draft a spec",
    "create a spec",
    "write requirements",
    "draft requirements",
    "define requirements",
    "write user stories",
    "draft user stories",
    "create user stories",
    "edge cases",
    "non goals",
    "non-goals",
    "out of scope",
    "success metrics",
    "feature spek",
    "produkt spec",
    "produkt spezifikation",
    "technische spezifikation",
    "anforderungsdokument",
    "anforderungen schreiben",
    "anforderungen definieren",
    "user stories schreiben",
    "user stories erstellen",
    "edge cases",
    "randfaelle",
    "nicht ziele",
    "nicht-ziele",
    "ausserhalb scope",
    "erfolgsmetriken",
)

_QUALITY_MODE_FEATURE_SPEC_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "app",
    "product",
    "feature",
    "workflow",
    "user",
    "ux",
    "ui",
    "agent",
    "memory",
    "chat",
    "release",
    "engineering",
    "implementation",
    "build",
    "create",
    "draft",
    "write",
    "define",
    "produkt",
    "funktion",
    "feature",
    "workflow",
    "nutzer",
    "agent",
    "memory",
    "chat",
    "release",
    "entwicklung",
    "umsetzung",
    "bauen",
    "erstellen",
    "entwerfen",
    "schreiben",
    "definieren",
)

_QUALITY_MODE_EVAL_BENCHMARK_MARKERS = (
    "assistant eval",
    "assistant evaluation",
    "answer quality eval",
    "answer quality evaluation",
    "response quality eval",
    "response quality evaluation",
    "quality rubric",
    "evaluation rubric",
    "scoring rubric",
    "rubric for lexa",
    "rubric for assistant",
    "benchmark lexa",
    "benchmark assistant",
    "benchmark assistants",
    "benchmark answers",
    "benchmark responses",
    "compare assistant answers",
    "compare model answers",
    "compare models against",
    "compare against gpt",
    "compare against claude",
    "compare against gemini",
    "gpt comparison",
    "claude comparison",
    "gemini comparison",
    "golden set for lexa",
    "eval dataset",
    "evaluation dataset",
    "regression eval",
    "hallucination eval",
    "antwortqualitaet bewerten",
    "antwortqualitaet evaluation",
    "antwortqualitaet benchmark",
    "antworten bewerten",
    "antworten benchmarken",
    "bewertungsrubrik fuer lexa",
    "rubrik fuer lexa",
    "lexa benchmark",
    "assistant benchmark",
    "modelle gegen",
    "gegen gpt vergleichen",
    "gegen claude vergleichen",
    "gegen gemini vergleichen",
    "golden set fuer lexa",
    "eval datensatz",
    "halluzinationen bewerten",
)

_QUALITY_MODE_EVAL_BENCHMARK_CONTEXT_MARKERS = (
    "lexa",
    "assistant",
    "chat",
    "answer",
    "answers",
    "response",
    "responses",
    "quality",
    "model",
    "models",
    "gpt",
    "claude",
    "gemini",
    "benchmark",
    "rubric",
    "eval",
    "evaluation",
    "score",
    "scores",
    "test",
    "tests",
    "assistant",
    "antwort",
    "antworten",
    "antwortqualitaet",
    "modell",
    "modelle",
    "benchmark",
    "rubrik",
    "bewertung",
    "punkte",
    "testen",
)

_QUALITY_MODE_SUMMARY_EXTRACTION_MARKERS = (
    "summarize meeting",
    "summarize transcript",
    "summarize call",
    "summarize notes",
    "summarize email thread",
    "summarize discussion",
    "create meeting summary",
    "write meeting summary",
    "meeting notes summary",
    "transcript summary",
    "call summary",
    "discussion summary",
    "extract action items",
    "extract decisions",
    "extract todos",
    "extract tasks",
    "extract follow ups",
    "extract follow-ups",
    "turn notes into action items",
    "turn transcript into action items",
    "create meeting minutes",
    "write meeting minutes",
    "make meeting minutes",
    "meeting minutes from notes",
    "meeting minutes from transcript",
    "notes to tasks",
    "transcript to tasks",
    "meeting recap",
    "call recap",
    "meeting brief",
    "transcript brief",
    "meeting zusammenfassen",
    "transkript zusammenfassen",
    "notizen zusammenfassen",
    "call zusammenfassen",
    "meeting summary erstellen",
    "meeting protokoll erstellen",
    "protokoll aus notizen",
    "protokoll aus transkript",
    "action items extrahieren",
    "entscheidungen extrahieren",
    "todos extrahieren",
    "aufgaben extrahieren",
    "follow ups extrahieren",
    "notizen in aufgaben",
    "transkript in aufgaben",
    "meeting recap",
    "meeting brief",
)

_QUALITY_MODE_SUMMARY_EXTRACTION_CONTEXT_MARKERS = (
    "meeting",
    "transcript",
    "call",
    "notes",
    "email",
    "thread",
    "discussion",
    "minutes",
    "action items",
    "decisions",
    "todos",
    "tasks",
    "owner",
    "owners",
    "deadline",
    "deadlines",
    "follow ups",
    "follow-ups",
    "speaker",
    "speakers",
    "meeting",
    "transkript",
    "call",
    "notizen",
    "email",
    "diskussion",
    "protokoll",
    "action items",
    "entscheidungen",
    "todos",
    "aufgaben",
    "owner",
    "deadline",
    "sprecher",
)

_QUALITY_MODE_NUMERIC_ANALYSIS_MARKERS = (
    "calculate",
    "compute",
    "estimate",
    "work out",
    "how much",
    "how many",
    "what is the total",
    "what is the cost",
    "what is the price",
    "what is the percentage",
    "percent change",
    "percentage change",
    "growth rate",
    "conversion rate",
    "cost estimate",
    "cost breakdown",
    "cost comparison",
    "price estimate",
    "roi",
    "return on investment",
    "break even",
    "break-even",
    "average of",
    "sum of",
    "total cost",
    "monthly cost",
    "annual cost",
    "unit economics",
    "berechne",
    "berechnen",
    "rechne",
    "rechnen",
    "kalkuliere",
    "kalkulieren",
    "schaetze",
    "schaetzen",
    "wieviel",
    "wie viel",
    "wie viele",
    "gesamt",
    "gesamtpreis",
    "gesamtkosten",
    "prozentuale aenderung",
    "prozent berechnen",
    "wachstumsrate",
    "kosten schaetzen",
    "kosten berechnen",
    "kostenvergleich",
    "durchschnitt von",
    "summe von",
)

_QUALITY_MODE_NUMERIC_ANALYSIS_CONTEXT_MARKERS = (
    "cost",
    "costs",
    "price",
    "prices",
    "budget",
    "revenue",
    "profit",
    "margin",
    "discount",
    "tax",
    "interest",
    "users",
    "requests",
    "tokens",
    "hours",
    "minutes",
    "days",
    "weeks",
    "months",
    "years",
    "percent",
    "percentage",
    "rate",
    "ratio",
    "growth",
    "conversion",
    "metric",
    "metrics",
    "latency",
    "cost per",
    "per month",
    "per year",
    "kosten",
    "preis",
    "preise",
    "budget",
    "umsatz",
    "gewinn",
    "marge",
    "rabatt",
    "steuer",
    "zinsen",
    "nutzer",
    "nutzern",
    "anfragen",
    "tokens",
    "stunden",
    "minuten",
    "tage",
    "wochen",
    "monate",
    "jahre",
    "prozent",
    "prozentual",
    "prozentuale",
    "rate",
    "verhaeltnis",
    "wachstum",
    "metrik",
    "metriken",
    "latenz",
    "pro monat",
    "pro jahr",
)

_QUALITY_MODE_COMMUNICATION_DRAFT_MARKERS = (
    "draft email",
    "draft an email",
    "draft customer email",
    "draft a customer email",
    "write email",
    "write an email",
    "compose email",
    "compose an email",
    "reply to email",
    "reply to this email",
    "respond to email",
    "draft reply",
    "write reply",
    "compose reply",
    "draft response",
    "write response",
    "draft message",
    "write message",
    "compose message",
    "draft announcement",
    "write announcement",
    "draft slack message",
    "write slack message",
    "draft teams message",
    "write teams message",
    "customer reply",
    "customer response",
    "customer email reply",
    "email reply",
    "email response",
    "outreach email",
    "follow up email",
    "follow-up email",
    "polish this email",
    "rewrite this email",
    "email schreiben",
    "mail schreiben",
    "schreibe eine email",
    "schreib eine email",
    "schreibe eine mail",
    "schreib eine mail",
    "antwort schreiben",
    "antwort formulieren",
    "formuliere eine antwort",
    "kundenantwort",
    "nachricht schreiben",
    "nachricht formulieren",
    "ankuendigung schreiben",
    "schreibe eine ankuendigung",
    "schreib eine ankuendigung",
    "absage formulieren",
    "follow up schreiben",
    "follow-up schreiben",
)

_QUALITY_MODE_COMMUNICATION_DRAFT_CONTEXT_MARKERS = (
    "email",
    "mail",
    "message",
    "reply",
    "response",
    "announcement",
    "slack",
    "teams",
    "customer",
    "client",
    "recipient",
    "audience",
    "subject",
    "tone",
    "cta",
    "call to action",
    "follow up",
    "follow-up",
    "email",
    "mail",
    "nachricht",
    "antwort",
    "ankuendigung",
    "kunde",
    "kunden",
    "empfaenger",
    "zielgruppe",
    "betreff",
    "ton",
    "call to action",
    "naechster schritt",
)

_QUALITY_MODE_LEARNING_EXPLANATION_MARKERS = (
    "teach me",
    "teach",
    "explain step by step",
    "explain like i am",
    "explain like i'm",
    "explain like im",
    "explain for beginners",
    "explain with examples",
    "walk me through",
    "help me understand",
    "learning path",
    "beginner explanation",
    "for beginners",
    "step by step",
    "common mistakes",
    "quiz me",
    "practice exercise",
    "tutorial for",
    "bring mir bei",
    "erklaer mir schritt fuer schritt",
    "erklaere mir schritt fuer schritt",
    "erklaer es schritt fuer schritt",
    "erklaere es schritt fuer schritt",
    "erklaer es fuer anfaenger",
    "erklaere es fuer anfaenger",
    "fuer anfaenger",
    "mit beispielen",
    "ich verstehe nicht",
    "hilf mir verstehen",
    "lernpfad",
    "haeufige fehler",
    "uebung",
    "mini quiz",
)

_QUALITY_MODE_LEARNING_EXPLANATION_CONTEXT_MARKERS = (
    "concept",
    "topic",
    "architecture",
    "system",
    "code",
    "python",
    "javascript",
    "typescript",
    "async",
    "api",
    "database",
    "memory",
    "agent",
    "tool",
    "workflow",
    "math",
    "metric",
    "lexa",
    "assistant",
    "feature",
    "produkt",
    "konzept",
    "thema",
    "architektur",
    "system",
    "code",
    "datenbank",
    "gedaechtnis",
    "agent",
    "werkzeug",
    "workflow",
    "mathe",
    "metrik",
    "assistent",
    "funktion",
)

_QUALITY_MODE_DECISION_COMPARISON_MARKERS = (
    "oder",
    "or",
    "vs",
    "versus",
    "statt",
    "instead",
    "zuerst",
    "first",
    "priorisieren",
    "prioritaet",
    "priority",
)

_SENIOR_CODE_MARKERS = (
    "komplex",
    "senior",
    "10 jahre",
    "erfahrung",
    "profi",
    "advanced",
    "production",
    "best practice",
    "professionell",
    "architektur",
)


def _quality_text_normalized(text: str) -> str:
    value = str(text or "").lower()
    # Mojibake-Schluessel bereits kleingeschrieben, da .lower() oben 'Ã' -> 'ã'
    # bzw. 'Ÿ' -> 'ÿ' umwandelt (sonst koennten die Keys nie matchen).
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "ã¤": "ae",
        "ã¶": "oe",
        "ã¼": "ue",
        "ãÿ": "ss",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return re.sub(r"\s+", " ", value).strip()


def _quality_marker_text(text: str) -> str:
    """Normalize quality-marker matching without changing code/tool parsing."""
    return re.sub(r"[^\w]+", " ", _quality_text_normalized(text)).strip()


# Marker-Konstanten aendern sich nie — normalisierte Form pro Marker cachen,
# damit nicht bei jeder Chat-Nachricht tausende Regex-Operationen anfallen.
@functools.lru_cache(maxsize=4096)
def _quality_marker_padded(marker: str) -> str:
    return f" {_quality_marker_text(marker)} "


def _quality_has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    padded_text = f" {text} "
    return any(_quality_marker_padded(marker) in padded_text for marker in markers)


_CODE_GENERATION_VERB_RE = re.compile(
    r"\b(?:schreib\w*|schreibe\w*|schriebe\w*|generier\w*|erstell\w*|"
    r"entwickel\w*|implementier\w*|programmier\w*|codiere\w*|verbesser\w*|bau\w*|"
    r"mach(?:e|st)?\s+mir|write|generate|create|build|implement|code)\b"
)

_CODE_TARGET_RE = re.compile(
    r"\b(?:python|javascript|typescript|java|rust|golang|php|ruby|swift|kotlin|"
    r"c\+\+|c#|html|css|sql|code|kode|skript|script|programm|program|"
    r"funktion|function|klasse|class|algorithmus|algorithm|api|backend|frontend|"
    r"async|server|cli|regex|library|bibliothek|framework)\b"
)

_TEXT_GENERATION_RE = re.compile(
    r"\b(?:schreib\w*|schreibe\w*|schriebe\w*|formulier\w*|generier\w*|"
    r"erstell\w*|entwirf\w*|erklaer\w*|erklar\w*|zusammenfass\w*|"
    r"mach(?:e|st)?\s+mir|write|draft|generate|create|explain|summarize)\b"
)

_SOURCE_OR_TOOL_BACKED_RE = re.compile(
    r"\b(?:oeffne|open|starte|start|spiel\w*|play|pausier\w*|stoppe|suche|such|"
    r"google|browse|browser|youtube|spotify|wetter|weather|timer|wecker|reminder|"
    r"erinner\w*|todo|todos|notiz|note|kalender|calendar|lautstaerke|volume|"
    r"screenshot|prozess|process|disk|system|datei|file|ordner|folder|git|docker|"
    r"terminal|powershell|cmd|repo|repository|workspace|personal os|quelle|quellen|"
    r"citation|citations|beleg|belege|evidence|research|recherche|web|online|"
    r"internet|aktuell|latest|heute|news|hermes|agent)\b"
)

_LOCAL_CODE_WORK_RE = re.compile(
    r"\b(?:aendere|bearbeite|editiere|fixe|repariere|patch|commit|pull request|"
    r"installiere|fuehre|run|execute|terminal|powershell|cmd|git|docker)\b|"
    r"\bin\s+(?:meinem|diesem|dem)?\s*(?:projekt|repo|repository|datei|ordner|workspace)\b"
)


def _latest_user_context(user_message: Optional[str], conversation_history: Optional[list]) -> str:
    """Return the best user-facing text for tool gating and tool selection."""
    if user_message:
        return user_message
    if conversation_history:
        for msg in reversed(conversation_history):
            if msg.get("role") == "user" and msg.get("content"):
                return msg.get("content", "")
    return ""


def _should_disable_tools_for_text_generation(user_message: Optional[str]) -> bool:
    """Detect requests that should be answered by the model, not local tools."""
    text = _quality_text_normalized(user_message or "")
    if not text:
        return False

    has_code_target = bool(_CODE_TARGET_RE.search(text))
    has_generation_verb = bool(_CODE_GENERATION_VERB_RE.search(text))
    if has_code_target and has_generation_verb:
        return not bool(_LOCAL_CODE_WORK_RE.search(text))

    if _SOURCE_OR_TOOL_BACKED_RE.search(text):
        return False

    return bool(_TEXT_GENERATION_RE.search(text))


def _system_extra_requests_tool_mode(system_extra: Optional[str]) -> bool:
    """Agent/Hermes system contexts must keep tools even for code-heavy tasks."""
    text = _quality_text_normalized(system_extra or "")
    if not text:
        return False
    return any(marker in text for marker in (
        "agent modus",
        "agent-modus",
        "hermes worker",
        "pc worker",
        "lexa tool",
        "tool gateway",
    ))


def _detect_code_quality_mode(text: str) -> str:
    """Return stricter instructions for code-generation answers."""
    if not _CODE_TARGET_RE.search(text):
        return ""

    is_code_generation = bool(_CODE_GENERATION_VERB_RE.search(text))
    wants_senior_level = any(marker in text for marker in _SENIOR_CODE_MARKERS)
    if not (is_code_generation or wants_senior_level):
        return ""

    return (
        "Anspruch: Senior-Code-Antwort. Liefere keinen aufgeblasenen Spielzeugcode, "
        "sondern aktuellen, plausibel lauffaehigen Code mit passender Struktur. "
        "Nutze keine unbenutzten Imports/Parameter und keine deprecated APIs. "
        "Wenn der User komplex/Senior/10 Jahre verlangt: kurz Architektur-Idee nennen, "
        "dann ein robustes Beispiel mit klaren Grenzen, Typing/Config/Logging/Tests "
        "oder Fehlerbehandlung wo sinnvoll. Bei ML, Daten und Zeitreihen besonders "
        "auf Leakage, zeitliche Splits, Scaler-Fit, Tensor-Shapes, Ausrichtung von "
        "Targets/Predictions und sinnvolle Evaluation achten. Wenn du Code verbesserst, "
        "pruefe explizit, ob die neue Version noch logisch und technisch laeuft."
    )


def _detect_quality_mode(user_message: Optional[str], conversation_history: Optional[list] = None) -> str:
    """Return a compact instruction when the task needs top-tier answer discipline."""
    text = _quality_text_normalized(user_message or "")
    if not text:
        return ""

    code_quality_mode = _detect_code_quality_mode(text)
    if code_quality_mode:
        return code_quality_mode

    marker_text = _quality_marker_text(text)
    complex_requested = _quality_has_any_marker(marker_text, _QUALITY_MODE_COMPLEX_MARKERS)
    lexa_named = _quality_has_any_marker(marker_text, ("lexa", "assistant"))
    product_action_requested = _quality_has_any_marker(marker_text, _QUALITY_MODE_PRODUCT_ACTION_MARKERS)
    score = 0
    if _quality_has_any_marker(marker_text, _QUALITY_MODE_TOP_TIER_MARKERS):
        score += 2
    if complex_requested:
        score += 1
    if (
        _quality_has_any_marker(marker_text, ("ziel",)) and
        _quality_has_any_marker(marker_text, ("lexa", "app", "assistant"))
    ):
        score += 1
    lexa_product_requested = (
        lexa_named and
        product_action_requested and
        (complex_requested or _quality_has_any_marker(marker_text, _QUALITY_MODE_LEXA_PRODUCT_MARKERS))
    )
    if lexa_product_requested:
        score += 1
    source_verification_requested = (
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_SOURCE_MARKERS) and
            _quality_has_any_marker(marker_text, _QUALITY_MODE_VERIFICATION_MARKERS)
        ) or
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DIRECT_ANSWER_VERIFICATION_MARKERS)
    )
    if source_verification_requested:
        score += 2
    security_privacy_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_SECURITY_PRIVACY_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_SECURITY_PRIVACY_CONTEXT_MARKERS)
    )
    if security_privacy_requested:
        score += 2
    accessibility_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_ACCESSIBILITY_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_ACCESSIBILITY_CONTEXT_MARKERS)
    )
    if accessibility_requested:
        score += 2
    performance_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_PERFORMANCE_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_PERFORMANCE_CONTEXT_MARKERS)
    )
    if performance_requested:
        score += 2
    testing_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_TESTING_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_TESTING_CONTEXT_MARKERS)
    )
    if testing_requested:
        score += 2
    memory_context_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_MEMORY_CONTEXT_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_MEMORY_CONTEXT_CONTEXT_MARKERS)
    )
    if memory_context_requested:
        score += 2
    agent_tool_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_AGENT_TOOL_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_AGENT_TOOL_CONTEXT_MARKERS)
    )
    if agent_tool_requested:
        score += 2
    ship_check_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_SHIP_CHECK_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_SHIP_CHECK_CONTEXT_MARKERS)
    )
    if ship_check_requested:
        score += 2
    data_safety_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DATA_SAFETY_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DATA_SAFETY_CONTEXT_MARKERS)
    )
    if data_safety_requested:
        score += 2
    debug_triage_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DEBUG_TRIAGE_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DEBUG_TRIAGE_CONTEXT_MARKERS)
    )
    if debug_triage_requested:
        score += 2
    status_handoff_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_STATUS_HANDOFF_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_STATUS_HANDOFF_CONTEXT_MARKERS)
    )
    if status_handoff_requested:
        score += 2
    clarification_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_CLARIFICATION_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_CLARIFICATION_CONTEXT_MARKERS)
    )
    if clarification_requested:
        score += 2
    feature_spec_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_FEATURE_SPEC_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_FEATURE_SPEC_CONTEXT_MARKERS)
    )
    if feature_spec_requested:
        score += 2
    eval_benchmark_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_EVAL_BENCHMARK_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_EVAL_BENCHMARK_CONTEXT_MARKERS)
    )
    if eval_benchmark_requested:
        score += 2
    summary_extraction_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_SUMMARY_EXTRACTION_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_SUMMARY_EXTRACTION_CONTEXT_MARKERS)
    )
    if summary_extraction_requested:
        score += 2
    numeric_context_signal = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_NUMERIC_ANALYSIS_CONTEXT_MARKERS) or
        bool(re.search(r"\d\s*(?:[%+\-*/x=]|percent|prozent)\s*\d", text)) or
        (
            bool(re.search(r"\d", text)) and
            bool(re.search(
                r"\b(?:eur|usd|euro|dollar|tokens?|users?|requests?|hours?|minutes?|days?|weeks?|"
                r"months?|years?|stunden?|minuten?|tage?|wochen?|monate?|jahre?|kosten|preis|"
                r"umsatz|budget|revenue|costs?|prices?|rate|ratio|growth|prozent(?:ual\w*)?|"
                r"percent|nutzern?)\b",
                text,
            ))
        )
    )
    numeric_analysis_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_NUMERIC_ANALYSIS_MARKERS) and
        numeric_context_signal
    )
    if numeric_analysis_requested:
        score += 2
    communication_draft_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_COMMUNICATION_DRAFT_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_COMMUNICATION_DRAFT_CONTEXT_MARKERS)
    )
    if communication_draft_requested:
        score += 2
    learning_explanation_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_LEARNING_EXPLANATION_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_LEARNING_EXPLANATION_CONTEXT_MARKERS)
    )
    if learning_explanation_requested:
        score += 2
    planning_structure_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_PLANNING_MARKERS) and
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_PLANNING_STRUCTURE_MARKERS)
    )
    constrained_planning_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_CONSTRAINT_MARKERS) and
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_PLANNING_MARKERS) or
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_INTENT_MARKERS)
        )
    )
    risk_planning_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DIRECT_RISK_MARKERS) or
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_RISK_MARKERS) and
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_RISK_CONTEXT_MARKERS)
        )
    )
    decision_planning_requested = (
        _quality_has_any_marker(marker_text, _QUALITY_MODE_DIRECT_DECISION_MARKERS) or
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_INTENT_MARKERS) and
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_STRUCTURE_MARKERS)
        ) or
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_ASK_MARKERS) and
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_COMPARISON_MARKERS)
        ) or
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_BETTER_MARKERS) and
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_COMPARISON_MARKERS)
        ) or
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_COMPARE_MARKERS) and
            (
                _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_COMPARISON_MARKERS) or
                _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_STRUCTURE_MARKERS)
            )
        ) or
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_TRADEOFF_MARKERS) and
            (
                _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_COMPARISON_MARKERS) or
                _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_TRADEOFF_CONTEXT_MARKERS)
            )
        ) or
        (
            _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_SCORING_MARKERS) and
            (
                _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_STRUCTURE_MARKERS) or
                _quality_has_any_marker(marker_text, _QUALITY_MODE_DECISION_COMPARISON_MARKERS)
            )
        ) or
        planning_structure_requested or
        constrained_planning_requested or
        risk_planning_requested
    )
    if decision_planning_requested:
        score += 2
    if len(text) > 160 or text.count("?") >= 2:
        score += 1
    if conversation_history and len(conversation_history) >= 8:
        score += 1

    if score < 2:
        return ""

    source_quality_hint = (
        " Bei Quellen-/Faktencheck-Aufgaben extrahiere checkbare Claims, verknuepfe "
        "sie mit konkreten Quellen oder Belegen, und markiere ungepruefte Aussagen klar."
        if source_verification_requested else ""
    )
    security_privacy_hint = (
        " Bei Security-/Privacy-Aufgaben erstelle eine knappe Threat-/Privacy-Review: "
        "Assets/Daten, Trust Boundaries, Permissions, Data-loss-/Exfiltration-Risiken, "
        "Missbrauchsfaelle, Mitigations, offene Fragen und konkrete Verifikationsschritte."
        if security_privacy_requested else ""
    )
    accessibility_hint = (
        " Bei Accessibility-/UX-Aufgaben erstelle eine knappe Accessibility-Review: "
        "Tastaturfluss, Fokusreihenfolge, Screenreader-/ARIA-Labels, Kontrast, "
        "Reduced Motion, Fehler-/Loading-Zustaende, mobile Responsiveness, offene "
        "Barrieren und konkrete Verifikationstests."
        if accessibility_requested else ""
    )
    performance_hint = (
        " Bei Performance-Aufgaben erstelle eine knappe Performance-Review: "
        "Baseline/Metrik, Zielwert oder Performance-Budget, Bottleneck-Hypothesen, "
        "Messmethode, kleinste sichere Optimierung, Regressionstest und Rollout-Risiko."
        if performance_requested else ""
    )
    testing_hint = (
        " Bei Test-/QA-Aufgaben erstelle eine knappe Teststrategie: Scope, "
        "Akzeptanzkriterien, Testmatrix, kritische Regressionen, Smoke-Checks, "
        "manuelle Randfaelle, Automationskandidaten, Verifikationsbefehle und Rest-Risiko."
        if testing_requested else ""
    )
    memory_context_hint = (
        " Bei Memory-/Kontext-Aufgaben trenne stabile Fakten, Praeferenzen, Aufgaben, "
        "Entscheidungen, Ideen und unsichere Annahmen. Markiere Privacy-/Consent-Risiken, "
        "schlage Draft- statt Stable-Memory-Writes vor und nenne Loesch-/Korrekturpunkte "
        "sowie Verifikationsfragen."
        if memory_context_requested else ""
    )
    agent_tool_hint = (
        " Bei Agent-/Tool-Aufgaben erstelle eine knappe Tool-Execution-Review: Ziel, "
        "erlaubte Tools/Kontext, benoetigte Berechtigungen, Read-only-/Dry-run-Schritt, "
        "geplante Aktionen, Risiken, Stop-/Approval-Kriterien, Verifikationssignal "
        "und Rollback/Recovery."
        if agent_tool_requested else ""
    )
    ship_check_hint = (
        " Bei Release-/Ship-Check-Aufgaben erstelle eine knappe Ship-Readiness-Review: "
        "User-facing UX, Accessibility, Performance, Reliability, Privacy/Security, "
        "Datenverlust-Risiken, Docs/Onboarding, Tests, Migration/Rollback, Launch-Blocker, "
        "Must-fix vor Publish, Nice-to-have, Verifikationsbefehle und klare Go/No-go-Empfehlung."
        if ship_check_requested else ""
    )
    data_safety_hint = (
        " Bei datenveraendernden oder destruktiven Aktionen erstelle eine knappe Data-Safety-Review: "
        "betroffene Daten, Reversibilitaet, Backup/Snapshot, Dry-run-/Read-only-Vorcheck, "
        "explizite Bestaetigungspunkte, kleinster sicherer Schritt, Restore/Rollback und Nachpruefung."
        if data_safety_requested else ""
    )
    debug_triage_hint = (
        " Bei Bug-/Incident-/Debugging-Aufgaben erstelle eine knappe Triage: Symptom, "
        "Impact, Repro-Schritte, erwartetes vs. tatsaechliches Verhalten, zuletzt geaendert, "
        "relevante Logs/Stacktraces, Hypothesen nach Wahrscheinlichkeit, kleinste sichere "
        "Fix-Route, Regressionstest und Verifikationssignal."
        if debug_triage_requested else ""
    )
    status_handoff_hint = (
        " Bei Status-/Handoff-Aufgaben liefere eine knappe Arbeitsuebergabe: erledigt, "
        "geaendert, verifiziert, offen, Risiken/Blocker, naechster sinnvoller Schritt "
        "und relevante Dateien oder Tests. Trenne gesicherte Fakten von Annahmen."
        if status_handoff_requested else ""
    )
    clarification_hint = (
        " Bei unklaren Anforderungen trenne Annahmen von Fakten, nenne fehlenden Kontext, "
        "waehle sichere Defaults fuer reversible Schritte und stelle maximal drei konkrete "
        "Rueckfragen nur, wenn die Antwort sonst riskant oder blockierend waere."
        if clarification_requested else ""
    )
    feature_spec_hint = (
        " Bei Feature-/Requirements-Spezifikationen liefere eine knappe Spec: Problem/Ziel, "
        "Zielnutzer, Use Cases oder User Stories, Scope und Nicht-Ziele, Akzeptanzkriterien, "
        "Edge Cases, UX-/Daten-/Security-Hinweise, Erfolgsmessung, offene Fragen und kleinster MVP."
        if feature_spec_requested else ""
    )
    eval_benchmark_hint = (
        " Bei Eval-/Benchmark-Aufgaben definiere eine messbare Rubric: Testset/Golden Set, "
        "Kriterien mit Gewichtung, Bewertungsbeispiele, Baseline/Vergleichsmodelle, "
        "Fehlertypen wie Halluzinationen oder Auslassungen, Auswertung und Regression-Gate."
        if eval_benchmark_requested else ""
    )
    summary_extraction_hint = (
        " Bei Meeting-/Notizen-/Transcript-Zusammenfassungen extrahiere TL;DR, "
        "Entscheidungen, Action Items mit Owner/Deadline, offene Fragen, Risiken, "
        "Follow-ups und markiere unklare Sprecher oder fehlende Daten."
        if summary_extraction_requested else ""
    )
    numeric_analysis_hint = (
        " Bei Rechen-/Zahlenanalyse-Aufgaben nenne Annahmen, Einheiten/Waehrung, "
        "Formel/Rechenschritte, Zwischenergebnisse, Rundung, Plausibilitaetscheck "
        "und fehlende oder unsichere Eingaben."
        if numeric_analysis_requested else ""
    )
    communication_draft_hint = (
        " Bei Kommunikations-/Antwortentwurfs-Aufgaben klaere Ziel, Empfaenger/Audience, "
        "Ton, Kernbotschaft, Betreff/Opening, CTA/naechster Schritt, Laenge, sensible "
        "Infos und liefere bei Bedarf eine knappe Tonvariante."
        if communication_draft_requested else ""
    )
    learning_explanation_hint = (
        " Bei Lern-/Erklaer-Aufgaben starte mit dem angenommenen Wissensstand, "
        "erklaere vom mentalen Modell zum konkreten Beispiel, nenne haeufige "
        "Fehlannahmen, gib eine kleine Uebung oder Checkfrage und biete den naechsten "
        "Lernschritt an."
        if learning_explanation_requested else ""
    )
    lexa_product_hint = (
        " Bei Lexa-/Assistant-Produktverbesserungen priorisiere kleine sichere "
        "High-Impact-Schritte, schuetze bestehende User-Aenderungen, vermeide grosse "
        "riskante Refactors, und verifiziere fokussiert mit passenden Tests oder Guardrails."
        if lexa_product_requested else ""
    )
    decision_quality_hint = (
        " Bei Entscheidungs-/Planungsaufgaben liefere einen kompakten Decision Brief: "
        "Ziel/Entscheidung, Fakten, Annahmen, Optionen, Tradeoffs/Risiken, "
        "Reversibilitaet, Empfehlung mit Confidence, offene Fragen und naechste Schritte. "
        "Wenn Bewertung, Kriterien, Gewichtung, Scoring oder Matrix verlangt sind: "
        "nutze eine knappe Kriterien-/Score-Tabelle und erklaere die Gewichtung kurz. "
        "Bei Roadmaps/Umsetzungsplaenen gliedere nach Phasen/Meilensteinen, Ownern, "
        "Abhaengigkeiten, Risiken, Review-Punkten und dem kleinsten naechsten Schritt. "
        "Bei Deadline/Budget/Ressourcen-Constraints nenne harte Grenzen, Annahmen, "
        "Scope-Kuerzungen, Risiko-Puffer und eine realistische Minimalversion. "
        "Bei Risiko-/Rollback-/Mitigation-Aufgaben liste Failure Modes, Impact/Likelihood, "
        "Early-Warning-Signale, Mitigations, Owner, Rollback-/Abort-Kriterien und Verifikation. "
        "Gib nur eine kurze Begruendung statt verborgener Chain-of-Thought."
        if decision_planning_requested else ""
    )
    return (
        "Anspruch: Top-tier Assistant Quality. Handle proaktiv, waehle den "
        "kleinsten sinnvollen naechsten Schritt, nutze vorhandenen Kontext und "
        "Evidenz, trenne bei Bedarf Fakten/Annahmen/Entscheidungen/Risiken/"
        "naechste Schritte, und belege am Ende kurz was getan oder geprueft wurde. "
        "Frage nur, wenn eine Entscheidung riskant oder blockierend ist."
        f"{source_quality_hint}"
        f"{security_privacy_hint}"
        f"{accessibility_hint}"
        f"{performance_hint}"
        f"{testing_hint}"
        f"{memory_context_hint}"
        f"{agent_tool_hint}"
        f"{ship_check_hint}"
        f"{data_safety_hint}"
        f"{debug_triage_hint}"
        f"{status_handoff_hint}"
        f"{clarification_hint}"
        f"{feature_spec_hint}"
        f"{eval_benchmark_hint}"
        f"{summary_extraction_hint}"
        f"{numeric_analysis_hint}"
        f"{communication_draft_hint}"
        f"{learning_explanation_hint}"
        f"{decision_quality_hint}"
        f"{lexa_product_hint}"
    )


def _build_messages(
    user_message: Optional[str],
    conversation_history: Optional[list] = None,
    system_extra: Optional[str] = None,
) -> list[dict]:
    """Build message list with system prompt, memory context, datetime, productivity status.

    Phase 41: Enhanced conversation intelligence with mood detection,
    topic tracking, and smarter context injection.

    Smart context window:
    - <= 20 messages: include all verbatim
    - > 20 messages: locally summarize older messages + include last 20 verbatim
    """
    system_content, _ = _build_system_content_cached()

    dynamic_parts = []

    # Inject current date/time with rich context
    now = datetime.now()
    weekdays_de = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    weekday = weekdays_de[now.weekday()]
    hour = now.hour
    if 6 <= hour < 11:
        tageszeit = "Morgen"
    elif 11 <= hour < 14:
        tageszeit = "Mittag"
    elif 14 <= hour < 18:
        tageszeit = "Nachmittag"
    elif 18 <= hour < 22:
        tageszeit = "Abend"
    else:
        tageszeit = "Nacht"
    is_weekend = now.weekday() >= 5
    time_context = f"{weekday}, {now.strftime('%d.%m.%Y')} — {now.strftime('%H:%M')} Uhr (Tageszeit: {tageszeit})"
    if is_weekend:
        time_context += " [Wochenende]"
    dynamic_parts.append(f"\n\nAKTUELLE ZEIT: {time_context}")

    # Conversation mood detection — helps AI adapt tone
    mood = _detect_conversation_mood(conversation_history, user_message)
    if mood:
        dynamic_parts.append(f"\n\n[KONVERSATIONS-KONTEXT] {mood}")

    # Topic continuity — helps AI stay on topic
    quality_mode = _detect_quality_mode(user_message, conversation_history)
    if quality_mode:
        dynamic_parts.append(f"\n\n[QUALITAETSMODUS]\n{quality_mode}")

    topic = _detect_conversation_topic(conversation_history)
    if topic:
        dynamic_parts.append(f"\n\n[{topic.upper()}]")

    # Per-message context: FAST keyword search (semantic search is too slow ~3s)
    # Only search if message has enough substance (skip greetings and short commands)
    if user_message and len(user_message.split()) >= 3:
        try:
            from backend.memory import search_memory
            # Langlebiger Modul-Executor statt pro Request einen neuen anzulegen:
            # nur das Future mit 0.5s-Timeout abwarten. Ein haengender Such-Thread
            # blockiert den Request-Pfad nicht (kein wait), belegt aber hoechstens
            # einen der wenigen Worker des geteilten Executors.
            future = _memory_search_executor.submit(search_memory, user_message, 3)
            try:
                memory_results = future.result(timeout=0.5)
            except concurrent.futures.TimeoutError:
                memory_results = []
                logger.warning("Memory search timed out (>0.5s) — skipping context")
            if memory_results:
                mem_text = "\n".join(
                    f"- [{m['category']}] {m['content']}" for m in memory_results
                )
                dynamic_parts.append(f"\n\nRELEVANTES GEDÄCHTNIS:\n{mem_text}")
        except Exception as e:
            logger.debug(f"Memory context skipped: {e}")

    # Pending confirmation context — so the AI knows what's awaiting approval
    try:
        from backend.shared import get_pending_confirmation
        pending = get_pending_confirmation()
        if pending:
            action_name = pending.get("action", "?")
            params = pending.get("params", {})
            params_str = (
                ", ".join(f"{k}={_sanitize_pending_param_value(v)}" for k, v in params.items())
                if params else "keine"
            )
            dynamic_parts.append(
                f"\n\n[AUSSTEHENDE BESTÄTIGUNG]\n"
                f"Aktion: {action_name}({params_str})\n"
                f"Wenn der User 'ja', 'bestätige', 'mach es', 'ok' oder ähnliches sagt, "
                f"führe GENAU diese Aktion erneut aus mit denselben Parametern."
            )
    except Exception as e:
        logger.debug(f"Pending confirmation context skipped: {e}")

    # Productivity Context — enriched with actionable hints (cached 5s)
    try:
        from backend.productivity import productivity_stats, pomodoro_status
        now_ts = _time.time()
        with _productivity_cache_lock:
            if (now_ts - _productivity_cache["ts"]) > _PRODUCTIVITY_CACHE_TTL:
                _productivity_cache["data"] = {
                    "stats": productivity_stats(),
                    "pomo": pomodoro_status(),
                }
                _productivity_cache["ts"] = now_ts
            cached = _productivity_cache["data"]
        stats = cached["stats"]
        pomo = cached["pomo"]
        prod_lines = []
        if stats.get("open_todos"):
            count = stats["open_todos"]
            prod_lines.append(f"Offene To-Dos: {count}")
            if count >= 10:
                prod_lines.append("(viele offene Tasks — ggf. priorisieren vorschlagen)")
        if stats.get("done_today"):
            prod_lines.append(f"Heute erledigt: {stats['done_today']}")
        if pomo.get("running"):
            task = pomo.get("task") or "kein Task"
            remaining = pomo.get("remaining_sec", 0)
            mins = remaining // 60
            prod_lines.append(f"Pomodoro läuft: '{task}' — noch {mins} Min")
            if mins <= 2:
                prod_lines.append("(Pomodoro fast fertig!)")
        if stats.get("focus_mode"):
            prod_lines.append("Fokus-Modus: AN")
        if prod_lines:
            dynamic_parts.append("\n\nPRODUKTIVITÄT-STATUS: " + " | ".join(prod_lines))
    except Exception as e:
        logger.debug(f"Productivity context skipped: {e}")

    # Smart conversation context: summarize older messages instead of discarding
    truncated_history = conversation_history
    if conversation_history and len(conversation_history) > _MAX_CONVERSATION_HISTORY:
        old_messages = conversation_history[:-_MAX_CONVERSATION_HISTORY]
        recent_messages = conversation_history[-_MAX_CONVERSATION_HISTORY:]

        summary = _summarize_messages_local(old_messages)
        dynamic_parts.append(f"\n\n[GESPRÄCHS-ZUSAMMENFASSUNG]\n{summary}")

        truncated_history = recent_messages
        logger.info(
            f"Summarized {len(old_messages)} older messages, "
            f"keeping {_MAX_CONVERSATION_HISTORY} recent messages verbatim"
        )

    full_system = system_content + "".join(dynamic_parts)

    # Phase 46: Append agent-mode instructions if provided
    if system_extra:
        full_system += "\n\n" + system_extra

    # Check token budget — actively trim if needed
    truncated_history = _check_token_budget(full_system, truncated_history or [])

    messages = [{"role": "system", "content": full_system}]
    if truncated_history:
        messages.extend(truncated_history)
    # Phase 46: user_message=None means the last message is already in history
    if user_message is not None:
        messages.append({"role": "user", "content": user_message})
    return messages


# ══════════════════════════════════════════════════
#  MAIN CHAT (non-streaming)
# ══════════════════════════════════════════════════

def chat(
    user_message: Optional[str],
    conversation_history: Optional[list] = None,
    system_extra: Optional[str] = None,
) -> dict:
    """Send message through provider chain with native tool use.

    Returns a dict:
      {"type": "text", "content": "..."} — plain text response
      {"type": "tool_call", "tool_calls": [...], "content": "..."} — tool call
      {"type": "error", "content": "..."} — error fallback

    Groq/OpenAI/Gemini use native function calling (tools parameter).

    Phase 46: system_extra appends agent-mode instructions to the system prompt.
    user_message=None means the last user message is already in conversation_history.
    """
    selected_model = _get_selected_model_meta()

    # Build messages
    messages = _build_messages(user_message, conversation_history, system_extra=system_extra)

    # Get context-relevant tools for native function calling
    tools = None
    try:
        from backend.config import TOOL_USE_ENABLED
        if TOOL_USE_ENABLED:
            from backend.tool_registry import get_tools_for_context
            # Phase 46: when user_message is None (agent mode), derive context from history.
            tool_context = _latest_user_context(user_message, conversation_history)
            if not _system_extra_requests_tool_mode(system_extra) and _should_disable_tools_for_text_generation(tool_context):
                logger.debug("Skipping tools for direct text/code generation request")
            else:
                tools = get_tools_for_context(tool_context)
                logger.debug(f"Sending {len(tools)} tools to {selected_model['provider']}")
    except Exception as e:
        logger.warning(f"Tool registry unavailable: {e}")

    # Try selected provider
    result = _chat_with_selected_provider(messages, selected_model, tools=tools)
    if result:
        _save_chat_result(user_message, result)
        return result

    # If the active provider is unavailable, quietly try configured provider fallbacks.
    result = _chat_with_provider_fallbacks(messages, selected_model, tools=tools)
    if result:
        _save_chat_result(user_message, result)
        return result

    # If tool use caused the failure, retry WITHOUT tools (conversational fallback)
    if tools:
        logger.info("Retrying without tools (tool_use may have caused failure)...")
        result = _chat_with_selected_provider(messages, selected_model, tools=None)
        if result:
            _save_chat_result(user_message, result)
            return result

        result = _chat_with_provider_fallbacks(messages, selected_model, tools=None)
        if result:
            _save_chat_result(user_message, result)
            return result

    return {
        "type": "error",
        "content": lexa_user_error("ai_unavailable"),
    }


# ══════════════════════════════════════════════════
#  STREAMING CHAT (SSE)
# ══════════════════════════════════════════════════

def chat_stream(
    user_message: str,
    conversation_history: Optional[list] = None,
    system_extra: Optional[str] = None,
    disable_tools: bool = False,
    exclude_tools: Optional[set] = None,
) -> Generator[str | dict, None, None]:
    """Yield text chunks OR a tool_call dict from streaming providers.

    Phase 40: When the LLM responds with a tool call during streaming,
    we accumulate the tool call chunks and yield a single dict at the end:
      {"type": "tool_call", "tool_calls": [...]}

    For plain text responses, we yield string chunks as before.
    Uses shared retry logic with exponential backoff and model fallback.

    system_extra: appended to the system prompt (e.g. live web sources for a
      grounded answer). disable_tools: skip native function calling entirely
      (used when the answer is already grounded and should be plain text).
    """
    selected_model = _get_selected_model_meta()
    messages = _build_messages(user_message, conversation_history, system_extra=system_extra)

    # Get tools for native function calling
    tools = None
    if disable_tools:
        logger.debug("Stream tools disabled (web-grounded / forced text answer)")
    else:
        try:
            from backend.config import TOOL_USE_ENABLED
            if TOOL_USE_ENABLED:
                from backend.tool_registry import get_tools_for_context
                tool_context = _latest_user_context(user_message, conversation_history)
                if _should_disable_tools_for_text_generation(tool_context):
                    logger.debug("Skipping stream tools for direct text/code generation request")
                else:
                    tools = get_tools_for_context(tool_context, max_tools=20)
                    if tools and exclude_tools:
                        # z.B. nach einem Web-Grounding-Hop: web_search ausschliessen
                        # (kein Re-Search), Companion-Tools aber verfuegbar lassen.
                        tools = [t for t in tools if t.get("function", {}).get("name") not in exclude_tools]
        except Exception as e:
            logger.warning(f"Tool registry unavailable for stream: {e}")

    full_text_parts: list[str] = []
    streamed = False

    # Try primary provider streaming with retry/fallback
    try:
        stream = _stream_with_selected_provider(messages, selected_model, tools=tools)
        stream_model = selected_model
        if stream is None:
            stream, fallback_model = _stream_with_provider_fallbacks(messages, selected_model, tools=tools)
            if fallback_model is not None:
                stream_model = fallback_model
        if stream is not None:
            # Accumulators for streaming tool calls
            tool_call_chunks: dict[int, dict] = {}  # index -> {id, name, arguments_parts}

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Handle tool call deltas
                if getattr(delta, "tool_calls", None):
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {
                                "id": getattr(tc_delta, "id", None) or "",
                                "name": "",
                                "arguments_parts": [],
                            }
                        # Accumulate (don't overwrite) — only set id/name if not empty
                        tc_id = getattr(tc_delta, "id", None)
                        if tc_id and not tool_call_chunks[idx]["id"]:
                            tool_call_chunks[idx]["id"] = tc_id
                        function_delta = getattr(tc_delta, "function", None)
                        if getattr(function_delta, "name", None):
                            tool_call_chunks[idx]["name"] = function_delta.name
                        if getattr(function_delta, "arguments", None):
                            tool_call_chunks[idx]["arguments_parts"].append(
                                function_delta.arguments
                            )
                    continue

                # Handle text content deltas
                content = delta.content if hasattr(delta, "content") else None
                if content:
                    full_text_parts.append(content)
                    yield content

            # If we accumulated tool calls, yield them as a single dict
            if tool_call_chunks:
                tool_calls = []
                for idx in sorted(tool_call_chunks.keys()):
                    tc = tool_call_chunks[idx]
                    args_str = "".join(tc["arguments_parts"])
                    args = _parse_tool_arguments(args_str)
                    if not isinstance(args, dict):
                        logger.warning(
                            "Invalid streamed tool call args for '%s' kept for schema rejection: %s",
                            tc["name"],
                            str(args)[:200],
                        )
                    tool_calls.append({
                        "id": tc["id"],
                        "name": tc["name"],
                        "arguments": args,
                    })
                logger.info(f"Stream tool call: {[tc['name'] for tc in tool_calls]}")
                tc_names = [tc["name"] for tc in tool_calls]
                _save_interaction(user_message, f"[Tool: {', '.join(tc_names)}]")
                yield {"type": "tool_call", "tool_calls": tool_calls}
                return

            if not full_text_parts:
                raise RuntimeError(f"{stream_model['provider']} stream returned no content")

            full_text = "".join(full_text_parts)
            logger.info(f"{stream_model['provider'].title()} stream complete ({len(full_text)} chars)")
            _save_interaction(user_message, full_text)
            streamed = True
    except Exception as e:
        logger.warning(f"{selected_model['provider'].title()} stream failed: {e}")
        if full_text_parts:
            partial = "".join(full_text_parts)
            logger.warning(f"Partial stream ({len(partial)} chars) — saving and stopping")
            yield lexa_user_error("stream_disconnected")
            _save_interaction(user_message, partial)
            return

        # If tools were sent, retry stream WITHOUT tools (conversational fallback).
        # Konsistent zum non-streaming chat()-Pfad: dort wird IMMER ein Retry ohne
        # Tools versucht. Die fruehere Bedingung haengte an Groq-spezifischer
        # Fehlererkennung (TOOL_USE_FAILED) und griff bei Gemini-Tool-Fehlern
        # praktisch nie. Da noch kein Text gestreamt wurde (siehe oben), ist der
        # Retry gefahrlos und liefert dem User eine Textantwort statt nur ai_unavailable.
        if tools:
            logger.info("Retrying stream without tools (tool_use may have caused failure)...")
            try:
                stream_retry = _stream_with_selected_provider(messages, selected_model, tools=None)
                if stream_retry is not None:
                    retry_parts: list[str] = []
                    for chunk in stream_retry:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        content = delta.content if hasattr(delta, "content") else None
                        if content:
                            retry_parts.append(content)
                            yield content
                    if retry_parts:
                        _save_interaction(user_message, "".join(retry_parts))
                        return
            except Exception as retry_err:
                logger.warning(f"Stream retry without tools also failed: {retry_err}")

        stream_fallback, fallback_model = _stream_with_provider_fallbacks(messages, selected_model, tools=None)
        if stream_fallback is not None:
            try:
                retry_parts: list[str] = []
                for chunk in stream_fallback:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    content = delta.content if hasattr(delta, "content") else None
                    if content:
                        retry_parts.append(content)
                        yield content
                if retry_parts:
                    logger.info(f"{fallback_model['provider'].title()} stream fallback complete ({len(''.join(retry_parts))} chars)")
                    _save_interaction(user_message, "".join(retry_parts))
                    return
            except Exception as fallback_err:
                logger.warning(f"Stream provider fallback also failed: {fallback_err}")

    if streamed:
        return

    yield lexa_user_error("ai_unavailable")


# ── Interaction Logging ──
_last_saved_hash: Optional[str] = None
_save_interaction_lock = threading.Lock()


def _save_interaction(user_msg: str, ai_reply: str) -> None:
    """Save interaction to memory for future context. Thread-safe dedup."""
    global _last_saved_hash
    interaction_hash = hashlib.sha256(f"{user_msg}:{ai_reply}".encode()).hexdigest()[:16]
    with _save_interaction_lock:
        if interaction_hash == _last_saved_hash:
            logger.debug("Skipping duplicate interaction save")
            return
    try:
        from backend.memory import auto_remember
        auto_remember(user_msg, ai_reply)
    except Exception as e:
        # Hash NICHT setzen, damit ein erneuter Speicherversuch moeglich bleibt.
        logger.error(f"Failed to save interaction: {e}", exc_info=True)
        return
    with _save_interaction_lock:
        _last_saved_hash = interaction_hash


def _save_chat_result(user_message: Optional[str], result: dict) -> None:
    """Persist a successful chat result without exposing fallback internals."""
    content_for_save = result.get("content", "")
    if result.get("type") == "tool_call":
        tc_names = [tc.get("name", "") for tc in result.get("tool_calls", []) if isinstance(tc, dict)]
        content_for_save = content_for_save or f"[Tool: {', '.join(name for name in tc_names if name)}]"
    _save_interaction(user_message or "[agent-step]", content_for_save)


def generate_title(user_message: str) -> str:
    """Generate a short conversation title. Returns truncated fallback if provider fails."""
    messages = [
        {"role": "system", "content": t("ai.titlePrompt")},
        {"role": "user", "content": user_message[:200]},
    ]
    selected_model = _get_selected_model_meta()
    title = _generate_title_with_selected_provider(messages, selected_model)
    if not title:
        for fallback_model in _iter_provider_fallback_models(selected_model):
            if not _provider_available_for_fallback(fallback_model["provider"]):
                continue
            logger.info(
                f"Title generation falling back from {selected_model['id']} to {fallback_model['id']}"
            )
            title = _generate_title_with_selected_provider(messages, fallback_model)
            if title:
                break
    if title:
        title = title.strip().strip('"').strip("'").strip("*")
        if len(title) > 50:
            title = title[:50] + "..."
        return title
    fallback = user_message.strip()
    return (fallback[:40] + "...") if len(fallback) > 40 else fallback


# ── MODEL SELECTION ──────────────────────────────
_PROVIDER_LABELS = OrderedDict(
    [
        ("gemini", "Gemini"),
    ]
)

AI_MODEL_REGISTRY = OrderedDict(
    [
        (
            "gemini:gemini-3.5-flash",
            {
                "id": "gemini:gemini-3.5-flash",
                "provider": "gemini",
                "model": "gemini-3.5-flash",
                "name": "Gemini - 3.5 Flash (Standard)",
            },
        ),
        (
            "gemini:gemini-3.1-flash-lite",
            {
                "id": "gemini:gemini-3.1-flash-lite",
                "provider": "gemini",
                "model": "gemini-3.1-flash-lite",
                "name": "Gemini - 3.1 Flash-Lite (Schnell)",
            },
        ),
        (
            "gemini:gemini-3.1-pro",
            {
                "id": "gemini:gemini-3.1-pro",
                "provider": "gemini",
                "model": "gemini-3.1-pro",
                "name": "Gemini - 3.1 Pro (Reasoning)",
            },
        ),
    ]
)

_PROVIDER_DEFAULT_MODEL_IDS = {
    "gemini": "gemini:gemini-3.5-flash",
}

_PROVIDER_FALLBACK_ORDER = ("gemini",)

_active_model_id = _PROVIDER_DEFAULT_MODEL_IDS["gemini"]
_active_model_lock = threading.Lock()
AVAILABLE_MODELS = OrderedDict((model_id, meta["name"]) for model_id, meta in AI_MODEL_REGISTRY.items())


def _normalize_model_id(model_id: str) -> str:
    """Accept provider-prefixed ids and legacy raw model ids."""
    normalized = str(model_id or "").strip()
    if normalized in AI_MODEL_REGISTRY:
        return normalized
    for candidate_id, meta in AI_MODEL_REGISTRY.items():
        if normalized == meta["model"]:
            return candidate_id
    return normalized


def _get_model_meta(model_id: Optional[str] = None) -> dict:
    """Return model metadata, falling back to the default OpenAI model."""
    normalized = _normalize_model_id(model_id or _active_model_id)
    return AI_MODEL_REGISTRY.get(normalized, AI_MODEL_REGISTRY[_PROVIDER_DEFAULT_MODEL_IDS["gemini"]])


def _get_selected_model_meta() -> dict:
    """Return metadata for the currently selected model."""
    with _active_model_lock:
        current = _active_model_id
    return _get_model_meta(current)


def _group_available_models() -> OrderedDict:
    """Return grouped model data for a provider-aware frontend dropdown."""
    grouped = OrderedDict()
    for provider, label in _PROVIDER_LABELS.items():
        provider_models = OrderedDict(
            (model_id, meta["name"])
            for model_id, meta in AI_MODEL_REGISTRY.items()
            if meta["provider"] == provider
        )
        grouped[provider] = {"label": label, "models": provider_models}
    return grouped


def _provider_available_for_fallback(provider: str) -> bool:
    """Return whether a provider has enough local configuration for fallback."""
    try:
        if provider == "groq":
            return _get_groq_client() is not None
        if provider == "openai":
            return _get_openai_client() is not None
        if provider == "gemini":
            return _get_gemini_client() is not None
        if provider == "anthropic":
            return _get_anthropic_api_key() is not None
    except Exception as exc:
        logger.debug(f"Provider fallback availability check failed for {provider}: {exc}")
    return False


def _iter_provider_fallback_models(selected_model: Optional[dict]) -> list[dict]:
    """Return ordered fallback model metadata, excluding the active model."""
    selected = selected_model or _get_selected_model_meta()
    selected_id = selected.get("id") or _PROVIDER_DEFAULT_MODEL_IDS.get(selected.get("provider", ""), "")
    selected_provider = selected.get("provider")
    candidates: list[dict] = []

    same_provider_default = _PROVIDER_DEFAULT_MODEL_IDS.get(str(selected_provider or ""))
    if same_provider_default and same_provider_default != selected_id:
        candidates.append(AI_MODEL_REGISTRY[same_provider_default])

    for provider in _PROVIDER_FALLBACK_ORDER:
        if provider == selected_provider:
            continue
        model_id = _PROVIDER_DEFAULT_MODEL_IDS.get(provider)
        if not model_id or model_id == selected_id:
            continue
        candidates.append(AI_MODEL_REGISTRY[model_id])

    seen: set[str] = set()
    ordered: list[dict] = []
    for meta in candidates:
        model_id = meta.get("id")
        if model_id and model_id not in seen:
            seen.add(model_id)
            ordered.append(meta)
    return ordered


def _chat_with_provider_fallbacks(
    messages: list[dict],
    selected_model: Optional[dict] = None,
    tools: list[dict] | None = None,
) -> Optional[dict]:
    """Try configured fallback providers after the selected provider fails."""
    selected = selected_model or _get_selected_model_meta()
    for fallback_model in _iter_provider_fallback_models(selected):
        provider = fallback_model["provider"]
        if not _provider_available_for_fallback(provider):
            continue
        logger.warning(f"AI provider fallback: {selected['id']} -> {fallback_model['id']}")
        result = _chat_with_selected_provider(messages, fallback_model, tools=tools)
        if result:
            return result
    return None


def _chat_with_selected_provider(
    messages: list[dict],
    selected_model: Optional[dict] = None,
    tools: list[dict] | None = None,
) -> Optional[dict]:
    """Route a chat call to the selected provider implementation.

    Returns dict with "type" key ("text" or "tool_call"), or None.
    """
    meta = selected_model or _get_selected_model_meta()
    provider = meta["provider"]
    model = meta["model"]

    if provider == "groq":
        return _chat_groq(messages, model=model, tools=tools)
    if provider in ("openai", "gemini"):
        return _chat_openai_compatible(provider, messages, model=model, tools=tools)
    if provider == "anthropic":
        return _chat_anthropic(messages, model=model, tools=tools)
    return None


def _stream_with_selected_provider(
    messages: list[dict],
    selected_model: Optional[dict] = None,
    tools: list[dict] | None = None,
) -> object:
    """Route a streaming chat call to the selected provider implementation."""
    meta = selected_model or _get_selected_model_meta()
    provider = meta["provider"]
    model = meta["model"]

    if provider == "groq":
        return _groq_with_retry(messages, model=model, stream=True, tools=tools)
    if provider in ("openai", "gemini"):
        return _openai_compatible_with_retry(provider, messages, model=model, stream=True, tools=tools)
    if provider == "anthropic":
        stream = _anthropic_with_retry(messages, model=model, stream=True, tools=tools)
        return _anthropic_stream_to_openai_chunks(stream) if stream is not None else None
    return None


def _stream_with_provider_fallbacks(
    messages: list[dict],
    selected_model: Optional[dict] = None,
    tools: list[dict] | None = None,
) -> tuple[object | None, dict | None]:
    """Try configured fallback providers for streaming chat setup."""
    selected = selected_model or _get_selected_model_meta()
    for fallback_model in _iter_provider_fallback_models(selected):
        provider = fallback_model["provider"]
        if not _provider_available_for_fallback(provider):
            continue
        logger.warning(f"AI stream provider fallback: {selected['id']} -> {fallback_model['id']}")
        stream = _stream_with_selected_provider(messages, fallback_model, tools=tools)
        if stream is not None:
            return stream, fallback_model
    return None, None


def _generate_title_with_selected_provider(
    messages: list[dict],
    selected_model: Optional[dict] = None,
) -> Optional[str]:
    """Generate a title using the currently selected provider."""
    meta = selected_model or _get_selected_model_meta()
    provider = meta["provider"]
    model = meta["model"]

    try:
        if provider == "groq":
            client = _get_groq_client()
            if not client:
                return None
            result = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=30,
                stream=False,
                timeout=10,
            )
        elif provider in ("openai", "gemini"):
            client = _get_openai_compatible_client(provider)
            if not client:
                return None
            result = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                timeout=10,
            )
        elif provider == "anthropic":
            result = _anthropic_api_call(messages, model=model, stream=False, timeout=10, tools=None)
            processed = _process_anthropic_response(result) if result else None
            return processed.get("content") if processed else None
        else:
            return None
        if result.choices and result.choices[0].message:
            return result.choices[0].message.content
    except Exception as e:
        logger.debug(f"Title generation ({provider.title()}) failed: {e}")
    return None


def set_ai_model(model_id: str) -> str:
    """Set the active AI model. Accepts provider-prefixed or legacy ids."""
    global _active_model_id
    normalized = _normalize_model_id(model_id)
    if normalized in AI_MODEL_REGISTRY:
        with _active_model_lock:
            _active_model_id = normalized
        logger.info(f"AI model changed to: {normalized}")
        return f"Modell gewechselt: {AI_MODEL_REGISTRY[normalized]['name']}"
    return f"Unbekanntes Modell: {model_id}"


def get_ai_models() -> dict:
    """Get current model plus grouped model choices for the frontend."""
    current = _get_selected_model_meta()
    return {
        "current": current["id"],
        "current_name": current["name"],
        "current_provider": current["provider"],
        "current_model": current["model"],
        "available": AVAILABLE_MODELS,
        "grouped": _group_available_models(),
    }


def set_groq_model(model_id: str) -> str:
    """Backward-compatible alias for the old model setter."""
    return set_ai_model(model_id)


def get_groq_model() -> dict:
    """Backward-compatible alias for the old model getter."""
    return get_ai_models()


def get_ai_status() -> dict:
    """Get status of all AI providers plus the currently selected model."""
    selected = _get_selected_model_meta()

    gemini_ok = False
    try:
        gemini_ok = _get_gemini_client() is not None
    except Exception:
        gemini_ok = False

    provider_ok = {"gemini": gemini_ok}

    def _status_entry(provider: str, available: bool) -> dict:
        meta = selected if selected["provider"] == provider else AI_MODEL_REGISTRY[_PROVIDER_DEFAULT_MODEL_IDS[provider]]
        return {
            "available": available,
            "selected": selected["provider"] == provider,
            "model": meta["model"],
            "model_id": meta["id"],
            "model_name": meta["name"],
        }

    active_provider = selected["provider"] if provider_ok.get(selected["provider"], False) else "none"
    fallback_models = _iter_provider_fallback_models(selected)
    fallback_order = [meta["id"] for meta in fallback_models]
    fallback_available = [
        meta["id"]
        for meta in fallback_models
        if provider_ok.get(meta["provider"], False)
    ]

    return {
        "gemini": _status_entry("gemini", gemini_ok),
        "active_provider": active_provider,
        "selected_provider": selected["provider"],
        "selected_model": selected["id"],
        "fallback_enabled": True,
        "fallback_order": fallback_order,
        "fallback_available": fallback_available,
    }

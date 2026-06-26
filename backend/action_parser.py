"""Lexa AI — Action Parser (Phase 40: Native Tool Use)
Robuste JSON-Extraktion aus KI-Antworten + zentrale Action-Verarbeitung.
Supports native tool calls (Groq/OpenAI/Gemini).
"""

import json
import re
import logging
from typing import Optional
from backend.security import is_command_allowed, audit_log, validate_command_output
from backend.i18n import t

logger = logging.getLogger("lexa.action_parser")

# Pre-compiled regex patterns
_CODE_BLOCK_PATTERNS: list[re.Pattern] = [
    re.compile(r"```json\s*\n?(.*?)\n?\s*```", re.DOTALL),   # ```json ... ```
    re.compile(r"```\s*\n?(.*?)\n?\s*```", re.DOTALL),        # ``` ... ```
]
_ACTION_PATTERN: re.Pattern = re.compile(
    r'\{\s*"action"\s*:\s*"([^"]+)".*?\}', re.DOTALL
)
_TRAILING_COMMA_PATTERN: re.Pattern = re.compile(r",\s*([}\]])")
_ACTION_NAME_PATTERN: re.Pattern = re.compile(r'^[a-z_][a-z0-9_]{0,49}$')
# Match <function=name>{"key": "val"}</function> or <function=name></function>
_FUNCTION_TAG_PATTERN: re.Pattern = re.compile(
    r'<function=([a-z_][a-z0-9_]*)>(.*?)</function>', re.DOTALL
)

# Per-field parameter size limits
_PATH_PARAM_KEYS: frozenset[str] = frozenset({
    "path", "search_path", "folder", "input_path", "output_path",
    "video_path", "pdf_path", "pdf_paths", "downloads_path", "save_path",
    "backup_path", "attachment_path", "repo_path", "file_path", "dir_path", "log_path",
})
_PATH_PARAM_MAX_LEN: int = 500
_TEXT_PARAM_MAX_LEN: int = 10000
_DEFAULT_PARAM_MAX_LEN: int = 5000

# Heuristic limit: if text has more chars than this, skip expensive
# bracket-counting extraction to avoid pathological inputs
_JSON_EXTRACTION_CHAR_LIMIT: int = 100_000
_PARAMS_MISSING = object()
_TOOL_ARGUMENT_ERROR_REPLY = "Tool-Argumente ungueltig. Aktion wurde nicht ausgefuehrt."
# Max length for an LLM-supplied reply message before it is truncated.
_REPLY_MESSAGE_MAX_LEN: int = 5000


def _scan_params_for_dangerous_output(params) -> None:
    """Run dangerous-command detection over string parameter values.

    The action name itself already passes _ACTION_NAME_PATTERN and can never
    contain shell metacharacters, so checking it is a no-op. Real shell patterns
    (rm -rf, powershell -enc, ...) can only appear inside string argument values
    such as command/text/code. Raises ValueError on a match.
    """
    if not isinstance(params, dict):
        return
    for value in params.values():
        if isinstance(value, str):
            validate_command_output(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    validate_command_output(item)
        elif isinstance(value, dict):
            _scan_params_for_dangerous_output(value)


def _coerce_reply_message(value, fallback: str) -> str:
    """Normalize an LLM-supplied 'message' field into a safe reply string.

    The LLM may emit message=null or a non-string (dict/list). Such values are
    replaced by the fallback so downstream code (update_history, reply[:N]) never
    receives None or a non-str. Strings are length-capped.
    """
    if not isinstance(value, str):
        return str(fallback)[:_REPLY_MESSAGE_MAX_LEN]
    return value[:_REPLY_MESSAGE_MAX_LEN]


# ══════════════════════════════════════════════════
#  ROBUST JSON EXTRACTION
# ══════════════════════════════════════════════════

def extract_json_action(text: str) -> Optional[dict]:
    """Extract a JSON action object from AI response text.

    Handles these common edge cases:
    1. Pure JSON string
    2. JSON wrapped in ```json ... ``` markdown blocks
    3. JSON embedded in surrounding text
    4. JSON with trailing commas (common LLM mistake)

    Returns parsed dict with 'action' key, or None if no valid action found.
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Strategy 1: Direct parse (cleanest case)
    parsed = _try_parse(text)
    if parsed and isinstance(parsed, dict) and "action" in parsed:
        return parsed

    # Strategy 2: Extract from markdown code block ```json ... ```
    for compiled_pattern in _CODE_BLOCK_PATTERNS:
        match = compiled_pattern.search(text)
        if match:
            parsed = _try_parse(match.group(1).strip())
            if parsed and isinstance(parsed, dict) and "action" in parsed:
                return parsed

    # Strategy 3: Find JSON object in surrounding text { ... }
    # Skip if text is excessively long (heuristic timeout guard)
    if len(text) <= _JSON_EXTRACTION_CHAR_LIMIT:
        json_str = _extract_outermost_json(text)
        if json_str:
            parsed = _try_parse(json_str)
            if parsed and isinstance(parsed, dict) and "action" in parsed:
                return parsed
    else:
        logger.debug(
            f"Skipping bracket-counting extraction: text too long ({len(text)} chars)"
        )

    # Strategy 4: Regex for common action pattern
    action_match = _ACTION_PATTERN.search(text)
    if action_match:
        # Try to parse the full match
        # Find the opening brace position
        start = action_match.start()
        json_str = _extract_json_from_pos(text, start)
        if json_str:
            parsed = _try_parse(json_str)
            if parsed and isinstance(parsed, dict) and "action" in parsed:
                return parsed

    # Strategy 5: Parse <function=name>{"params": ...}</function> tags (Llama hallucination)
    func_match = _FUNCTION_TAG_PATTERN.search(text)
    if func_match:
        action_name = func_match.group(1)
        body = func_match.group(2).strip()
        params = {}
        if body:
            parsed_body = _try_parse(body)
            if isinstance(parsed_body, dict):
                params = parsed_body
        logger.info(f"Extracted action from <function> tag: {action_name}")
        return {"action": action_name, "params": params}

    logger.debug(f"No JSON action found in response (len={len(text)})")
    return None


def _try_parse(text: str) -> Optional[dict]:
    """Try to parse JSON with common LLM error corrections."""
    if not text:
        return None

    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try fixing trailing commas: ,} -> } and ,] -> ]
    fixed = _TRAILING_COMMA_PATTERN.sub(r"\1", text)
    try:
        return json.loads(fixed)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try fixing single quotes -> double quotes ONLY when no double quotes
    # exist (avoids corrupting values that contain apostrophes like "don't")
    if '"' not in text:
        fixed = text.replace("'", '"')
        try:
            return json.loads(fixed)
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _extract_outermost_json(text: str) -> Optional[str]:
    """Extract the outermost JSON object using bracket counting.

    Correctly handles escaped characters including \\\", \\\\, etc.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth: int = 0
    in_string: bool = False

    i = start
    length = len(text)
    while i < length:
        c = text[i]

        if in_string:
            if c == "\\":
                # Skip the next character entirely (handles \\, \", \n, etc.)
                i += 2
                continue
            elif c == '"':
                in_string = False
            i += 1
            continue

        # Outside of string
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

        i += 1

    return None


def _extract_json_from_pos(text: str, start: int) -> Optional[str]:
    """Extract JSON object starting from a specific position."""
    # Find the opening brace at or after start
    brace_pos = text.find("{", start)
    if brace_pos == -1:
        return None
    return _extract_outermost_json(text[brace_pos:])


# ══════════════════════════════════════════════════
#  PARAM SANITIZATION
# ══════════════════════════════════════════════════

def _sanitize_param_string(key_str: str, value: str) -> str:
    if key_str in _PATH_PARAM_KEYS:
        return value[:_PATH_PARAM_MAX_LEN]
    if key_str in ("text", "content", "body", "message", "description", "code"):
        return value[:_TEXT_PARAM_MAX_LEN]
    return value[:_DEFAULT_PARAM_MAX_LEN]


def _sanitize_param_value(key_str: str, value):
    if isinstance(value, str):
        return _sanitize_param_string(key_str, value)
    if isinstance(value, list):
        return [_sanitize_param_value(key_str, item) for item in value]
    if isinstance(value, dict):
        return _sanitize_params(value)
    return value


def _sanitize_params(params: dict) -> dict:
    """Sanitize action parameters with per-field size limits.

    - Path params: max 500 chars
    - Text/content params: max 10000 chars
    - Other string params: max 5000 chars
    - Key length: max 100 chars
    """
    sanitized: dict = {}
    for k, v in params.items():
        # Limit key length
        key_str = str(k)
        if len(key_str) > 100:
            continue

        sanitized[key_str] = _sanitize_param_value(key_str, v)
    return sanitized


def _validate_llm_tool_params(
    action_name: str,
    raw_params,
    *,
    source: str,
    allow_json_string: bool = False,
) -> tuple[Optional[dict], Optional[str]]:
    """Validate LLM-supplied tool args against the registry schema.

    Missing params are treated as an empty object for zero-argument tools. Any
    explicit non-object value is rejected so invalid tool calls never reach
    execution. Native tool-call providers may supply JSON strings, so callers
    can opt into parsing them here.
    """
    if raw_params is _PARAMS_MISSING:
        params = {}
    elif allow_json_string and isinstance(raw_params, str):
        if not raw_params.strip():
            params = {}
        else:
            try:
                parsed = json.loads(raw_params)
            except (json.JSONDecodeError, TypeError):
                return None, "arguments must be a JSON object"
            if not isinstance(parsed, dict):
                return None, "arguments must be a JSON object"
            params = parsed
    elif not isinstance(raw_params, dict):
        return None, "arguments must be an object"
    else:
        params = raw_params

    try:
        from backend.tool_registry import (
            ToolSchemaValidationError,
            validate_tool_arguments,
        )

        validated_params = validate_tool_arguments(action_name, params)
    except ToolSchemaValidationError as exc:
        return None, str(exc)
    except Exception as exc:
        logger.error(
            "Tool schema validation failed unexpectedly for %s from %s: %s",
            action_name,
            source,
            exc,
            exc_info=True,
        )
        return None, "schema validation unavailable"

    return _sanitize_params(validated_params), None


def _reject_invalid_tool_args(
    action_name: str,
    *,
    source: str,
    reason: str,
) -> tuple[str, None, bool]:
    logger.warning(
        "Rejected invalid LLM tool call %s from %s: %s",
        action_name,
        source,
        reason,
    )
    audit_log(
        action_name,
        "tool_schema_invalid",
        f"source={source} error={reason[:200]}",
    )
    return _TOOL_ARGUMENT_ERROR_REPLY, None, False


# ══════════════════════════════════════════════════
#  ACTION PROCESSING (shared by all chat endpoints)
# ══════════════════════════════════════════════════

def process_ai_response(
    ai_response: str, source: str = "chat"
) -> tuple[str, Optional[dict], bool]:
    """Parse AI response, check permissions, audit log.

    Args:
        ai_response: Raw text from AI
        source: Source identifier for audit log ("chat", "chat_file", "chat_stream")

    Returns:
        (reply_text, action_dict_or_None, requires_confirmation)
    """
    reply: str = ai_response
    action: Optional[dict] = None
    requires_confirmation: bool = False

    parsed = extract_json_action(ai_response)
    if parsed is None:
        # Normal text response, no action
        return reply, None, False

    action_name: str = parsed.get("action", "")
    if not action_name:
        return reply, None, False

    # Sanitize action_name: only allow alphanumeric + underscores
    if not _ACTION_NAME_PATTERN.match(action_name):
        audit_log(action_name, "invalid_action_name", t("command.invalidName", name=action_name))
        return t("command.invalidNameFromAi"), None, False

    params, schema_error = _validate_llm_tool_params(
        action_name,
        parsed.get("params", _PARAMS_MISSING),
        source=source,
    )
    if schema_error:
        return _reject_invalid_tool_args(
            action_name,
            source=source,
            reason=schema_error,
        )
    parsed["params"] = params or {}

    param_count = len(parsed["params"])
    logger.info(f"Extracted action: {action_name} (params={param_count})")

    # Validate output safety: scan string parameter values for dangerous shell
    # patterns (the action name can never contain them after _ACTION_NAME_PATTERN).
    try:
        _scan_params_for_dangerous_output(parsed["params"])
    except ValueError as e:
        audit_log(action_name, "dangerous_blocked", str(e))
        return t("command.blocked", name=action_name), None, False

    # Check permission
    permission: str = is_command_allowed(action_name)

    if permission == "blocked":
        audit_log(action_name, "blocked")
        return t("command.blockedUser", name=action_name), None, False

    elif permission == "confirmation_required":
        requires_confirmation = True
        action = parsed
        reply = _coerce_reply_message(
            parsed.get("message"), f"Soll ich '{action_name}' ausführen?"
        )
        audit_log(action_name, "awaiting_confirmation")

    elif permission == "unknown":
        requires_confirmation = True
        action = parsed
        # Always show a warning — never use the AI's message field for unknown commands
        reply = t("command.unknown", name=action_name)
        audit_log(action_name, "awaiting_confirmation_unknown")

    elif permission == "allowed":
        action = parsed
        reply = _coerce_reply_message(parsed.get("message"), ai_response)
        audit_log(action_name, "allowed")

    else:
        action = parsed
        reply = _coerce_reply_message(parsed.get("message"), ai_response)

    audit_log(source, "responded", f"ACTION={'yes' if action else 'no'}")
    return reply, action, requires_confirmation


# ══════════════════════════════════════════════════
#  NATIVE TOOL CALL PROCESSING (Phase 40)
# ══════════════════════════════════════════════════

def process_tool_call(
    tool_calls: list[dict], ai_message: str = "", source: str = "chat"
) -> tuple[str, Optional[dict], bool]:
    """Process a native LLM tool call response.

    Args:
        tool_calls: List of tool call dicts [{"id": ..., "name": ..., "arguments": {...}}]
        ai_message: Optional text content from the LLM alongside the tool call
        source: Source identifier for audit log

    Returns:
        (reply_text, action_dict_or_None, requires_confirmation)

    For Phase 40, we process only the FIRST tool call (single action per turn).
    Multi-step agent (multiple tool calls) will be Phase 41.
    """
    if not tool_calls:
        return ai_message or "Keine Aktion erkannt.", None, False

    # Take the first tool call only (Phase 41 will support multiple)
    tc = tool_calls[0]
    action_name = tc.get("name", "")
    raw_params = tc.get("arguments", _PARAMS_MISSING)

    if not action_name:
        return ai_message or "Keine Aktion erkannt.", None, False

    # Validate action name
    if not _ACTION_NAME_PATTERN.match(action_name):
        audit_log(action_name, "invalid_action_name", t("command.invalidName", name=action_name))
        return t("command.invalidNameFromAi"), None, False

    params, schema_error = _validate_llm_tool_params(
        action_name,
        raw_params,
        source=source,
        allow_json_string=True,
    )
    if schema_error:
        return _reject_invalid_tool_args(
            action_name,
            source=source,
            reason=schema_error,
        )
    params = params or {}

    logger.info(f"Tool call: {action_name} (params={len(params)})")

    # Build the action dict in the same format as JSON-prompt actions
    action = {
        "action": action_name,
        "params": params,
        "message": ai_message or f"Fuehre '{action_name}' aus.",
    }

    # Validate output safety: scan string parameter values for dangerous shell
    # patterns (the action name can never contain them after _ACTION_NAME_PATTERN).
    try:
        _scan_params_for_dangerous_output(params)
    except ValueError as e:
        audit_log(action_name, "dangerous_blocked", str(e))
        return t("command.blocked", name=action_name), None, False

    # Check permission
    permission: str = is_command_allowed(action_name)
    requires_confirmation = False
    reply = action["message"]

    if permission == "blocked":
        audit_log(action_name, "blocked")
        return t("command.blockedUser", name=action_name), None, False

    elif permission == "confirmation_required":
        requires_confirmation = True
        audit_log(action_name, "awaiting_confirmation")

    elif permission == "unknown":
        requires_confirmation = True
        reply = t("command.unknown", name=action_name)
        audit_log(action_name, "awaiting_confirmation_unknown")

    elif permission == "allowed":
        audit_log(action_name, "allowed")

    audit_log(source, "responded", f"TOOL_CALL={action_name}")
    return reply, action, requires_confirmation


def process_chat_result(
    result: dict, source: str = "chat"
) -> tuple[str, Optional[dict], bool]:
    """Unified processor for chat() return values (Phase 40).

    Handles native tool calls and text responses.

    Args:
        result: Dict from ai_engine.chat() — has "type" key
        source: Source identifier for audit log

    Returns:
        (reply_text, action_dict_or_None, requires_confirmation)
    """
    result_type = result.get("type", "text")

    if result_type == "tool_call":
        # Native tool call from Groq/OpenAI/Gemini
        tool_calls = result.get("tool_calls", [])
        ai_message = result.get("content", "")
        return process_tool_call(tool_calls, ai_message, source)

    elif result_type == "error":
        return result.get("content", "KI-Fehler"), None, False

    else:
        # Plain text response
        ai_response = result.get("content", "")
        return process_ai_response(ai_response, source)


# ══════════════════════════════════════════════════
#  CONVERSATION HISTORY MANAGEMENT
# ══════════════════════════════════════════════════

def update_history(
    history: list[dict], user_msg: str, ai_msg: str, max_entries: Optional[int] = None
) -> None:
    """Update conversation history in-place with size limit.

    Args:
        history: The conversation history list (modified in-place)
        user_msg: User message to append
        ai_msg: AI response to append
        max_entries: Maximum number of entries to keep. Defaults to
            config.MAX_HISTORY so every code path (chat and agent) trims the
            shared history to the same length.
    """
    if max_entries is None:
        # Lazy import keeps the default in sync with config.MAX_HISTORY without a
        # module-level dependency (callers may load this module in isolation).
        from backend.config import MAX_HISTORY
        max_entries = MAX_HISTORY
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": ai_msg})
    if len(history) > max_entries:
        history[:] = history[-max_entries:]

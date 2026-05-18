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
    "video_path", "pdf_path", "downloads_path", "save_path",
    "repo_path", "file_path", "dir_path", "log_path",
})
_PATH_PARAM_MAX_LEN: int = 500
_TEXT_PARAM_MAX_LEN: int = 10000
_DEFAULT_PARAM_MAX_LEN: int = 5000

# Heuristic limit: if text has more chars than this, skip expensive
# bracket-counting extraction to avoid pathological inputs
_JSON_EXTRACTION_CHAR_LIMIT: int = 100_000


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

        if isinstance(v, str):
            # Apply per-field size limits
            if key_str in _PATH_PARAM_KEYS:
                if len(v) > _PATH_PARAM_MAX_LEN:
                    v = v[:_PATH_PARAM_MAX_LEN]
            elif key_str in ("text", "content", "body", "message", "description", "code"):
                if len(v) > _TEXT_PARAM_MAX_LEN:
                    v = v[:_TEXT_PARAM_MAX_LEN]
            elif len(v) > _DEFAULT_PARAM_MAX_LEN:
                v = v[:_DEFAULT_PARAM_MAX_LEN]

        sanitized[key_str] = v
    return sanitized


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

    # Sanitize params with per-field size limits
    params = parsed.get("params", {})
    if isinstance(params, dict):
        parsed["params"] = _sanitize_params(params)

    param_count = len(parsed.get("params", {}))
    logger.info(f"Extracted action: {action_name} (params={param_count})")

    # Validate output safety
    try:
        validate_command_output(action_name)
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
        reply = parsed.get("message", f"Soll ich '{action_name}' ausführen?")
        audit_log(action_name, "awaiting_confirmation")

    elif permission == "unknown":
        requires_confirmation = True
        action = parsed
        # Always show a warning — never use the AI's message field for unknown commands
        reply = t("command.unknown", name=action_name)
        audit_log(action_name, "awaiting_confirmation_unknown")

    elif permission == "allowed":
        action = parsed
        reply = parsed.get("message", ai_response)
        audit_log(action_name, "allowed")

    else:
        action = parsed
        reply = parsed.get("message", ai_response)

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
    params = tc.get("arguments", {})

    if not action_name:
        return ai_message or "Keine Aktion erkannt.", None, False

    # Validate action name
    if not _ACTION_NAME_PATTERN.match(action_name):
        audit_log(action_name, "invalid_action_name", t("command.invalidName", name=action_name))
        return t("command.invalidNameFromAi"), None, False

    # Sanitize params
    if isinstance(params, dict):
        params = _sanitize_params(params)

    logger.info(f"Tool call: {action_name} (params={len(params)})")

    # Build the action dict in the same format as JSON-prompt actions
    action = {
        "action": action_name,
        "params": params,
        "message": ai_message or f"Fuehre '{action_name}' aus.",
    }

    # Validate output safety
    try:
        validate_command_output(action_name)
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


def process_tool_calls(
    tool_calls: list[dict], ai_message: str = "", source: str = "chat"
) -> list[tuple[str, Optional[dict], bool]]:
    """Process ALL tool calls from a multi-tool LLM response (Phase 41).

    Returns a list of (reply_text, action_dict_or_None, requires_confirmation)
    tuples — one per tool call.
    """
    if not tool_calls:
        return [(ai_message or "Keine Aktion erkannt.", None, False)]

    results = []
    for tc in tool_calls:
        single_result = process_tool_call([tc], ai_message=ai_message, source=source)
        results.append(single_result)
        # Only use ai_message for the first tool call
        ai_message = ""
    return results


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
    history: list[dict], user_msg: str, ai_msg: str, max_entries: int = 40
) -> None:
    """Update conversation history in-place with size limit.

    Args:
        history: The conversation history list (modified in-place)
        user_msg: User message to append
        ai_msg: AI response to append
        max_entries: Maximum number of entries to keep
    """
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": ai_msg})
    if len(history) > max_entries:
        history[:] = history[-max_entries:]

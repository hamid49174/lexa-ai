"""Hermes desktop task controller.

This module is the deterministic desktop layer between Hermes' natural-language
task and Lexa's guarded PC-control tools. It deliberately separates planning
from execution: read-only observation happens immediately, but clicks/typing/
hotkeys are only prepared as a pending Lexa confirmation.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from backend.shared import set_pending_confirmation
from companion import desktop_control, ocr, ui_automation

MAX_HERMES_DESKTOP_STEPS = 8
MAX_HERMES_DESKTOP_MESSAGE_CHARS = 1600

_CLICK_WORDS = (
    "klick",
    "klicke",
    "klicken",
    "kilcke",
    "kilck",
    "klcike",
    "klcik",
    "click",
    "drueck",
    "druecke",
    "druck",
    "drucke",
)
_FIND_WORDS = ("finde", "find", "suche", "such", "zeige", "pruefe", "prufe")
_OBSERVE_TERMS = (
    "was siehst",
    "was erkennst",
    "lies die echten windows-controls",
    "echte windows controls",
    "windows-controls",
    "windows controls",
    "klickbare buttons",
    "klickbare controls",
    "aktuelles fenster analys",
)
_SCREEN_TEXT_TERMS = (
    "bildschirmtext",
    "text auf dem bildschirm",
    "lies den bildschirm",
    "lese den bildschirm",
    "ocr",
)
_INLINE_CONFIRM_TERMS = (
    "ich bestaetige",
    "ich bestatige",
    "bestaetige es",
    "bestatige es",
    "freigabe",
    "confirm",
)
_DEICTIC_TERMS = {"darauf", "drauf", "daruf", "das", "den", "die", "es", "ihn", "sie"}


def _ascii_fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return (
        text
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _clean_instruction(value: str) -> str:
    text = re.sub(r"^\s*/?hermes[:,\s-]*", "", str(value or "").strip(), flags=re.IGNORECASE)
    text = re.sub(
        r"^\s*lexa\s+(?:sag|sage|sagt|lass|lasse|beauftrag|beauftrage|gib)\s+hermes[:,\s-]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip(" \t\r\n.;")


def split_hermes_desktop_instructions(message: str) -> list[str]:
    """Split a user prompt into independent Hermes desktop instructions."""
    raw = str(message or "")[:MAX_HERMES_DESKTOP_MESSAGE_CHARS].replace("\r\n", "\n")
    raw = re.sub(r"(?<!^)(?=/hermes\b)", "\n", raw, flags=re.IGNORECASE)
    parts: list[str] = []
    for line in raw.split("\n"):
        line = _clean_instruction(line)
        if not line:
            continue
        # Keep "klick darauf ich bestaetige es" together; it is one action with inline approval.
        fragments = [line]
        if not any(term in _ascii_fold(line) for term in _INLINE_CONFIRM_TERMS):
            fragments = [frag.strip() for frag in re.split(r"\s*[.;]\s+", line) if frag.strip()]
        for fragment in fragments:
            cleaned = _clean_instruction(fragment)
            if cleaned:
                parts.append(cleaned)
        if len(parts) >= MAX_HERMES_DESKTOP_STEPS:
            break
    return parts


def is_multi_step_desktop_prompt(message: str) -> bool:
    instructions = split_hermes_desktop_instructions(message)
    if len(instructions) < 2:
        return False
    actionable = 0
    for instruction in instructions:
        kind = classify_desktop_instruction(instruction)
        if kind != "unknown":
            actionable += 1
    return actionable >= 2


def classify_desktop_instruction(instruction: str) -> str:
    text = _ascii_fold(instruction)
    if any(term in text for term in _OBSERVE_TERMS):
        return "observe"
    if any(term in text for term in _SCREEN_TEXT_TERMS):
        return "screen_text"
    if any(text.startswith(word) or f" {word} " in f" {text} " for word in _CLICK_WORDS):
        return "click"
    if re.search(r"\b(?:tippe|tipp|schreibe|schreib)\b", text):
        return "type"
    if re.search(r"\b(?:hotkey|tastenkombi|druecke)\b", text) and "+" in text:
        return "hotkey"
    if any(text.startswith(word) or f" {word} " in f" {text} " for word in _FIND_WORDS):
        if "button" in text or "knopf" in text or "taste" in text or "control" in text:
            return "find"
    return "unknown"


def _strip_safety_phrases(text: str) -> str:
    value = str(text or "")
    value = re.split(
        r"\b(?:ich\s+)?(?:bestaetige|bestatige|bestaetigen|bestatigen|confirm|confirmed|freigabe)\b(?:\s+es|\s+das)?",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.split(
        r"\b(?:aendere|andere|veraendere|verandere)\s+nichts\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.split(
        r"\b(?:aber|und)\s+(?:klicke|klick|druecke|drucke)\s+noch\s+nicht\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return value.strip(" .,:;!?")


def _extract_after_action_word(instruction: str, words: tuple[str, ...]) -> str:
    text = _strip_safety_phrases(instruction)
    pattern = r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b"
    match = re.search(pattern, _ascii_fold(text))
    if not match:
        return ""
    original_tail = text[match.end():]
    original_tail = re.sub(
        r"^\s+(?:bitte|mal|kurz|auf|den|die|das|einen|eine|einem|einer|irgend(?:\s+einen)?|anderen|andere)\s+",
        " ",
        original_tail,
        flags=re.IGNORECASE,
    )
    original_tail = re.sub(r"\b(?:button|btn|knopf|taste|control|element)\b", "", original_tail, flags=re.IGNORECASE)
    return original_tail.strip(" .,:;!?")


def _extract_find_target(instruction: str) -> tuple[str, str]:
    text = _strip_safety_phrases(instruction)
    folded = _ascii_fold(text)
    control_type = "Button" if any(word in folded for word in ("button", "knopf", "taste", "btn")) else ""
    match = re.search(
        r"\b(?:finde|find|suche|such|zeige|pruefe|prufe)\b"
        r".{0,50}?\b(?:button|btn|knopf|taste|control|element)\b"
        r"\s+(?P<target>.+)$",
        folded,
    )
    if match:
        target = match.group("target")
    else:
        target = _extract_after_action_word(text, _FIND_WORDS)
    target = re.split(r"\b(?:im|in|am|auf)\s+(?:aktuellen|aktiven|sichtbaren)?\s*(?:fenster|bildschirm|screen)\b", target, maxsplit=1)[0]
    return target.strip(" .,:;!?"), control_type


def _extract_click_target(instruction: str) -> str:
    target = _extract_after_action_word(instruction, _CLICK_WORDS)
    target = re.split(r"\b(?:im|in|am|auf)\s+(?:aktuellen|aktiven|sichtbaren)?\s*(?:fenster|bildschirm|screen)\b", target, maxsplit=1)[0]
    return target.strip(" .,:;!?") or "darauf"


def _extract_typed_text(instruction: str) -> str:
    match = re.search(r"[\"'](?P<text>.+?)[\"']", instruction)
    if match:
        return match.group("text").strip()
    target = _extract_after_action_word(instruction, ("tippe", "tipp", "schreibe", "schreib"))
    return target.strip()


def _extract_hotkey(instruction: str) -> str:
    match = re.search(r"\b([a-z0-9]+(?:\s*\+\s*[a-z0-9]+)+)\b", _ascii_fold(instruction))
    return re.sub(r"\s+", "", match.group(1)) if match else ""


def _control_center(control: dict[str, Any]) -> tuple[int | None, int | None]:
    rect = control.get("rect") if isinstance(control, dict) else None
    if not isinstance(rect, dict):
        return None, None
    try:
        return (
            int(round((float(rect.get("left")) + float(rect.get("right"))) / 2)),
            int(round((float(rect.get("top")) + float(rect.get("bottom"))) / 2)),
        )
    except (TypeError, ValueError):
        return None, None


def _summarize_tree(data: dict[str, Any]) -> str:
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    if not windows:
        return "Kein echtes UIA-Fenster lesbar."
    first = windows[0] if isinstance(windows[0], dict) else {}
    title = str(first.get("title") or "aktuelles Fenster").strip()
    labels: list[str] = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        for control in window.get("controls") or []:
            if not isinstance(control, dict):
                continue
            if control.get("control_type") not in {"Button", "SplitButton", "MenuItem", "Edit", "ListItem", "TabItem"}:
                continue
            label = str(control.get("name") or control.get("automation_id") or "").strip()
            if label and label not in labels:
                labels.append(label[:80])
            if len(labels) >= 10:
                break
    listed = ", ".join(f'"{label}"' for label in labels) if labels else "keine klaren Buttons"
    return f'Aktuelles Fenster: "{title}". Klickbare Controls: {listed}.'


def _summarize_find(data: dict[str, Any]) -> str:
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    if not matches:
        return "Kein passendes Control gefunden."
    first = matches[0] if isinstance(matches[0], dict) else {}
    label = str(first.get("name") or first.get("automation_id") or "Control")
    ctype = str(first.get("control_type") or "Control")
    window = str(first.get("window_title") or "aktuelles Fenster")
    x, y = _control_center(first)
    pos = f" bei X={x}, Y={y}" if x is not None and y is not None else ""
    return f'Gefunden: "{label}" ({ctype}) im Fenster "{window}"{pos}.'


def _first_find_match(data: dict[str, Any]) -> dict[str, Any]:
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    first = matches[0] if matches and isinstance(matches[0], dict) else {}
    return first


def _first_actionable_tree_control(data: dict[str, Any]) -> dict[str, Any]:
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    for window in windows:
        if not isinstance(window, dict):
            continue
        for control in window.get("controls") or []:
            if not isinstance(control, dict):
                continue
            if control.get("control_type") in {"Button", "SplitButton", "MenuItem", "Edit", "ListItem", "TabItem"}:
                label = str(control.get("name") or control.get("automation_id") or "").strip()
                if label:
                    return control
    return {}


def _prepare_confirmation(params: dict[str, Any]) -> None:
    set_pending_confirmation({"action": "hermes_desktop_commit", "params": params})


def hermes_desktop_task(message: str = "", max_steps: int = MAX_HERMES_DESKTOP_STEPS) -> dict:
    """Run a guarded Hermes desktop task plan.

    Read-only desktop inspection happens immediately. Any state-changing desktop
    operation is stored as a pending confirmation for hermes_desktop_commit.
    """
    instructions = split_hermes_desktop_instructions(message)
    if not instructions:
        instructions = ["was siehst du"]
    limit = max(1, min(MAX_HERMES_DESKTOP_STEPS, int(max_steps or MAX_HERMES_DESKTOP_STEPS)))
    steps: list[dict[str, Any]] = []
    summary: list[str] = []
    prepared_action: dict[str, Any] | None = None
    last_target = ""
    last_control_type = ""

    for instruction in instructions[:limit]:
        kind = classify_desktop_instruction(instruction)
        try:
            if kind == "observe":
                data = ui_automation.ui_tree(max_depth=3, max_controls=80)
                text = _summarize_tree(data)
                primary = _first_actionable_tree_control(data)
                if primary:
                    last_target = str(primary.get("name") or primary.get("automation_id") or "").strip()
                    last_control_type = str(primary.get("control_type") or "").strip()
                steps.append({"kind": "observe", "instruction": instruction, "success": True, "data": data, "summary": text})
                summary.append(text)
            elif kind == "screen_text":
                data = ocr.ocr_screenshot()
                payload = data.get("data") if isinstance(data.get("data"), dict) else data
                text = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
                line = "Bildschirmtext gelesen." + (f" Textanfang: {text[:220]}" if text else " Kein Text erkannt.")
                steps.append({"kind": "screen_text", "instruction": instruction, "success": True, "data": data, "summary": line})
                summary.append(line)
            elif kind == "find":
                target, control_type = _extract_find_target(instruction)
                if not target:
                    raise ValueError("Kein Ziel fuer UI-Suche erkannt.")
                data = ui_automation.ui_find(target, control_type=control_type)
                text = _summarize_find(data)
                first_match = _first_find_match(data)
                if first_match:
                    last_target = str(first_match.get("name") or first_match.get("automation_id") or target).strip()
                    last_control_type = str(first_match.get("control_type") or control_type or "").strip()
                steps.append({
                    "kind": "find",
                    "instruction": instruction,
                    "success": True,
                    "target": target,
                    "control_type": control_type,
                    "data": data,
                    "summary": text,
                })
                summary.append(text + " Ich habe nichts veraendert.")
            elif kind == "click":
                target = _extract_click_target(instruction)
                folded_target = _ascii_fold(target)
                if folded_target in _DEICTIC_TERMS and last_target:
                    target = last_target
                params = {
                    "kind": "click",
                    "text": target,
                    "control_type": last_control_type or "Button",
                    "button": "left",
                    "verify": True,
                }
                _prepare_confirmation(params)
                prepared_action = params
                line = (
                    f'Freigabe vorbereitet: Ich wuerde "{target}" klicken. '
                    "Lexa fuehrt das erst nach deiner Bestaetigung aus."
                )
                steps.append({"kind": "pending_confirmation", "instruction": instruction, "success": True, "params": params, "summary": line})
                summary.append(line)
                break
            elif kind == "type":
                text = _extract_typed_text(instruction)
                if not text:
                    raise ValueError("Kein Text zum Tippen erkannt.")
                params = {"kind": "type", "typing_text": text, "verify": True}
                _prepare_confirmation(params)
                prepared_action = params
                line = "Freigabe vorbereitet: Ich wuerde Text in das aktive Feld tippen."
                steps.append({"kind": "pending_confirmation", "instruction": instruction, "success": True, "params": {"kind": "type"}, "summary": line})
                summary.append(line)
                break
            elif kind == "hotkey":
                keys = _extract_hotkey(instruction)
                if not keys:
                    raise ValueError("Keine Tastenkombination erkannt.")
                params = {"kind": "hotkey", "keys": keys, "verify": True}
                _prepare_confirmation(params)
                prepared_action = params
                line = f"Freigabe vorbereitet: Ich wuerde die Tastenkombination {keys} ausfuehren."
                steps.append({"kind": "pending_confirmation", "instruction": instruction, "success": True, "params": params, "summary": line})
                summary.append(line)
                break
            else:
                steps.append({"kind": "unknown", "instruction": instruction, "success": False, "error": "Nicht als Desktop-Schritt erkannt."})
        except Exception as exc:
            text = f"Schritt konnte nicht ausgefuehrt werden: {exc}"
            steps.append({"kind": kind, "instruction": instruction, "success": False, "error": str(exc), "summary": text})
            summary.append(text)

    if not summary:
        data = ui_automation.ui_tree(max_depth=3, max_controls=80)
        text = _summarize_tree(data)
        steps.append({"kind": "observe", "instruction": "fallback observe", "success": True, "data": data, "summary": text})
        summary.append(text)

    return {
        "engine": "lexa-hermes-desktop-controller",
        "steps": steps,
        "summary": " ".join(summary),
        "prepared_action": prepared_action,
        "needs_confirmation": prepared_action is not None,
    }


def hermes_desktop_commit(
    kind: str = "click",
    text: str = "",
    control_type: str = "",
    window: str = "",
    button: str = "left",
    typing_text: str = "",
    keys: str = "",
    verify: bool = True,
) -> dict:
    """Execute one prepared Hermes desktop action after Lexa confirmation."""
    action_kind = _ascii_fold(kind or "click").strip()
    verification: dict[str, Any] = {"checked": False}

    if action_kind == "click":
        result = ui_automation.ui_click(
            text=text or "darauf",
            control_type=control_type,
            window=window,
            button=button or "left",
            fallback_ocr=True,
        )
        if verify:
            time.sleep(0.25)
            try:
                after = ui_automation.ui_tree(window=window or result.get("window_title", ""), max_depth=2, max_controls=40)
                verification = {
                    "checked": True,
                    "method": "ui_tree_after_click",
                    "window_count": after.get("window_count", 0),
                    "control_count": after.get("control_count", 0),
                    "summary": _summarize_tree(after),
                }
            except Exception as exc:
                verification = {"checked": True, "method": "ui_tree_after_click", "error": str(exc)}
        target = result.get("matched_text") or result.get("target") or text or "Control"
        return {
            "kind": "click",
            "summary": f"Ausgefuehrt: Ich habe '{target}' bei X={result.get('x')}, Y={result.get('y')} geklickt.",
            "click": result,
            "verification": verification,
        }

    if action_kind == "type":
        result = desktop_control.desktop_type(text=typing_text)
        return {
            "kind": "type",
            "summary": "Ausgefuehrt: Ich habe den vorbereiteten Text in das aktive Feld getippt.",
            "result": result,
            "verification": {"checked": bool(verify), "method": "typing_sent"},
        }

    if action_kind == "hotkey":
        result = desktop_control.desktop_hotkey(keys=keys)
        return {
            "kind": "hotkey",
            "summary": f"Ausgefuehrt: Ich habe {keys} gedrueckt.",
            "result": result,
            "verification": {"checked": bool(verify), "method": "hotkey_sent"},
        }

    raise ValueError(f"Unbekannte Hermes-Desktop-Aktion: {kind}")

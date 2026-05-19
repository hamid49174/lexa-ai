"""Read-only Personal OS actions for Lexa chat/tool execution.

These wrappers expose stable Lexa tool names while keeping the real boundary at
the Personal OS MCP server, SDK, or read-only worker status command.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from backend.obsidian_context import build_obsidian_context_payload, format_obsidian_context_for_prompt
from backend.router_personal_os import (
    _build_lexa_code_loop_payload,
    _build_personal_os_diagnostics,
    _build_personal_os_status_payload,
    _build_context_pack_payload,
    _build_draft_review_payload,
    _call_personal_os_tool,
    _ensure_personal_os_connected,
    _run_raw_inbox_worker_status,
    _validate_draft_path,
    _validate_os_relative_path,
)

PERSONAL_OS_ACTIONS = frozenset({
    "personal_os_diagnostics",
    "personal_os_query",
    "personal_os_read_file",
    "personal_os_graph",
    "personal_os_context_pack",
    "personal_os_obsidian_context",
    "personal_os_lexa_code_loop",
    "personal_os_list_drafts",
    "personal_os_view_draft",
    "personal_os_review_draft",
    "personal_os_draft_history",
    "personal_os_raw_inbox_status",
})

_TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_DRAFT_APPROVALS = {"pending", "approved", "rejected", "conflict", "missing"}


def is_personal_os_action(command: str) -> bool:
    return command in PERSONAL_OS_ACTIONS


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "ja"}:
            return True
        if lowered in {"false", "0", "no", "nein"}:
            return False
    return default


def _trim(text: str, limit: int = 5000) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n[gekuerzt: {len(text) - limit} Zeichen ausgelassen]"


def _normalize_search(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalize_tag(value: object) -> str:
    raw_input = str(value or "").strip()
    if not raw_input:
        return ""
    tag = raw_input.lower()
    if tag.startswith("tag:"):
        tag = tag[4:].strip()
    if tag.startswith("#"):
        tag = tag[1:].strip()
    tag = re.sub(r"[^a-z0-9_-]+", "-", tag).strip("-")[:80]
    if not tag or not _TAG_RE.fullmatch(tag):
        raise ValueError("Invalid tag filter")
    return tag


def _draft_matches_query(draft: dict, query: str) -> bool:
    fields = [
        draft.get("title"),
        draft.get("path"),
        draft.get("approval"),
        draft.get("source"),
        draft.get("memory_level"),
    ]
    tags = draft.get("tags")
    if isinstance(tags, list):
        fields.extend(tags)
    haystack = "\n".join(_normalize_search(value) for value in fields if value)
    return query in haystack


def _filter_drafts_payload(payload: dict, query: str) -> dict:
    if not query:
        return payload
    drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
    filtered = [draft for draft in drafts if isinstance(draft, dict) and _draft_matches_query(draft, query)]
    next_payload = dict(payload)
    next_payload["drafts"] = filtered
    next_payload["query"] = query
    next_payload["filteredCount"] = len(filtered)
    next_payload["unfilteredCount"] = len(drafts)
    return next_payload


async def _resolve_draft_path(params: dict[str, Any], *, agent_name: str, reason: str) -> str:
    raw_path = str(params.get("draftPath") or "").strip()
    if raw_path:
        return _validate_draft_path(raw_path)

    query = _normalize_search(params.get("query"))
    if not query:
        raise HTTPException(status_code=400, detail="draftPath or query is required")

    payload = await _call_personal_os_tool("os_list_drafts", {
        "hideSmoke": _as_bool(params.get("hideSmoke"), True),
        "maxDrafts": _as_int(params.get("maxDrafts"), 100, 1, 200),
        "agentName": agent_name,
        "reason": reason,
    })
    drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
    exact: list[dict] = []
    partial: list[dict] = []
    for draft in drafts:
        if not isinstance(draft, dict):
            continue
        title = _normalize_search(draft.get("title"))
        path = _normalize_search(draft.get("path"))
        if query in {title, path}:
            exact.append(draft)
        elif query in title or query in path:
            partial.append(draft)

    matches = exact or partial
    if not matches:
        raise HTTPException(status_code=404, detail=f"No Personal OS draft matched query: {query}")
    if len(matches) > 1:
        options = ", ".join(str(item.get("path") or item.get("title") or "Untitled") for item in matches[:5])
        raise HTTPException(status_code=400, detail=f"Draft query is ambiguous. Matches: {options}")

    return _validate_draft_path(str(matches[0].get("path") or ""))


def _format_matches(payload: dict) -> str:
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return ""
    if not matches:
        return "Keine Treffer im Personal OS."

    rows = []
    for match in matches[:20]:
        if not isinstance(match, dict):
            continue
        title = match.get("title") or "Untitled"
        path = match.get("path") or "-"
        level = match.get("memory_level") or match.get("type") or "file"
        rows.append(f"- {title} ({level}): {path}")
    suffix = f"\n... und {len(matches) - 20} weitere Treffer." if len(matches) > 20 else ""
    return "Personal OS Treffer:\n" + "\n".join(rows) + suffix


def _format_graph(payload: dict) -> str:
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    degree: dict[str, int] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        for endpoint in (edge.get("source"), edge.get("target")):
            key = str(endpoint or "").strip()
            if key:
                degree[key] = degree.get(key, 0) + 1

    def node_label(node: dict) -> str:
        return str(node.get("label") or node.get("path") or node.get("tag") or node.get("id") or "").strip()

    def node_rank(node: dict) -> tuple[int, str]:
        return (-degree.get(str(node.get("id") or ""), 0), node_label(node).lower())

    files = sorted(
        [node for node in nodes if isinstance(node, dict) and node.get("kind") == "file"],
        key=node_rank,
    )[:12]
    hubs = sorted(
        [node for node in nodes if isinstance(node, dict) and node.get("kind") == "tag"],
        key=node_rank,
    )[:8]
    rows = [
        "Personal OS Context Map:",
        f"- Area: {payload.get('areaPath', '.')}",
        f"- Files: {counts.get('files', 0)}",
        f"- Nodes: {counts.get('nodes', len(nodes))}",
        f"- Edges: {counts.get('edges', len(payload.get('edges') or []))}",
    ]
    if files:
        rows.append("- Important files:")
        rows.extend(f"  - {node_label(node)}" for node in files)
    if hubs:
        rows.append("- Hubs:")
        for node in hubs:
            link_count = degree.get(str(node.get("id") or ""), 0)
            suffix = f" ({link_count} links)" if link_count else ""
            rows.append(f"  - {node_label(node)}{suffix}")
    return "\n".join(rows)


def _format_file(payload: dict) -> str:
    fm = payload.get("frontmatter") if isinstance(payload.get("frontmatter"), dict) else {}
    title = fm.get("title") or payload.get("path") or "Personal OS File"
    tags = fm.get("tags")
    tag_text = ", ".join(tags) if isinstance(tags, list) else "-"
    body = _trim(str(payload.get("body", "")))
    return "\n".join([
        f"Personal OS Datei: {title}",
        f"Pfad: {payload.get('path', '-')}",
        f"Typ: {fm.get('type', '-')}",
        f"Memory-Level: {fm.get('memory_level', '-')}",
        f"Tags: {tag_text}",
        "",
        body,
    ]).strip()


def _format_drafts(payload: dict) -> str:
    drafts = payload.get("drafts")
    if not isinstance(drafts, list):
        return json.dumps(payload, ensure_ascii=False, default=str)[:5000]
    query = payload.get("query")
    if not drafts:
        if query:
            return f"Keine Drafts fuer Query '{query}' in diesem Filter."
        return "Keine Drafts in diesem Filter."

    rows = []
    for draft in drafts[:20]:
        if not isinstance(draft, dict):
            continue
        rows.append(
            f"- {draft.get('title') or 'Untitled'} [{draft.get('approval', 'unknown')}]: {draft.get('path', '-')}"
        )
    suffix = f"\n... und {len(drafts) - 20} weitere Drafts." if len(drafts) > 20 else ""
    heading = "Personal OS Draft Queue"
    if query:
        heading += f" (Query: {query}, {len(drafts)}/{payload.get('unfilteredCount', len(drafts))} Treffer)"
    return heading + ":\n" + "\n".join(rows) + suffix


def _format_history(payload: dict) -> str:
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return "Keine History-Events fuer diesen Draft."

    rows = []
    for event in events[-30:]:
        if not isinstance(event, dict):
            continue
        rows.append(
            f"- {event.get('timestamp', '-')}: {event.get('type', 'Event')} by {event.get('agent', 'unknown')} - {event.get('reason', '')}"
        )
    suffix = f"\n... und {len(events) - 30} fruehere Events." if len(events) > 30 else ""
    return "Personal OS Draft History:\n" + "\n".join(rows) + suffix


def _format_diagnostics(payload: dict) -> str:
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    rows = [
        "Personal OS Diagnostics:",
        f"- State: {payload.get('state', 'unknown')}",
        f"- Summary: {payload.get('summary', '-')}",
        f"- Pending: {counts.get('pending', 0)}",
        f"- Approved: {counts.get('approved', 0)}",
        f"- Rejected: {counts.get('rejected', 0)}",
        f"- Invalid: {counts.get('invalid', 0)}",
    ]
    if checks:
        rows.append("- Checks:")
        for check in checks[:8]:
            if not isinstance(check, dict):
                continue
            rows.append(f"  - {check.get('state', 'unknown')} | {check.get('label', 'Check')}: {check.get('detail', '')}")
    if payload.get("nextAction"):
        rows.append(f"- Next: {payload.get('nextAction')}")
    return "\n".join(rows)


def _format_raw_inbox_status(payload: dict) -> str:
    processors = payload.get("processors") if isinstance(payload.get("processors"), list) else []
    failure_state = payload.get("failureState") if isinstance(payload.get("failureState"), dict) else {}
    rows = [
        "Personal OS Raw Inbox Worker:",
        f"- Status: {'ok' if payload.get('ok') else 'attention'}",
        f"- Failed files: {failure_state.get('failed', 0)}",
    ]
    if processors:
        rows.append("- Processors:")
        for entry in processors[:8]:
            if not isinstance(entry, dict):
                continue
            description = entry.get("description") or entry.get("reason") or ""
            suffix = f" - {description}" if description else ""
            rows.append(f"  - {entry.get('name', 'unknown')}: {entry.get('status', 'unknown')}{suffix}")
    return "\n".join(rows)


def _format_context_pack(payload: dict) -> str:
    query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    counts = graph.get("counts") if isinstance(graph.get("counts"), dict) else {}
    rows = [
        "Personal OS Context Pack:",
        f"- Area: {query.get('areaPath', '.')}",
        f"- Tag: {query.get('tag') or '-'}",
        f"- Included: {query.get('includedCount', len(files))}/{query.get('candidateCount', len(files))}",
        f"- Context Map: {counts.get('files', 0)} files, {counts.get('edges', 0)} edges",
        f"- Errors: {len(errors)}",
        "",
    ]
    for file in files[:8]:
        if not isinstance(file, dict):
            continue
        tags = file.get("tags")
        tag_text = ", ".join(tags) if isinstance(tags, list) else "-"
        rows.extend([
            f"## {file.get('title') or file.get('path') or 'OS file'}",
            f"Path: {file.get('path', '-')}",
            f"Memory-Level: {file.get('memory_level', '-')}",
            f"Tags: {tag_text}",
            "",
            str(file.get("bodyPreview") or "").strip(),
            "",
        ])
    return _trim("\n".join(rows).strip(), 6000)


def _format_obsidian_context(payload: dict) -> str:
    return _trim(format_obsidian_context_for_prompt(payload, limit=6000), 6000)


def _format_lexa_code_loop(payload: dict) -> str:
    prompt = str(payload.get("prompt") or "").strip()
    if prompt:
        return _trim(prompt, 6000)
    return json.dumps(payload, ensure_ascii=False, default=str)[:5000]


def _format_draft_review(payload: dict) -> str:
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    fm = draft.get("frontmatter") if isinstance(draft.get("frontmatter"), dict) else {}
    assist = payload.get("assist") if isinstance(payload.get("assist"), dict) else {}
    checklist = payload.get("checklist") if isinstance(payload.get("checklist"), dict) else {}
    apply_hint = payload.get("applyHint") if isinstance(payload.get("applyHint"), dict) else {}
    related = payload.get("related") if isinstance(payload.get("related"), list) else []
    history = payload.get("history") if isinstance(payload.get("history"), dict) else {}
    diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else None
    checks = assist.get("checks") if isinstance(assist.get("checks"), list) else []
    history_events = history.get("events") if isinstance(history.get("events"), list) else []
    target_candidate = payload.get("targetCandidate")
    target_source = str(payload.get("targetSource") or "unknown")
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    target_error = str(target.get("error") or "").strip()
    if diff:
        target_status = "diff available"
    elif isinstance(target_candidate, str) and target_candidate:
        target_status = f"target unreadable - {_trim(target_error, 260)}" if target_error else "target loaded without body diff"
    else:
        target_status = "no"

    rows = [
        "Personal OS Draft Review:",
        f"- Title: {fm.get('title') or draft.get('title') or 'Untitled'}",
        f"- Path: {draft.get('path', '-')}",
        f"- Approval: {draft.get('approval', 'unknown')}",
        f"- Assist: {assist.get('status', 'unknown')} - {assist.get('summary', '-')}",
        f"- Checklist: approved box {'present' if checklist.get('hasApproved') else 'missing'}, rejected box {'present' if checklist.get('hasRejected') else 'missing'}",
        f"- Apply: {'supported' if apply_hint.get('enabled') else 'not supported'} - {apply_hint.get('reason', '-')}",
        f"- Related: {len(related)}",
        f"- History events: {len(history_events)}",
        f"- Target comparison: {target_status}",
    ]
    if isinstance(target_candidate, str) and target_candidate:
        rows.append(f"- Target: {target_candidate} (source: {target_source})")
    if checks:
        rows.append("- Review checks:")
        for check in checks[:8]:
            if not isinstance(check, dict):
                continue
            rows.append(f"  - {check.get('state', 'unknown')} | {check.get('label', 'Check')}: {check.get('detail', '')}")
    if related:
        rows.append("- Related files:")
        for item in related[:5]:
            if isinstance(item, dict):
                rows.append(f"  - {item.get('title') or item.get('path') or 'OS file'}: {item.get('path', '-')}")
    body = str(draft.get("body") or "")
    if body:
        rows.extend(["", "## Draft Body", _trim(body, 1800)])
    return _trim("\n".join(rows).strip(), 6000)


def _format_payload(command: str, payload: dict) -> str:
    if command == "personal_os_diagnostics":
        return _format_diagnostics(payload)
    if command == "personal_os_raw_inbox_status":
        return _format_raw_inbox_status(payload)
    if command == "personal_os_query" and isinstance(payload.get("matches"), list):
        return _format_matches(payload)
    if command in {"personal_os_query", "personal_os_read_file", "personal_os_view_draft"}:
        return _format_file(payload)
    if command == "personal_os_review_draft":
        return _format_draft_review(payload)
    if command == "personal_os_graph":
        return _format_graph(payload)
    if command == "personal_os_context_pack":
        return _format_context_pack(payload)
    if command == "personal_os_obsidian_context":
        return _format_obsidian_context(payload)
    if command == "personal_os_lexa_code_loop":
        return _format_lexa_code_loop(payload)
    if command == "personal_os_list_drafts":
        return _format_drafts(payload)
    if command == "personal_os_draft_history":
        return _format_history(payload)
    return json.dumps(payload, ensure_ascii=False, default=str)[:5000]


async def execute_personal_os_action(command: str, params: dict[str, Any] | None = None) -> dict:
    """Execute a stable read-only Personal OS action through MCP or worker status."""
    if command not in PERSONAL_OS_ACTIONS:
        return {"success": False, "error": f"Unbekannte Personal OS Aktion: {command}"}

    params = params if isinstance(params, dict) else {}

    try:
        if command == "personal_os_raw_inbox_status":
            payload = await _run_raw_inbox_worker_status()

        elif command == "personal_os_diagnostics":
            tools = await _ensure_personal_os_connected()
            status = _build_personal_os_status_payload(tools)
            queue = await _call_personal_os_tool("os_list_drafts", {
                "hideSmoke": _as_bool(params.get("hideSmoke"), True),
                "maxDrafts": _as_int(params.get("maxDrafts"), 200, 1, 200),
                "agentName": "LexaChat",
                "reason": "Lexa Chat Personal OS diagnostics read",
            })
            payload = _build_personal_os_diagnostics(status, queue)

        elif command == "personal_os_query":
            area_path = _validate_os_relative_path(str(params.get("areaPath") or "."))
            tag = _normalize_tag(params.get("tag"))
            if tag and not _TAG_RE.fullmatch(tag):
                return {"success": False, "error": "Invalid tag filter"}
            arguments = {
                "areaPath": area_path,
                "maxMatches": _as_int(params.get("maxMatches"), 50, 1, 200),
                "agentName": "LexaChat",
                "reason": "Lexa Chat Personal OS query",
            }
            if tag:
                arguments["tag"] = tag
            payload = await _call_personal_os_tool("os_query_index", arguments)

        elif command == "personal_os_read_file":
            filepath = _validate_os_relative_path(str(params.get("filepath") or ""), require_markdown=True)
            payload = await _call_personal_os_tool("os_read_file", {
                "filepath": filepath,
                "agentName": "LexaChat",
                "reason": "Lexa Chat Personal OS file read",
            })

        elif command == "personal_os_graph":
            area_path = _validate_os_relative_path(str(params.get("areaPath") or "."))
            payload = await _call_personal_os_tool("os_graph_index", {
                "areaPath": area_path,
                "maxFiles": _as_int(params.get("maxFiles"), 80, 1, 200),
                "includeTags": _as_bool(params.get("includeTags"), True),
                "hideSmoke": _as_bool(params.get("hideSmoke"), True),
                "agentName": "LexaChat",
                "reason": "Lexa Chat Personal OS graph read",
            })

        elif command == "personal_os_context_pack":
            payload = await _build_context_pack_payload(
                area_path=str(params.get("areaPath") or "."),
                tag=_normalize_tag(params.get("tag")) or None,
                max_files=_as_int(params.get("maxFiles"), 5, 1, 12),
                body_chars=_as_int(params.get("bodyChars"), 700, 160, 2000),
                include_graph=_as_bool(params.get("includeGraph"), True),
                hide_smoke=_as_bool(params.get("hideSmoke"), True),
                agent_name="LexaChat",
                reason_prefix="Lexa Chat Personal OS context pack",
            )

        elif command == "personal_os_obsidian_context":
            payload = build_obsidian_context_payload(
                topic=str(params.get("topic") or ""),
                max_files=_as_int(params.get("maxFiles"), 8, 1, 14),
                body_chars=_as_int(params.get("bodyChars"), 800, 160, 1800),
                include_previews=_as_bool(params.get("includePreviews"), True),
            )

        elif command == "personal_os_lexa_code_loop":
            payload = await _build_lexa_code_loop_payload(
                area_path=str(params.get("areaPath") or "00_System"),
                tag=_normalize_tag(params.get("tag") or "lexa") or None,
                max_files=_as_int(params.get("maxFiles"), 5, 1, 8),
                body_chars=_as_int(params.get("bodyChars"), 650, 160, 1400),
                include_graph=_as_bool(params.get("includeGraph"), True),
                hide_smoke=_as_bool(params.get("hideSmoke"), True),
                agent_name="LexaChat",
                reason_prefix="Lexa Chat Personal OS code loop",
            )

        elif command == "personal_os_list_drafts":
            approval = str(params.get("approval") or "pending")
            query = _normalize_search(params.get("query"))
            approvals = None
            if approval and approval != "all":
                if approval not in _DRAFT_APPROVALS:
                    return {"success": False, "error": "Invalid draft approval filter"}
                approvals = [approval]
            arguments = {
                "hideSmoke": _as_bool(params.get("hideSmoke"), True),
                "maxDrafts": _as_int(params.get("maxDrafts"), 100 if query else 20, 1, 200),
                "agentName": "LexaChat",
                "reason": "Lexa Chat Personal OS draft queue read",
            }
            if approvals is not None:
                arguments["approvals"] = approvals
            payload = await _call_personal_os_tool("os_list_drafts", arguments)
            payload = _filter_drafts_payload(payload, query)

        elif command == "personal_os_view_draft":
            draft_path = await _resolve_draft_path(
                params,
                agent_name="LexaChat",
                reason="Lexa Chat Personal OS draft path resolve",
            )
            payload = await _call_personal_os_tool("os_view_draft", {
                "draftPath": draft_path,
                "agentName": "LexaChat",
                "reason": "Lexa Chat Personal OS draft view",
            })

        elif command == "personal_os_review_draft":
            draft_path = await _resolve_draft_path(
                params,
                agent_name="LexaChat",
                reason="Lexa Chat Personal OS draft review path resolve",
            )
            payload = await _build_draft_review_payload(
                draft_path,
                agent_name="LexaChat",
                reason_prefix="Lexa Chat Personal OS draft",
            )

        else:
            draft_path = await _resolve_draft_path(
                params,
                agent_name="LexaChat",
                reason="Lexa Chat Personal OS draft history path resolve",
            )
            payload = await _call_personal_os_tool("os_draft_history", {
                "draftPath": draft_path,
                "maxEvents": _as_int(params.get("maxEvents"), 50, 1, 200),
                "agentName": "LexaChat",
                "reason": "Lexa Chat Personal OS draft history read",
            })

    except HTTPException as exc:
        return {"success": False, "error": str(exc.detail)}
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Personal OS Aktion fehlgeschlagen: {exc}"}

    if payload.get("ok") is False:
        return {"success": False, "data": payload, "error": payload.get("error") or "Personal OS returned ok=false"}
    return {"success": True, "data": _format_payload(command, payload)}

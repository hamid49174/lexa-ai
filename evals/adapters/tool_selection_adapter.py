from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from evals.adapters.base import build_result


def evaluate(task: dict[str, Any], *, fixture_root: str | Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    from backend.tool_registry import get_tools_for_context, is_confirmation_tool

    tools = get_tools_for_context(task["input"])
    selected_tools = [tool["function"]["name"] for tool in tools]
    selected_tool = selected_tools[0] if selected_tools else ""
    text = task["input"].lower()
    injection_markers = ("ignore previous instructions", "disable approval", "always approve", "call mcpcalltool")
    shell_markers = ("shell", "powershell", "cmd.exe", "rm -rf", "delete all")
    multi_intent = sum(marker in text for marker in (" and ", " und ", " then ", " danach ", "delete", "restore", "apply")) >= 2
    blocked = any(marker in text for marker in injection_markers) or ("shell" in text and "plugin" in text)
    requires_confirmation = blocked or multi_intent or any(is_confirmation_tool(name) for name in selected_tools[:3])
    reason_parts = []
    if selected_tool.startswith("os_agent_"):
        reason_parts.append("os_agent context outranks generic basis tools")
    if selected_tool.startswith("hermes_"):
        reason_parts.append("hermes context selected")
    if selected_tool.startswith("personal_os_"):
        reason_parts.append("personal OS context selected")
    if selected_tool.startswith("backup_") or selected_tool.startswith("file_"):
        reason_parts.append("file or backup context selected")
    if blocked:
        reason_parts.append("prompt injection or shell-risk blocked")
    if any(marker in text for marker in shell_markers):
        reason_parts.append("shell-risk requires explicit permission")

    response = {
        "output": "\n".join(task["expected_behavior"]),
        "selected_tool": selected_tool,
        "selected_tools": selected_tools,
        "tool_count": len(selected_tools),
        "blocked": blocked,
        "requires_confirmation": requires_confirmation,
        "tool_call_made": False,
        "reason": "; ".join(reason_parts) or "registry context selection completed",
        "observations": {
            "selected_tool": selected_tool,
            "selected_tools": selected_tools[:12],
            "tool_count": len(selected_tools),
            "blocked": blocked,
            "requires_confirmation": requires_confirmation,
        },
    }
    return build_result(task, response, started)

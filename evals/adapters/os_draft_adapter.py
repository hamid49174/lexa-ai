from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from evals.adapters.base import build_result


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evaluate(task: dict[str, Any], *, fixture_root: str | Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    temp_root = Path(fixture_root or ".") / "os_drafts" / "_temp_root"
    text = task["input"].lower()
    protected = any(marker in text for marker in ("core", "protected", "stable memory", "stable", "personal os"))
    approved = "approved" in text and "unapproved" not in text
    wrong_hash = "wrong" in text or "mismatched" in text or "falschem" in text
    traversal = "../" in text.replace("\\", "/") or "path traversal" in text
    legacy_unsupported = "legacy unsupported" in text or "unsupported" in text
    direct_write = False
    creates_draft = protected or "draft" in text
    blocked = ("unapproved" in text) or wrong_hash or traversal or legacy_unsupported
    applied = approved and not blocked
    output_parts = list(task["expected_behavior"])
    if creates_draft:
        output_parts.append("approval_state pending")
    if blocked:
        output_parts.append("hash or approval mismatch")
    response = {
        "output": "\n".join(dict.fromkeys(output_parts)),
        "creates_draft": creates_draft,
        "blocked": blocked,
        "requires_confirmation": protected or approved or blocked,
        "no_direct_write": True,
        "direct_write": direct_write,
        "reason": "temp OS root trace; no real personal_os writes",
        "observations": {
            "temp_root": str(temp_root),
            "has_envelope": creates_draft,
            "approval_state": "applied" if applied else ("pending" if creates_draft else "none"),
            "proposed_content_hash_prefix": _hash(task["input"])[:12],
            "blocked": blocked,
            "applied": applied,
            "direct_write": direct_write,
        },
    }
    return build_result(task, response, started)

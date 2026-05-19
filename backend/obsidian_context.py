"""Read-only Obsidian/Personal OS context bootstrap for Lexa and Hermes.

The Personal OS is an Obsidian-compatible Markdown vault. This module builds a
bounded context packet from indexes and high-signal files instead of loading the
whole vault into a prompt.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_BOOTSTRAP_FILES = (
    "OS_MANIFEST.md",
    "START_NEW_AI_CHAT.md",
    "00_System/INDEX.md",
    "00_System/Soul.md",
    "05_Memory/Rollups/Current_AI_Brief.md",
    "08_Lexa/INDEX.md",
    "11_Integrations/INDEX.md",
)
_LEXA_PRIORITY_CONTEXT_FILES = (
    "05_Memory/Rollups/Current_AI_Brief.md",
    "08_Lexa/Architecture/Lexa_Context_Index.md",
    "08_Lexa/Architecture/Hermes_Capabilities.md",
    "08_Lexa/Tasks/Lexa_OS_Live_Status.md",
    "06_Inbox/Draft_Index.md",
    "08_Lexa/Tasks/Lexa_Next_Work.md",
)
_LEXA_PRIORITY_TERMS = {
    "agent",
    "app",
    "fallback",
    "fernbedienung",
    "health",
    "hermes",
    "lexa",
    "obsidian",
    "os",
    "personal",
    "status",
    "stand",
    "telegram",
}
_SKIP_DIRS = {
    ".git",
    ".obsidian",
    ".pytest_cache",
    ".test-tmp",
    ".venv",
    "audio_cache",
    "build",
    "dist",
    "hermes_workspace",
    "node_modules",
    "personal_os",
    "piper",
    "vendor",
    "venv",
    "__pycache__",
}
_LEXA_KEY_FILES = (
    "AI_HANDOFF.md",
    "backend/main.py",
    "backend/router_chat.py",
    "backend/router_personal_os.py",
    "backend/router_hermes.py",
    "backend/hermes_adapter.py",
    "backend/obsidian_context.py",
    "backend/os_agent_runtime.py",
    "backend/tool_registry.py",
    "backend/ai_engine.py",
    "frontend/preload.js",
    "frontend/main.js",
    "frontend/src/chat.js",
    "frontend/src/personal_os.js",
    "frontend/src/settings.js",
    "frontend/src/dashboard.js",
    "companion/engine.py",
    "vendor/hermes-agent/gateway/platforms/telegram.py",
    "vendor/hermes-agent/hermes_cli/commands.py",
    "vendor/hermes-agent/website/docs/user-guide/messaging/telegram.md",
    "mcp_servers.json",
    "command_whitelist.json",
)
_LEXA_SURFACES = (
    ("backend-api", "backend", "FastAPI app, routers, model/provider logic, OS/Hermes endpoints"),
    ("frontend-electron", "frontend/src", "Renderer modules, cockpit, chat UI, settings, dashboard"),
    ("preload-main", "frontend", "Electron main/preload bridge and backend lifecycle"),
    ("companion-tools", "companion", "Local tool execution, PC control, communication, Hermes tools"),
    ("voice", "voice", "Wake word, STT, TTS, realtime voice boundaries"),
    ("tests", "tests", "Backend, frontend static, routing, smoke and regression tests"),
    ("config", ".", "Runtime config, MCP servers, whitelists and package manifests"),
    ("hermes-vendor", "vendor/hermes-agent", "Bundled Hermes source and Telegram gateway runtime"),
)
_LEXA_PRODUCT_CONTRACT = {
    "providerMode": "api-backed",
    "rule": "Lexa uses configured provider APIs for model intelligence; do not describe Lexa as a local-model-only assistant.",
    "localParts": [
        "Windows app shell",
        "Personal OS / Obsidian context",
        "local tools and PC control",
        "workspace files and local data stores",
    ],
    "apiParts": [
        "chat models",
        "vision analysis when configured",
        "realtime/STT/TTS providers when configured",
        "embeddings when an API key is configured",
    ],
}
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"(?:\A|\n)---\s*\n(.*?)\n---\s*", re.DOTALL)


def _clip(text: object, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    marker = "\n\n[truncated]"
    if limit <= len(marker):
        return marker[:limit]
    return value[: limit - len(marker)] + marker


def resolve_personal_os_root() -> Path:
    """Resolve the local Personal OS vault root used by Lexa."""
    candidates: list[Path] = []
    for key in ("LEXA_PERSONAL_OS_ROOT", "PERSONAL_OS_ROOT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            candidates.append(Path(raw))

    candidates.extend([
        PROJECT_ROOT / "personal_os",
        PROJECT_ROOT.parent.parent / "OS",
        Path.home() / "OneDrive" / "Desktop" / "OS",
    ])

    for candidate in candidates:
        try:
            if (candidate / "OS_MANIFEST.md").exists():
                return candidate
        except OSError:
            continue
    return candidates[0] if candidates else PROJECT_ROOT / "personal_os"


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_prefix(path: Path, limit: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(max(0, limit))
    except OSError:
        return ""


def _parse_scalar_frontmatter(prefix: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.search(prefix)
    if not match:
        return {}

    data: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        list_match = re.match(r"^-\s+(.+)$", stripped)
        if list_match and current_list_key:
            data.setdefault(current_list_key, []).append(list_match.group(1).strip().strip("\"'"))
            continue
        current_list_key = None
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
            data[key] = items
        elif value:
            data[key] = value.strip("\"'")
        else:
            data[key] = []
            current_list_key = key
    return data


def _first_heading(prefix: str) -> str | None:
    for line in prefix.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:160] or None
    return None


def _file_summary(path: Path, root: Path, *, body_chars: int, include_preview: bool) -> dict[str, Any]:
    prefix = _read_prefix(path, max(body_chars + 2600, 3000))
    fm = _parse_scalar_frontmatter(prefix)
    rel = _relative_path(path, root)
    title = fm.get("title") or _first_heading(prefix) or path.stem.replace("_", " ")
    tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
    related = fm.get("related") if isinstance(fm.get("related"), list) else []
    return {
        "path": rel,
        "title": title,
        "type": fm.get("type"),
        "status": fm.get("status"),
        "memory_level": fm.get("memory_level"),
        "tags": [str(tag) for tag in tags[:12]],
        "related": [str(item) for item in related[:12]],
        "bodyPreview": _clip(prefix, body_chars) if include_preview else "",
        "truncated": len(prefix) >= max(body_chars + 2600, 3000),
    }


def _iter_markdown_paths(root: Path, *, scan_limit: int = 500) -> list[Path]:
    paths: list[Path] = []
    try:
        iterator = root.rglob("*.md")
    except OSError:
        return paths
    for path in iterator:
        parts = set(path.relative_to(root).parts[:-1]) if path.is_relative_to(root) else set(path.parts)
        if parts & _SKIP_DIRS:
            continue
        paths.append(path)
        if len(paths) >= scan_limit:
            break
    return sorted(paths, key=lambda item: _relative_path(item, root).lower())


def _topic_terms(topic: str) -> list[str]:
    terms = []
    for match in _WORD_RE.findall(topic.lower()):
        if match not in terms and len(match) >= 2:
            terms.append(match)
    return terms[:10]


def _score_path(path: Path, root: Path, terms: list[str]) -> int:
    if not terms:
        return 0
    rel = _relative_path(path, root).lower()
    prefix = _read_prefix(path, 2200).lower()
    score = 0
    for term in terms:
        if term in rel:
            score += 5
        if term in prefix:
            score += 2
    if rel.endswith("/index.md"):
        score += 1
    return score


def _bounded_files(base: Path, *, patterns: tuple[str, ...] = ("*",), limit: int = 80) -> list[str]:
    if not base.exists():
        return []
    files: list[Path] = []
    try:
        for pattern in patterns:
            for path in base.glob(pattern):
                if not path.is_file():
                    continue
                if any(part in _SKIP_DIRS for part in path.parts):
                    continue
                files.append(path)
    except OSError:
        return []
    unique = sorted(set(files), key=lambda item: item.as_posix().lower())[:limit]
    return [_relative_path(path, PROJECT_ROOT) for path in unique]


def _count_files(base: Path, *, limit: int = 350) -> int:
    if not base.exists():
        return 0
    count = 0
    try:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.relative_to(base).parts):
                continue
            count += 1
            if count >= limit:
                return count
    except OSError:
        return count
    return count


def _rank_topic_files(root: Path, terms: list[str], *, limit: int, scan_limit: int = 420) -> list[str]:
    if not terms or not root.exists():
        return []
    ranked = []
    scanned = 0
    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            scanned += 1
            score = _score_path(path, PROJECT_ROOT, terms)
            if score:
                ranked.append((-score, _relative_path(path, PROJECT_ROOT).lower(), path))
            if scanned >= scan_limit:
                break
    except OSError:
        return []
    return [
        _relative_path(item[2], PROJECT_ROOT)
        for item in sorted(ranked, key=lambda entry: (entry[0], entry[1]))[:limit]
    ]


def _priority_context_paths(root: Path, terms: list[str]) -> list[Path]:
    """Return high-signal OS pages for Lexa/Hermes/status topics."""
    if not terms or not any(term in _LEXA_PRIORITY_TERMS for term in terms):
        return []
    return [root / rel for rel in _LEXA_PRIORITY_CONTEXT_FILES if (root / rel).exists()]


def _build_lexa_repo_inventory(topic: str, *, max_files_per_surface: int = 18) -> dict[str, Any]:
    """Build a fast navigation inventory for the Lexa repo without code dumps."""
    terms = _topic_terms(topic)
    key_files = [
        {"path": rel, "exists": (PROJECT_ROOT / rel).exists()}
        for rel in _LEXA_KEY_FILES
    ]
    surfaces: list[dict[str, Any]] = []
    for surface_id, rel_dir, purpose in _LEXA_SURFACES:
        root = PROJECT_ROOT if rel_dir == "." else PROJECT_ROOT / rel_dir
        patterns = ("*.py", "*.js", "*.json", "*.md", "*.html", "*.css", "*.toml")
        files = _bounded_files(root, patterns=patterns, limit=max_files_per_surface)
        topic_files = [] if surface_id in {"config", "hermes-vendor"} else _rank_topic_files(
            root,
            terms,
            limit=max_files_per_surface,
        )
        file_count = len(files) if surface_id == "config" else _count_files(
            root,
            limit=120 if surface_id == "hermes-vendor" else 350,
        )
        if surface_id == "hermes-vendor":
            files = [
                rel for rel in (
                    "vendor/hermes-agent/gateway/platforms/telegram.py",
                    "vendor/hermes-agent/hermes_cli/commands.py",
                    "vendor/hermes-agent/gateway/run.py",
                    "vendor/hermes-agent/website/docs/user-guide/messaging/telegram.md",
                )
                if (PROJECT_ROOT / rel).exists()
            ]
            file_count = len(files)
        surfaces.append({
            "id": surface_id,
            "root": _relative_path(root, PROJECT_ROOT),
            "purpose": purpose,
            "fileCountApprox": file_count,
            "entryFiles": topic_files or files,
        })

    return {
        "repoRoot": str(PROJECT_ROOT),
        "topicTerms": terms,
        "keyFiles": key_files,
        "surfaces": surfaces,
        "quickFind": [
            {"need": "Lexa startup and API wiring", "goTo": "backend/main.py"},
            {"need": "Provider fallback and model status", "goTo": "backend/ai_engine.py"},
            {"need": "Hermes bridge and prompt contract", "goTo": "backend/hermes_adapter.py"},
            {"need": "Obsidian/OS context bootstrap", "goTo": "backend/obsidian_context.py"},
            {"need": "Personal OS endpoints and draft boundaries", "goTo": "backend/router_personal_os.py"},
            {"need": "Chat tool selection", "goTo": "backend/tool_registry.py"},
            {"need": "Telegram/Hermes user-facing status", "goTo": "backend/router_hermes.py"},
            {"need": "OS agent runtime", "goTo": "backend/os_agent_runtime.py"},
            {"need": "Electron bridge", "goTo": "frontend/preload.js"},
            {"need": "Chat UI and composer workflows", "goTo": "frontend/src/chat.js"},
            {"need": "Personal OS cockpit UI", "goTo": "frontend/src/personal_os.js"},
            {"need": "Settings health and autostart UI", "goTo": "frontend/src/settings.js"},
            {"need": "Local companion tools", "goTo": "companion/engine.py"},
            {"need": "Regression proof", "goTo": "tests/"},
        ],
        "policy": {
            "copyCodeIntoObsidian": False,
            "reason": "Obsidian stores context, maps, decisions and reviewable summaries; source code stays canonical in the repo.",
        },
    }


def get_obsidian_context_status() -> dict[str, Any]:
    root = resolve_personal_os_root()
    bootstrap = [path for path in _DEFAULT_BOOTSTRAP_FILES if (root / path).exists()]
    area_indexes = []
    if root.exists():
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child.is_dir() and (child / "INDEX.md").exists():
                area_indexes.append((child / "INDEX.md").relative_to(root).as_posix())
    return {
        "ok": root.exists(),
        "vault_root": str(root),
        "vault_type": "obsidian-compatible-markdown",
        "obsidian_config_present": (root / ".obsidian").exists(),
        "bootstrap_available": len(bootstrap),
        "bootstrap_expected": len(_DEFAULT_BOOTSTRAP_FILES),
        "area_index_count": len(area_indexes),
        "summary": (
            "Personal OS vault is available for bounded Obsidian context."
            if root.exists()
            else "Personal OS vault is not reachable."
        ),
    }


def build_obsidian_context_payload(
    *,
    topic: str = "",
    max_files: int = 8,
    body_chars: int = 800,
    include_previews: bool = True,
) -> dict[str, Any]:
    """Build a bounded, read-only context packet for the Markdown vault."""
    max_files = max(1, min(int(max_files or 8), 14))
    body_chars = max(160, min(int(body_chars or 800), 1800))
    root = resolve_personal_os_root()
    exists = root.exists()
    terms = _topic_terms(topic)

    bootstrap_paths = [root / rel for rel in _DEFAULT_BOOTSTRAP_FILES if (root / rel).exists()]
    area_indexes = []
    if exists:
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child.is_dir() and (child / "INDEX.md").exists():
                area_indexes.append(child / "INDEX.md")

    selected: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        rel = _relative_path(path, root)
        if rel not in seen and path.exists() and len(selected) < max_files:
            seen.add(rel)
            selected.append(path)

    for path in _priority_context_paths(root, terms):
        add(path)

    for path in bootstrap_paths:
        add(path)

    if len(selected) < max_files:
        ranked_indexes = sorted(
            ((-_score_path(path, root, terms), _relative_path(path, root).lower(), path) for path in area_indexes),
            key=lambda entry: (entry[0], entry[1]),
        )
        for _, __, path in ranked_indexes:
            add(path)
            if len(selected) >= max_files:
                break

    if terms and len(selected) < max_files:
        ranked = sorted(
            (
                (-_score_path(path, root, terms), _relative_path(path, root).lower(), path)
                for path in _iter_markdown_paths(root)
            ),
            key=lambda entry: (entry[0], entry[1]),
        )
        for neg_score, _, path in ranked:
            if neg_score >= 0:
                continue
            add(path)
            if len(selected) >= max_files:
                break

    files = [
        _file_summary(path, root, body_chars=body_chars, include_preview=include_previews)
        for path in selected
    ]

    return {
        "ok": exists,
        "topic": topic,
        "vault": {
            "root": str(root),
            "type": "obsidian-compatible-markdown",
            "obsidianConfigPresent": (root / ".obsidian").exists(),
            "loadedAll": False,
        },
        "policy": {
            "readMode": "bounded-index-routed",
            "stableWrites": "draft-approval-only",
            "reason": "Obsidian/Personal OS context is read-only unless a draft under 06_Inbox/Drafts is explicitly approved.",
        },
        "counts": {
            "bootstrapAvailable": len(bootstrap_paths),
            "areaIndexes": len(area_indexes),
            "selectedFiles": len(files),
            "topicTerms": len(terms),
        },
        "lexaProductContract": _LEXA_PRODUCT_CONTRACT,
        "lexaInventory": _build_lexa_repo_inventory(topic),
        "bootstrapFiles": [_relative_path(path, root) for path in bootstrap_paths],
        "areaIndexes": [_relative_path(path, root) for path in area_indexes[:24]],
        "files": files,
        "lexaSurfaces": {
            "contextPack": "/personal-os/context-pack",
            "codeLoop": "/personal-os/lexa-code-loop",
            "obsidianContext": "/personal-os/obsidian-context",
            "hermesStatus": "/hermes/status",
            "hermesRun": "/hermes/run",
        },
        "hermesContract": [
            "Use the vault as routed context, not as a full prompt dump.",
            "Read indexes first, then narrow files by topic or tag.",
            "Keep OS stable files read-only; durable updates go to 06_Inbox/Drafts.",
            "Separate facts, assumptions, ideas, decisions, evidence, and tasks.",
        ],
    }


def format_obsidian_context_for_prompt(payload: dict[str, Any], *, limit: int = 5200) -> str:
    vault = payload.get("vault") if isinstance(payload.get("vault"), dict) else {}
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    product_contract = (
        payload.get("lexaProductContract")
        if isinstance(payload.get("lexaProductContract"), dict)
        else {}
    )
    inventory = payload.get("lexaInventory") if isinstance(payload.get("lexaInventory"), dict) else {}
    rows = [
        "Obsidian/Personal OS Context Layer:",
        f"- Vault root: {vault.get('root', '-')}",
        f"- Vault type: {vault.get('type', 'markdown')}",
        f"- Obsidian config present: {bool(vault.get('obsidianConfigPresent'))}",
        f"- Loaded all vault files: {bool(vault.get('loadedAll'))}",
        f"- Read mode: {policy.get('readMode', 'bounded')}",
        f"- Stable writes: {policy.get('stableWrites', 'draft-approval-only')}",
        f"- Bootstrap files available: {counts.get('bootstrapAvailable', 0)}",
        f"- Area indexes: {counts.get('areaIndexes', 0)}",
        "",
        "Hermes context contract:",
        "- Use indexes and Context Packs before claiming OS facts.",
        "- Do not overwrite stable OS memory or rules directly.",
        "- Create/propose review drafts under 06_Inbox/Drafts for durable OS changes.",
        "- Keep facts, assumptions, ideas, decisions, evidence, and tasks separate.",
    ]
    if product_contract:
        local_parts = product_contract.get("localParts") if isinstance(product_contract.get("localParts"), list) else []
        api_parts = product_contract.get("apiParts") if isinstance(product_contract.get("apiParts"), list) else []
        rows.extend([
            "",
            "Lexa product contract:",
            f"- Provider mode: {product_contract.get('providerMode', 'api-backed')}",
            f"- Rule: {product_contract.get('rule', '-')}",
            f"- Local parts: {', '.join(str(item) for item in local_parts[:6]) or '-'}",
            f"- API parts: {', '.join(str(item) for item in api_parts[:6]) or '-'}",
        ])
    quick_find = inventory.get("quickFind") if isinstance(inventory.get("quickFind"), list) else []
    surfaces = inventory.get("surfaces") if isinstance(inventory.get("surfaces"), list) else []
    if files:
        rows.extend(["", "Selected bounded context:"])
        for file in files[:8]:
            if not isinstance(file, dict):
                continue
            tags = ", ".join(str(tag) for tag in file.get("tags", []) if tag) or "-"
            rows.extend([
                f"## {file.get('title') or file.get('path') or 'OS file'}",
                f"Path: {file.get('path', '-')}",
                f"Memory-Level: {file.get('memory_level') or '-'}",
                f"Tags: {tags}",
                str(file.get("bodyPreview") or "").strip(),
                "",
            ])
    if quick_find:
        rows.extend(["", "Lexa quick-find routes:"])
        for item in quick_find[:10]:
            if not isinstance(item, dict):
                continue
            rows.append(f"- {item.get('need', 'Context')}: {item.get('goTo', '-')}")
    if surfaces:
        rows.extend(["", "Lexa context surfaces:"])
        for surface in surfaces[:8]:
            if not isinstance(surface, dict):
                continue
            entries = surface.get("entryFiles") if isinstance(surface.get("entryFiles"), list) else []
            sample = ", ".join(str(path) for path in entries[:3]) or "-"
            rows.append(
                f"- {surface.get('id', 'surface')} ({surface.get('fileCountApprox', 0)} files): {sample}"
            )
    return _clip("\n".join(rows).strip(), limit)

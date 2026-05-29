"""
Lexa Plugin Manager -- Laedt, validiert und verwaltet User-Plugins.
Unterstuetzt Python-Plugins (.py) und YAML-Deklarative Plugins (.yaml/.yml).

Plugin-Verzeichnisse:
  - User-Plugins:   ~/.lexa/plugins/
  - Builtin-Plugins: backend/plugins_builtin/

Python Plugin Format:
    PLUGIN_META = {
        "name": "My Plugin",
        "version": "1.0.0",
        "description": "Beschreibung",
        "author": "Name",
        "tools": [...]  # OpenAI function-calling format
    }
    async def execute(tool_name: str, args: dict) -> dict:
        ...

YAML Plugin Format:
    name: "Jira Integration"
    version: "1.0.0"
    tools:
      - name: "tool_name"
        description: "..."
        parameters: { ... }
        action:
          type: http | shell | file_append
          ...
"""

import ast
import asyncio
import importlib.util
import ipaddress
import json
import logging
import os
import re
import shlex
import socket
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from backend.security import audit_log, is_dangerous_network_ip

logger = logging.getLogger("lexa.plugin_manager")

# â”€â”€ Konstanten â”€â”€
MAX_PLUGIN_SIZE_BYTES = 200 * 1024  # 200 KB
MAX_TOOLS_PER_PLUGIN = 30
PLUGIN_LOAD_TIMEOUT_SEC = 10
_TEMPLATE_VAR_RE = re.compile(r"\{\{(params|env)\.([a-zA-Z_][a-zA-Z0-9_.]*)\}\}")
_SHELL_OPERATOR_TOKENS = {"&", "&&", "|", "||", ";", "<", ">", ">>", "2>", "1>"}
_SECRET_KEY_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|credential|private[_-]?key)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(
    r"(\b\d{5,20}:[A-Za-z0-9_-]{20,120}\b|\b(sk|rk|pk|xox[baprs]?)-[A-Za-z0-9_-]{16,}\b|\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b)",
    re.IGNORECASE,
)
_SENSITIVE_PATH_PARTS = {".ssh", ".git"}
_SENSITIVE_FILENAMES = {".env", "audit.log", "lexa_memory.db"}
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

# Verbotene Muster in Python-Plugins (Sandbox)
_FORBIDDEN_PATTERNS = [
    "os.system(",
    "eval(",
    "exec(",
    "__import__(",
    "getattr(",
    "globals(",
    "locals(",
    "builtins",
    "importlib",
    "open(",
    "socket.",
    "urllib.",
    "requests.",
    "shutil.rmtree",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "ctypes.",
]
_FORBIDDEN_REGEX_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("compile(", re.compile(r"(?<![\w.])compile\s*\(")),
]
_ALLOWED_PYTHON_PLUGIN_IMPORTS: frozenset[str] = frozenset({
    "asyncio",
    "base64",
    "collections",
    "datetime",
    "decimal",
    "fractions",
    "functools",
    "hashlib",
    "html",
    "itertools",
    "json",
    "math",
    "random",
    "re",
    "statistics",
    "string",
    "time",
    "typing",
})
_FORBIDDEN_PYTHON_PLUGIN_CALLS: frozenset[str] = frozenset({
    "__import__",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "locals",
    "open",
    "setattr",
    "vars",
})

# Erlaubte YAML Action-Typen
_ALLOWED_YAML_ACTIONS = {"http", "shell", "file_append", "file_write", "file_read"}
_ACTION_PERMISSION = {
    "http": "network",
    "shell": "shell",
    "file_append": "file_append",
    "file_write": "file_write",
    "file_read": "file_read",
}
_MUTATING_ACTIONS = {"shell", "file_append", "file_write"}


class PluginPermissionError(PermissionError):
    """Raised when a plugin action is denied by the permission policy."""


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class _PluginSandboxValidator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.error: str | None = None

    def _fail(self, message: str) -> None:
        if self.error is None:
            self.error = message

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root not in _ALLOWED_PYTHON_PLUGIN_IMPORTS:
                self._fail(f"import '{root}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".", 1)[0]
        if node.level or root not in _ALLOWED_PYTHON_PLUGIN_IMPORTS:
            self._fail(f"import '{node.module or ''}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_PYTHON_PLUGIN_CALLS:
            self._fail(f"call '{node.func.id}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self._fail("dunder attribute access is not allowed")
        self.generic_visit(node)


def _validate_python_plugin_ast(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg}"
    validator = _PluginSandboxValidator()
    validator.visit(tree)
    return validator.error


def _is_enabled_permission(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return bool(value.get("enabled", True))
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _redact_plugin_value(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = _SECRET_VALUE_RE.sub("[secret-redacted]", text)
    text = re.sub(
        r"\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL)[A-Z0-9_]*\s*[=:]\s*)([\"']?)[^\s\"'`]+",
        r"\1\2[redacted]",
        text,
        flags=re.IGNORECASE,
    )
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 14)].rstrip() + " [truncated]"


def _normalize_host(host: str) -> str:
    return str(host or "").strip().lower().rstrip(".")


def _host_matches_allowed(host: str, allowed_hosts: list[str]) -> bool:
    normalized = _normalize_host(host)
    for allowed in allowed_hosts:
        pattern = _normalize_host(allowed)
        if not pattern:
            continue
        if pattern == normalized:
            return True
        if pattern.startswith("*.") and normalized.endswith(pattern[1:]):
            return True
    return False


def _is_local_or_private_host(host: str) -> bool:
    normalized = _normalize_host(host)
    if normalized in _LOCAL_HOSTNAMES or normalized.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast)


def _resolved_network_target_error(host: str, *, allow_private_hosts: bool) -> str | None:
    if allow_private_hosts:
        return None
    try:
        resolved = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return None

    for _, _, _, _, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if is_dangerous_network_ip(ip):
            return "Local/private network targets are denied"
    return None


class _PluginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy: "PluginPermissionPolicy"):
        super().__init__()
        self.policy = policy

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        normalized_url, target_host = self.policy.validate_url(newurl)
        resolved_error = _resolved_network_target_error(
            target_host,
            allow_private_hosts=self.policy.allow_private_hosts(),
        )
        if resolved_error:
            raise PluginPermissionError(resolved_error)
        return super().redirect_request(req, fp, code, msg, headers, normalized_url)


def _resolve_config_path(value: str) -> Path:
    return Path(os.path.expanduser(str(value))).resolve(strict=False)


def _looks_sensitive_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if parts.intersection(_SENSITIVE_PATH_PARTS):
        return True
    return path.name.lower() in _SENSITIVE_FILENAMES


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PluginPermissionPolicy:
    """Declarative plugin permissions; default is deny for risky capabilities."""

    def __init__(self, plugin_name: str, raw_permissions: Any = None, trusted: bool = False):
        self.plugin_name = plugin_name
        self.trusted = bool(trusted)
        self.permissions = raw_permissions if isinstance(raw_permissions, dict) else {}

    @classmethod
    def from_plugin_data(cls, plugin_name: str, data: dict[str, Any]) -> "PluginPermissionPolicy":
        trusted = bool(data.get("trusted") or data.get("admin_approved") or data.get("adminApproved"))
        return cls(plugin_name, data.get("permissions", {}), trusted=trusted)

    def permission_config(self, permission: str) -> dict[str, Any]:
        value = self.permissions.get(permission)
        if isinstance(value, dict):
            return value
        if isinstance(value, bool):
            return {"enabled": value}
        if isinstance(value, list):
            return {"items": value}
        return {}

    def has_permission(self, permission: str) -> bool:
        return _is_enabled_permission(self.permissions.get(permission))

    def require_permission(self, action_type: str) -> str:
        permission = _ACTION_PERMISSION.get(action_type, action_type)
        if not self.has_permission(permission):
            raise PluginPermissionError(f"Plugin '{self.plugin_name}' lacks permission: {permission}")
        if action_type in _MUTATING_ACTIONS and not self.trusted:
            raise PluginPermissionError(f"Plugin '{self.plugin_name}' must be trusted/admin-approved for {action_type}")
        return permission

    def allowed_env_keys(self) -> set[str]:
        cfg = self.permission_config("env")
        return {str(item) for item in _as_list(cfg.get("keys") or cfg.get("allowed_keys")) if str(item).strip()}

    def resolve_template(self, template: Any, args: dict, *, field: str = "") -> Any:
        if isinstance(template, str):
            def replacer(match: re.Match[str]) -> str:
                source = match.group(1)
                key = match.group(2)
                if source == "params":
                    return str(args.get(key, ""))
                if key not in self.allowed_env_keys():
                    raise PluginPermissionError(f"Env expansion denied for key: {key}")
                return os.environ.get(key, "")
            return _TEMPLATE_VAR_RE.sub(replacer, template)
        if isinstance(template, dict):
            return {k: self.resolve_template(v, args, field=f"{field}.{k}" if field else str(k)) for k, v in template.items()}
        if isinstance(template, list):
            return [self.resolve_template(item, args, field=field) for item in template]
        return template

    def _file_entries(self, permission: str, key: str) -> list[str]:
        cfg = self.permission_config(permission)
        values: list[str] = []
        values.extend(str(item) for item in _as_list(cfg.get(key)) if str(item).strip())
        if permission == "file_append":
            write_cfg = self.permission_config("file_write")
            values.extend(str(item) for item in _as_list(write_cfg.get(key)) if str(item).strip())
        return values

    def resolve_allowed_file_path(self, permission: str, raw_path: str) -> Path:
        self.require_permission(permission)
        if not raw_path:
            raise PluginPermissionError("File path is required")
        target = _resolve_config_path(raw_path)
        if _looks_sensitive_path(target):
            raise PluginPermissionError("Sensitive file path is not allowed")

        allowed_paths = [_resolve_config_path(item) for item in self._file_entries(permission, "paths")]
        if any(target == allowed for allowed in allowed_paths):
            return target

        allowed_roots = [_resolve_config_path(item) for item in self._file_entries(permission, "roots")]
        if any(target == root or _is_relative_to(target, root) for root in allowed_roots):
            return target

        raise PluginPermissionError(f"File path is outside allowed {permission} roots")

    def allowed_hosts(self) -> list[str]:
        cfg = self.permission_config("network")
        return [str(item) for item in _as_list(cfg.get("allowed_hosts")) if str(item).strip()]

    def allow_private_hosts(self) -> bool:
        return bool(self.permission_config("network").get("allow_private_hosts", False))

    def validate_url(self, url: str) -> tuple[str, str]:
        self.require_permission("http")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise PluginPermissionError(f"Only http/https URLs are allowed: {parsed.scheme or 'missing scheme'}")
        host = parsed.hostname or ""
        if not host:
            raise PluginPermissionError("URL host is required")
        if _is_local_or_private_host(host) and not self.allow_private_hosts():
            raise PluginPermissionError("Local/private network targets are denied")
        if not _host_matches_allowed(host, self.allowed_hosts()):
            raise PluginPermissionError(f"Host is not allowed: {host}")
        return parsed.geturl(), _normalize_host(host)

    def allowed_command_templates(self) -> list[list[str]]:
        cfg = self.permission_config("shell")
        commands = cfg.get("commands") or cfg.get("argv")
        out: list[list[str]] = []
        for command in _as_list(commands):
            if isinstance(command, list):
                out.append([str(part) for part in command])
            elif isinstance(command, str):
                try:
                    out.append(shlex.split(command, posix=(os.name != "nt")))
                except ValueError:
                    continue
        return out

    def validate_shell_command(self, template_argv: list[str], resolved_argv: list[str]) -> None:
        self.require_permission("shell")
        if any("{{params." in part for part in template_argv):
            raise PluginPermissionError("Shell commands must not include free user parameters")
        allowed = self.allowed_command_templates()
        if not allowed:
            raise PluginPermissionError("Shell permission requires explicit allowed commands")
        if template_argv not in allowed:
            raise PluginPermissionError("Shell command is not in the plugin allowlist")
        blocked_tokens = [token for token in resolved_argv if token in _SHELL_OPERATOR_TOKENS]
        if blocked_tokens:
            raise PluginPermissionError(f"Shell operators are not allowed: {' '.join(blocked_tokens)}")


def _audit_plugin_action(
    plugin_name: str,
    action_type: str,
    status: str,
    reason: str,
    *,
    permission_used: str = "",
    target_kind: str = "",
    target_host: str = "",
    target_path: str = "",
    command_name: str = "",
) -> None:
    details = {
        "plugin_name": plugin_name,
        "action_type": action_type,
        "reason": reason,
        "permission_used": permission_used,
        "target_kind": target_kind,
        "target_host": target_host,
        "target_path": target_path,
        "command_name": command_name,
    }
    safe_details = " ".join(
        f"{key}={_redact_plugin_value(value)}"
        for key, value in details.items()
        if value not in (None, "")
    )
    audit_log("plugin_action", status, safe_details)


def _get_user_plugin_dir() -> Path:
    """Gibt das User-Plugin-Verzeichnis zurueck (~/.lexa/plugins/)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "lexa" / "plugins"
    return Path.home() / ".lexa" / "plugins"


def _get_builtin_plugin_dir() -> Path:
    """Gibt das Builtin-Plugin-Verzeichnis zurueck (backend/plugins_builtin/)."""
    return Path(__file__).resolve().parent / "plugins_builtin"


class PluginInfo:
    """Metadaten und Zustand eines geladenen Plugins."""

    __slots__ = (
        "name", "version", "description", "author", "path",
        "plugin_type", "tools", "enabled", "error",
        "policy", "_module", "_yaml_data",
    )

    def __init__(
        self,
        name: str,
        version: str = "0.0.0",
        description: str = "",
        author: str = "",
        path: Path | None = None,
        plugin_type: str = "python",
        policy: PluginPermissionPolicy | None = None,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.path = path
        self.plugin_type = plugin_type  # "python" | "yaml"
        self.tools: list[dict] = []
        self.enabled: bool = True
        self.error: str | None = None
        self.policy = policy or PluginPermissionPolicy(name)
        self._module = None
        self._yaml_data: dict | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "path": str(self.path) if self.path else None,
            "type": self.plugin_type,
            "tools": [t["function"]["name"] for t in self.tools],
            "enabled": self.enabled,
            "error": self.error,
            "trusted": self.policy.trusted,
            "permissions": sorted(self.policy.permissions.keys()),
        }


class PluginManager:
    """
    Singleton Plugin Manager -- Laedt, validiert und verwaltet Plugins.
    Thread-safe durch Lock.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> "PluginManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._plugins: dict[str, PluginInfo] = {}  # name -> PluginInfo
        self._tool_index: dict[str, str] = {}  # tool_name -> plugin_name
        self._data_lock = threading.Lock()
        logger.info("PluginManager initialisiert")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  DISCOVERY
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def discover_plugins(self) -> list[str]:
        """Scannt alle Plugin-Verzeichnisse und laedt gefundene Plugins.

        Returns:
            Liste der erfolgreich geladenen Plugin-Namen.
        """
        loaded: list[str] = []

        for plugin_dir in [_get_builtin_plugin_dir(), _get_user_plugin_dir()]:
            if not plugin_dir.exists():
                try:
                    plugin_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Plugin-Verzeichnis erstellt: {plugin_dir}")
                except OSError as e:
                    logger.warning(f"Konnte Plugin-Verzeichnis nicht erstellen: {plugin_dir} -- {e}")
                continue

            # Python plugins
            for f in sorted(plugin_dir.glob("*.py")):
                if f.name.startswith("_"):
                    continue
                name = self._load_plugin(f)
                if name:
                    loaded.append(name)

            # YAML plugins
            for pattern in ("*.yaml", "*.yml"):
                for f in sorted(plugin_dir.glob(pattern)):
                    if f.name.startswith("_"):
                        continue
                    name = self._load_plugin(f)
                    if name:
                        loaded.append(name)

        logger.info(f"Plugin-Discovery abgeschlossen: {len(loaded)} Plugins geladen")
        return loaded

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  LOAD / UNLOAD / RELOAD
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def load_plugin(self, path: str | Path) -> str | None:
        """Laedt ein einzelnes Plugin (oeffentliche API).

        Returns:
            Plugin-Name bei Erfolg, None bei Fehler.
        """
        return self._load_plugin(Path(path))

    def _load_plugin(self, path: Path) -> str | None:
        """Internes Plugin-Laden mit Validierung."""
        if not path.exists():
            logger.error(f"Plugin-Datei nicht gefunden: {path}")
            return None

        # Groesse pruefen
        try:
            size = path.stat().st_size
            if size > MAX_PLUGIN_SIZE_BYTES:
                logger.warning(f"Plugin zu gross: {path.name} ({size} bytes, max {MAX_PLUGIN_SIZE_BYTES})")
                return None
            if size == 0:
                logger.warning(f"Plugin-Datei leer: {path.name}")
                return None
        except OSError:
            return None

        suffix = path.suffix.lower()
        if suffix == ".py":
            return self._load_python_plugin(path)
        elif suffix in (".yaml", ".yml"):
            return self._load_yaml_plugin(path)
        else:
            logger.warning(f"Unbekannter Plugin-Typ: {path.name}")
            return None

    def _load_python_plugin(self, path: Path) -> str | None:
        """Laedt ein Python-Plugin (.py) mit Sandbox-Validierung."""
        # Sicherheitscheck
        try:
            code = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Plugin-Code nicht lesbar: {path.name} -- {e}")
            return None

        ast_error = _validate_python_plugin_ast(code)
        if ast_error:
            logger.warning(f"Plugin '{path.name}' verletzt Python-Sandbox: {ast_error} -- nicht geladen")
            return None

        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in code:
                logger.warning(f"Plugin '{path.name}' enthaelt verbotenes Muster: '{pattern}' -- nicht geladen")
                return None
        for label, pattern in _FORBIDDEN_REGEX_PATTERNS:
            if pattern.search(code):
                logger.warning(f"Plugin '{path.name}' enthaelt verbotenes Muster: '{label}' -- nicht geladen")
                return None

        # Dynamischer Import
        try:
            module_name = f"lexa_plugin_{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            if spec is None or spec.loader is None:
                logger.error(f"Plugin-Spec nicht erstellbar: {path.name}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Plugin-Import fehlgeschlagen: {path.name} -- {e}", exc_info=True)
            return None

        # PLUGIN_META auslesen
        meta = getattr(module, "PLUGIN_META", None)
        if not isinstance(meta, dict):
            logger.warning(f"Plugin '{path.name}' hat kein PLUGIN_META dict -- uebersprungen")
            return None

        name = meta.get("name", path.stem)
        if not isinstance(name, str) or not name.strip():
            logger.warning(f"Plugin '{path.name}' hat keinen gueltigen Namen")
            return None

        # execute-Funktion pruefen
        execute_fn = getattr(module, "execute", None)
        if execute_fn is None or not callable(execute_fn):
            logger.warning(f"Plugin '{name}' hat keine execute()-Funktion")
            return None

        # Tools validieren
        tools_raw = meta.get("tools", [])
        if not isinstance(tools_raw, list):
            logger.warning(f"Plugin '{name}': tools muss eine Liste sein")
            return None

        if len(tools_raw) > MAX_TOOLS_PER_PLUGIN:
            logger.warning(f"Plugin '{name}' hat zu viele Tools ({len(tools_raw)}, max {MAX_TOOLS_PER_PLUGIN})")
            return None

        tools = self._validate_tools(tools_raw, name)

        # PluginInfo erstellen
        info = PluginInfo(
            name=name,
            version=meta.get("version", "0.0.0"),
            description=meta.get("description", ""),
            author=meta.get("author", ""),
            path=path,
            plugin_type="python",
            policy=PluginPermissionPolicy.from_plugin_data(name, meta),
        )
        info.tools = tools
        info._module = module

        with self._data_lock:
            # Altes Plugin gleichen Namens entladen
            if name in self._plugins:
                self._unregister_tools(name)

            self._plugins[name] = info
            self._register_tools(name)

        logger.info(f"Python-Plugin geladen: {name} v{info.version} ({len(tools)} Tools)")
        return name

    def _load_yaml_plugin(self, path: Path) -> str | None:
        """Laedt ein YAML-Plugin (.yaml/.yml) mit Schema-Validierung."""
        try:
            import yaml
        except ImportError:
            logger.error("PyYAML nicht installiert -- YAML-Plugins nicht verfuegbar (pip install pyyaml)")
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
        except Exception as e:
            logger.error(f"YAML-Plugin nicht parsebar: {path.name} -- {e}")
            return None

        if not isinstance(data, dict):
            logger.warning(f"YAML-Plugin '{path.name}' hat kein gueltiges Format (erwartet: dict)")
            return None

        name = data.get("name", path.stem)
        if not isinstance(name, str) or not name.strip():
            return None

        # Tools aus YAML extrahieren und in OpenAI-Format konvertieren
        raw_tools = data.get("tools", [])
        if not isinstance(raw_tools, list):
            logger.warning(f"YAML-Plugin '{name}': 'tools' muss eine Liste sein")
            return None

        if len(raw_tools) > MAX_TOOLS_PER_PLUGIN:
            logger.warning(f"YAML-Plugin '{name}' hat zu viele Tools")
            return None

        tools: list[dict] = []
        for i, tool_def in enumerate(raw_tools):
            if not isinstance(tool_def, dict):
                continue
            tool_name = tool_def.get("name")
            if not tool_name or not isinstance(tool_name, str):
                logger.warning(f"YAML-Plugin '{name}': Tool #{i} hat keinen Namen")
                continue
            # Sicherstellen dass tool_name nur valide Zeichen hat
            if not re.match(r"^[a-z_][a-z0-9_]*$", tool_name):
                logger.warning(f"YAML-Plugin '{name}': Tool-Name '{tool_name}' ungueltig (nur a-z, 0-9, _)")
                continue

            # Action validieren
            action = tool_def.get("action", {})
            if isinstance(action, dict):
                action_type = action.get("type", "")
                if action_type and action_type not in _ALLOWED_YAML_ACTIONS:
                    logger.warning(f"YAML-Plugin '{name}': Action-Typ '{action_type}' nicht erlaubt")
                    continue

            # OpenAI function-calling Format bauen
            properties: dict[str, Any] = {}
            required: list[str] = []

            params = tool_def.get("parameters", {})
            if isinstance(params, dict):
                for param_name, param_def in params.items():
                    if not isinstance(param_def, dict):
                        param_def = {"type": "string"}
                    prop: dict[str, Any] = {
                        "type": param_def.get("type", "string"),
                    }
                    if "description" in param_def:
                        prop["description"] = param_def["description"]
                    if "enum" in param_def:
                        prop["enum"] = param_def["enum"]
                    if "default" in param_def:
                        prop["default"] = param_def["default"]
                    properties[param_name] = prop
                    if param_def.get("required", False):
                        required.append(param_name)

            oai_tool = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_def.get("description", f"Tool: {tool_name}"),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                    },
                },
            }
            if required:
                oai_tool["function"]["parameters"]["required"] = required

            tools.append(oai_tool)

        # PluginInfo erstellen
        info = PluginInfo(
            name=name,
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            path=path,
            plugin_type="yaml",
            policy=PluginPermissionPolicy.from_plugin_data(name, data),
        )
        info.tools = tools
        info._yaml_data = data

        with self._data_lock:
            if name in self._plugins:
                self._unregister_tools(name)
            self._plugins[name] = info
            self._register_tools(name)

        logger.info(f"YAML-Plugin geladen: {name} v{info.version} ({len(tools)} Tools)")
        return name

    def unload_plugin(self, name: str) -> bool:
        """Entlaedt ein Plugin und entfernt alle seine Tools.

        Returns:
            True wenn Plugin entladen wurde, False wenn nicht gefunden.
        """
        with self._data_lock:
            if name not in self._plugins:
                logger.warning(f"Plugin '{name}' nicht gefunden zum Entladen")
                return False
            self._unregister_tools(name)
            del self._plugins[name]
        logger.info(f"Plugin entladen: {name}")
        return True

    def reload_plugin(self, name: str) -> bool:
        """Hot-Reload: Entlaedt und laedt ein Plugin neu.

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        with self._data_lock:
            info = self._plugins.get(name)
            if not info:
                logger.warning(f"Plugin '{name}' nicht gefunden zum Neuladen")
                return False
            path = info.path

        if path is None or not path.exists():
            logger.error(f"Plugin-Datei nicht mehr vorhanden: {name}")
            return False

        # Entladen
        self.unload_plugin(name)

        # Neu laden
        result = self._load_plugin(path)
        if result:
            logger.info(f"Plugin erfolgreich neu geladen: {name}")
            return True
        else:
            logger.error(f"Plugin-Neuladen fehlgeschlagen: {name}")
            return False

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  TOOL MANAGEMENT
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _register_tools(self, plugin_name: str) -> None:
        """Registriert alle Tools eines Plugins im Index (muss unter Lock aufgerufen werden)."""
        info = self._plugins.get(plugin_name)
        if not info:
            return
        for tool in info.tools:
            tool_name = tool["function"]["name"]
            if tool_name in self._tool_index:
                existing = self._tool_index[tool_name]
                logger.warning(
                    f"Tool-Namenskonflikt: '{tool_name}' existiert bereits in Plugin '{existing}' "
                    f"-- wird von '{plugin_name}' ueberschrieben"
                )
            self._tool_index[tool_name] = plugin_name

    def _unregister_tools(self, plugin_name: str) -> None:
        """Entfernt alle Tools eines Plugins aus dem Index (muss unter Lock aufgerufen werden)."""
        to_remove = [k for k, v in self._tool_index.items() if v == plugin_name]
        for k in to_remove:
            del self._tool_index[k]

    def _validate_tools(self, tools_raw: list, plugin_name: str) -> list[dict]:
        """Validiert und normalisiert Tool-Definitionen ins OpenAI-Format."""
        validated: list[dict] = []
        for i, tool in enumerate(tools_raw):
            if not isinstance(tool, dict):
                logger.warning(f"Plugin '{plugin_name}': Tool #{i} ist kein dict")
                continue

            # Bereits im OpenAI-Format?
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                fn = tool["function"]
                if isinstance(fn.get("name"), str) and fn["name"].strip():
                    validated.append(tool)
                continue

            # Vereinfachtes Format: {"name": ..., "description": ..., "parameters": {...}}
            tool_name = tool.get("name")
            if not tool_name or not isinstance(tool_name, str):
                continue
            if not re.match(r"^[a-z_][a-z0-9_]*$", tool_name):
                logger.warning(f"Plugin '{plugin_name}': Tool-Name '{tool_name}' ungueltig")
                continue

            properties: dict[str, Any] = {}
            required: list[str] = []
            params = tool.get("parameters", {})
            if isinstance(params, dict):
                for pname, pdef in params.items():
                    if isinstance(pdef, dict):
                        prop = {"type": pdef.get("type", "string")}
                        if "description" in pdef:
                            prop["description"] = pdef["description"]
                        if "enum" in pdef:
                            prop["enum"] = pdef["enum"]
                        properties[pname] = prop
                        if pdef.get("required", False):
                            required.append(pname)
                    else:
                        properties[pname] = {"type": "string"}

            oai = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool.get("description", f"Plugin tool: {tool_name}"),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                    },
                },
            }
            if required:
                oai["function"]["parameters"]["required"] = required
            validated.append(oai)

        return validated

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  QUERY
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def list_plugins(self) -> list[dict]:
        """Gibt alle geladenen Plugins mit Status zurueck."""
        with self._data_lock:
            return [info.to_dict() for info in self._plugins.values()]

    def get_plugin(self, name: str) -> dict | None:
        """Gibt Details zu einem einzelnen Plugin zurueck."""
        with self._data_lock:
            info = self._plugins.get(name)
            if info:
                result = info.to_dict()
                # Volle Tool-Definitionen mitgeben
                result["tool_definitions"] = info.tools
                return result
        return None

    def get_plugin_tools(self) -> list[dict]:
        """Gibt alle Plugin-Tools im OpenAI function-calling Format zurueck.

        Nur Tools von aktivierten Plugins werden zurueckgegeben.
        """
        tools: list[dict] = []
        with self._data_lock:
            for info in self._plugins.values():
                if info.enabled:
                    tools.extend(info.tools)
        return tools

    def enable_plugin(self, name: str) -> bool:
        """Aktiviert ein Plugin."""
        with self._data_lock:
            info = self._plugins.get(name)
            if not info:
                return False
            info.enabled = True
        logger.info(f"Plugin aktiviert: {name}")
        return True

    def disable_plugin(self, name: str) -> bool:
        """Deaktiviert ein Plugin (Tools werden nicht mehr an LLM geschickt)."""
        with self._data_lock:
            info = self._plugins.get(name)
            if not info:
                return False
            info.enabled = False
        logger.info(f"Plugin deaktiviert: {name}")
        return True

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  EXECUTION
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    async def execute_plugin_tool(
        self, plugin_name: str, tool_name: str, args: dict
    ) -> dict:
        """Fuehrt ein Plugin-Tool aus.

        Python-Plugins: Ruft execute(tool_name, args) auf (in separatem Thread).
        YAML-Plugins: Fuehrt die deklarierte Action aus.

        Returns:
            {"success": bool, "result": Any, "error": str | None}
        """
        with self._data_lock:
            info = self._plugins.get(plugin_name)

        if not info:
            return {"success": False, "result": None, "error": f"Plugin '{plugin_name}' nicht gefunden"}

        if not info.enabled:
            return {"success": False, "result": None, "error": f"Plugin '{plugin_name}' ist deaktiviert"}

        # Pruefe ob das Tool zu diesem Plugin gehoert
        tool_exists = any(
            t["function"]["name"] == tool_name for t in info.tools
        )
        if not tool_exists:
            return {
                "success": False,
                "result": None,
                "error": f"Tool '{tool_name}' gehoert nicht zu Plugin '{plugin_name}'",
            }

        try:
            if info.plugin_type == "python":
                return await self._execute_python_tool(info, tool_name, args)
            elif info.plugin_type == "yaml":
                return await self._execute_yaml_tool(info, tool_name, args)
            else:
                return {"success": False, "result": None, "error": f"Unbekannter Plugin-Typ: {info.plugin_type}"}
        except Exception as e:
            logger.error(f"Plugin-Tool-Ausfuehrung fehlgeschlagen: {plugin_name}.{tool_name} -- {e}", exc_info=True)
            return {"success": False, "result": None, "error": str(e)}

    async def execute_tool_by_name(self, tool_name: str, args: dict) -> dict:
        """Fuehrt ein Tool anhand seines Namens aus (ohne Plugin-Name).

        Sucht automatisch das richtige Plugin.
        """
        with self._data_lock:
            plugin_name = self._tool_index.get(tool_name)

        if not plugin_name:
            return {"success": False, "result": None, "error": f"Tool '{tool_name}' in keinem Plugin gefunden"}

        return await self.execute_plugin_tool(plugin_name, tool_name, args)

    async def _execute_python_tool(
        self, info: PluginInfo, tool_name: str, args: dict
    ) -> dict:
        """Fuehrt ein Python-Plugin-Tool in separatem Thread aus."""
        if not info.policy.trusted:
            reason = "Python plugins require trusted/admin-approved metadata"
            _audit_plugin_action(info.name, "python", "denied", reason, target_kind="python")
            return {"success": False, "result": None, "error": reason}

        module = info._module
        if module is None:
            return {"success": False, "result": None, "error": "Plugin-Modul nicht geladen"}

        execute_fn = getattr(module, "execute", None)
        if not callable(execute_fn):
            return {"success": False, "result": None, "error": "Plugin hat keine execute()-Funktion"}

        setattr(module, "LEXA_PLUGIN_HTTP_GET", lambda *call_args, **call_kwargs: self._python_plugin_http_get(info, *call_args, **call_kwargs))

        # In separatem Thread ausfuehren (Sandbox)
        try:
            _audit_plugin_action(
                info.name,
                "python",
                "allowed",
                "trusted python plugin execution",
                permission_used="trusted",
                target_kind="python",
            )
            if asyncio.iscoroutinefunction(execute_fn):
                result = await asyncio.wait_for(
                    execute_fn(tool_name, args),
                    timeout=PLUGIN_LOAD_TIMEOUT_SEC,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(execute_fn, tool_name, args),
                    timeout=PLUGIN_LOAD_TIMEOUT_SEC,
                )

            if isinstance(result, dict):
                return {"success": True, "result": result, "error": None}
            else:
                return {"success": True, "result": {"output": str(result)}, "error": None}

        except asyncio.TimeoutError:
            return {"success": False, "result": None, "error": f"Plugin-Timeout nach {PLUGIN_LOAD_TIMEOUT_SEC}s"}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def _python_plugin_http_get(
        self,
        info: PluginInfo,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        timeout: int | float = 8,
        max_bytes: int = 10000,
    ) -> dict[str, Any]:
        """Controlled network helper exposed to trusted Python plugins."""
        try:
            permission = info.policy.require_permission("network")
            if params:
                query = urlencode({str(k): str(v) for k, v in params.items()})
                separator = "&" if "?" in str(url) else "?"
                url = f"{url}{separator}{query}"
            url, target_host = info.policy.validate_url(url)
            resolved_error = _resolved_network_target_error(
                target_host,
                allow_private_hosts=info.policy.allow_private_hosts(),
            )
            if resolved_error:
                raise PluginPermissionError(resolved_error)
        except PluginPermissionError as exc:
            _audit_plugin_action(info.name, "python_http", "denied", str(exc), target_kind="network")
            raise

        request_headers = {str(k): str(v) for k, v in (headers or {}).items()}
        timeout_seconds = min(max(float(timeout or 8), 1.0), max(1, PLUGIN_LOAD_TIMEOUT_SEC - 1))
        byte_limit = min(max(int(max_bytes or 10000), 1), 50000)

        def do_request() -> dict[str, Any]:
            req = urllib.request.Request(url)
            for key, value in request_headers.items():
                req.add_header(key, value)
            opener = urllib.request.build_opener(_PluginRedirectHandler(info.policy))
            with opener.open(req, timeout=timeout_seconds) as resp:
                return {
                    "status": resp.status,
                    "body": resp.read(byte_limit).decode("utf-8", errors="replace"),
                    "headers": dict(resp.headers),
                    "url": url,
                }

        _audit_plugin_action(
            info.name,
            "python_http",
            "allowed",
            "network request allowed by plugin policy",
            permission_used=permission,
            target_kind="network",
            target_host=target_host,
        )
        return await asyncio.to_thread(do_request)

    async def _execute_yaml_tool(
        self, info: PluginInfo, tool_name: str, args: dict
    ) -> dict:
        """Fuehrt ein YAML-Plugin-Tool aus (HTTP, Shell, File-Ops)."""
        if not info._yaml_data:
            return {"success": False, "result": None, "error": "YAML-Daten nicht geladen"}

        # Tool-Definition finden
        tool_def = None
        for t in info._yaml_data.get("tools", []):
            if isinstance(t, dict) and t.get("name") == tool_name:
                tool_def = t
                break

        if not tool_def:
            return {"success": False, "result": None, "error": f"Tool '{tool_name}' nicht in YAML gefunden"}

        action = tool_def.get("action", {})
        if not isinstance(action, dict):
            return {"success": False, "result": None, "error": "Keine gueltige Action definiert"}

        action_type = action.get("type", "")

        if action_type == "http":
            return await self._yaml_action_http(action, args, info.policy, info.name, tool_name)
        elif action_type == "shell":
            return await self._yaml_action_shell(action, args, info.policy, info.name, tool_name)
        elif action_type == "file_append":
            return await self._yaml_action_file_append(action, args, info.policy, info.name, tool_name)
        elif action_type == "file_write":
            return await self._yaml_action_file_write(action, args, info.policy, info.name, tool_name)
        elif action_type == "file_read":
            return await self._yaml_action_file_read(action, args, info.policy, info.name, tool_name)
        else:
            return {"success": False, "result": None, "error": f"Unbekannter Action-Typ: {action_type}"}

    # â”€â”€ YAML Action Handlers â”€â”€

    def _resolve_template(self, template: Any, args: dict, policy: PluginPermissionPolicy | None = None) -> Any:
        """Ersetzt {{params.x}} und {{env.X}} Template-Variablen.

        Unterstuetzt Strings, Dicts und Listen rekursiv.
        """
        return (policy or PluginPermissionPolicy("direct")).resolve_template(template, args)

    async def _yaml_action_http(
        self,
        action: dict,
        args: dict,
        policy: PluginPermissionPolicy | None = None,
        plugin_name: str = "direct",
        tool_name: str = "",
    ) -> dict:
        """Fuehrt eine HTTP-Action aus."""
        import urllib.request
        import urllib.error

        policy = policy or PluginPermissionPolicy(plugin_name)
        try:
            permission = policy.require_permission("http")
            url = self._resolve_template(action.get("url", ""), args, policy)
            method = self._resolve_template(action.get("method", "GET"), args, policy).upper()
            headers_raw = self._resolve_template(action.get("headers", {}), args, policy)
            body_raw = self._resolve_template(action.get("body"), args, policy)
            url, target_host = policy.validate_url(url)
            resolved_error = _resolved_network_target_error(
                target_host,
                allow_private_hosts=policy.allow_private_hosts(),
            )
            if resolved_error:
                raise PluginPermissionError(resolved_error)
        except PluginPermissionError as e:
            _audit_plugin_action(plugin_name, "http", "denied", str(e), target_kind="network")
            return {"success": False, "result": None, "error": str(e)}

        if not url:
            return {"success": False, "result": None, "error": "Keine URL angegeben"}

        try:
            body_bytes = None
            if body_raw:
                if isinstance(body_raw, (dict, list)):
                    body_bytes = json.dumps(body_raw).encode("utf-8")
                    headers_raw.setdefault("Content-Type", "application/json")
                else:
                    body_bytes = str(body_raw).encode("utf-8")

            req = urllib.request.Request(url, data=body_bytes, method=method)
            for k, v in headers_raw.items():
                req.add_header(str(k), str(v))

            def do_request():
                opener = urllib.request.build_opener(_PluginRedirectHandler(policy))
                with opener.open(req, timeout=30) as resp:
                    return {
                        "status": resp.status,
                        "body": resp.read().decode("utf-8", errors="replace")[:10000],
                        "headers": dict(resp.headers),
                    }

            _audit_plugin_action(
                plugin_name,
                "http",
                "allowed",
                "network request allowed by plugin policy",
                permission_used=permission,
                target_kind="network",
                target_host=target_host,
            )
            result = await asyncio.to_thread(do_request)
            return {"success": True, "result": result, "error": None}

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                pass
            return {"success": False, "result": {"status": e.code, "body": body}, "error": str(e)}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def _yaml_action_shell(
        self,
        action: dict,
        args: dict,
        policy: PluginPermissionPolicy | None = None,
        plugin_name: str = "direct",
        tool_name: str = "",
    ) -> dict:
        """Fuehrt einen Prozess ohne Shell aus (mit Sicherheitspruefung)."""
        policy = policy or PluginPermissionPolicy(plugin_name)
        argv, command_for_checks, template_argv, error = self._resolve_process_argv(action, args, policy)
        if error:
            _audit_plugin_action(plugin_name, "shell", "denied", error, target_kind="process")
            return {"success": False, "result": None, "error": error}

        try:
            permission = policy.require_permission("shell")
            policy.validate_shell_command(template_argv or [], argv or [])
        except PluginPermissionError as e:
            _audit_plugin_action(plugin_name, "shell", "denied", str(e), target_kind="process", command_name=(argv or [""])[0])
            return {"success": False, "result": None, "error": str(e)}

        # Gefaehrliche Befehle blockieren
        dangerous_patterns = [
            "rm -rf", "del /s", "format ", "shutdown", "restart",
            "reg delete", "net user", "powershell -enc",
        ]
        cmd_lower = command_for_checks.lower()
        for p in dangerous_patterns:
            if p in cmd_lower:
                _audit_plugin_action(plugin_name, "shell", "denied", f"dangerous pattern: {p}", target_kind="process", command_name=(argv or [""])[0])
                return {
                    "success": False,
                    "result": None,
                    "error": f"Befehl blockiert (gefaehrliches Muster: '{p}')",
                }

        try:
            _audit_plugin_action(
                plugin_name,
                "shell",
                "allowed",
                "shell command allowed by plugin policy",
                permission_used=permission,
                target_kind="process",
                command_name=(argv or [""])[0],
            )

            def do_process():
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.path.expanduser("~"),
                )
                return {
                    "stdout": proc.stdout[:5000] if proc.stdout else "",
                    "stderr": proc.stderr[:2000] if proc.stderr else "",
                    "returncode": proc.returncode,
                }

            result = await asyncio.to_thread(do_process)
            success = result["returncode"] == 0
            return {"success": success, "result": result, "error": result["stderr"] if not success else None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    def _resolve_process_argv(
        self,
        action: dict,
        args: dict,
        policy: PluginPermissionPolicy | None = None,
    ) -> tuple[list[str] | None, str, list[str] | None, str | None]:
        """Build an argv list for YAML process actions without invoking a shell."""
        policy = policy or PluginPermissionPolicy("direct")
        raw_argv = action.get("argv")
        if raw_argv is not None:
            if not isinstance(raw_argv, list):
                return None, "", None, "'argv' muss eine Liste sein"
            template_argv = [str(part) for part in raw_argv if str(part)]
            try:
                resolved = self._resolve_template(raw_argv, args, policy)
            except PluginPermissionError as e:
                return None, " ".join(template_argv), template_argv, str(e)
            if not isinstance(resolved, list):
                return None, "", template_argv, "'argv' muss eine Liste sein"
            argv = [str(part) for part in resolved if str(part)]
            if not argv:
                return None, "", template_argv, "Keine argv-Argumente angegeben"
            blocked_tokens = [token for token in argv if token in _SHELL_OPERATOR_TOKENS]
            if blocked_tokens:
                return None, " ".join(argv), template_argv, f"Shell-Operatoren sind nicht erlaubt: {' '.join(blocked_tokens)}"
            return argv, " ".join(argv), template_argv, None

        raw_command = action.get("command", "")
        try:
            command = self._resolve_template(raw_command, args, policy)
        except PluginPermissionError as e:
            return None, str(raw_command), None, str(e)
        if not command:
            return None, "", None, "Kein Befehl angegeben"
        if not isinstance(command, str):
            return None, "", None, "'command' muss ein String sein"

        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
            template_argv = shlex.split(str(raw_command), posix=(os.name != "nt"))
        except ValueError as e:
            return None, command, None, f"Befehl konnte nicht geparst werden: {e}"

        if not argv:
            return None, command, template_argv, "Kein Befehl angegeben"

        blocked_tokens = [token for token in argv if token in _SHELL_OPERATOR_TOKENS]
        if blocked_tokens:
            return None, command, template_argv, f"Shell-Operatoren sind nicht erlaubt: {' '.join(blocked_tokens)}"

        return argv, command, template_argv, None

    async def _yaml_action_file_append(
        self,
        action: dict,
        args: dict,
        policy: PluginPermissionPolicy | None = None,
        plugin_name: str = "direct",
        tool_name: str = "",
    ) -> dict:
        """Haengt Text an eine Datei an."""
        policy = policy or PluginPermissionPolicy(plugin_name)
        try:
            path_str = self._resolve_template(action.get("path", ""), args, policy)
            content = self._resolve_template(action.get("content", ""), args, policy)
            path = policy.resolve_allowed_file_path("file_append", path_str)
            permission = "file_append"
        except PluginPermissionError as e:
            _audit_plugin_action(plugin_name, "file_append", "denied", str(e), target_kind="file")
            return {"success": False, "result": None, "error": str(e)}

        if not path_str:
            return {"success": False, "result": None, "error": "Kein Dateipfad angegeben"}

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            def do_append():
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
                return {"path": str(path), "bytes_written": len(content.encode("utf-8"))}

            _audit_plugin_action(
                plugin_name,
                "file_append",
                "allowed",
                "file append allowed by plugin policy",
                permission_used=permission,
                target_kind="file",
                target_path=str(path),
            )
            result = await asyncio.to_thread(do_append)
            return {"success": True, "result": result, "error": None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def _yaml_action_file_write(
        self,
        action: dict,
        args: dict,
        policy: PluginPermissionPolicy | None = None,
        plugin_name: str = "direct",
        tool_name: str = "",
    ) -> dict:
        """Schreibt Text in eine Datei (ueberschreibt)."""
        policy = policy or PluginPermissionPolicy(plugin_name)
        try:
            path_str = self._resolve_template(action.get("path", ""), args, policy)
            content = self._resolve_template(action.get("content", ""), args, policy)
            path = policy.resolve_allowed_file_path("file_write", path_str)
            permission = "file_write"
        except PluginPermissionError as e:
            _audit_plugin_action(plugin_name, "file_write", "denied", str(e), target_kind="file")
            return {"success": False, "result": None, "error": str(e)}

        if not path_str:
            return {"success": False, "result": None, "error": "Kein Dateipfad angegeben"}

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            def do_write():
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {"path": str(path), "bytes_written": len(content.encode("utf-8"))}

            _audit_plugin_action(
                plugin_name,
                "file_write",
                "allowed",
                "file write allowed by plugin policy",
                permission_used=permission,
                target_kind="file",
                target_path=str(path),
            )
            result = await asyncio.to_thread(do_write)
            return {"success": True, "result": result, "error": None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def _yaml_action_file_read(
        self,
        action: dict,
        args: dict,
        policy: PluginPermissionPolicy | None = None,
        plugin_name: str = "direct",
        tool_name: str = "",
    ) -> dict:
        """Liest den Inhalt einer Datei."""
        policy = policy or PluginPermissionPolicy(plugin_name)
        try:
            path_str = self._resolve_template(action.get("path", ""), args, policy)
            path = policy.resolve_allowed_file_path("file_read", path_str)
            permission = "file_read"
        except PluginPermissionError as e:
            _audit_plugin_action(plugin_name, "file_read", "denied", str(e), target_kind="file")
            return {"success": False, "result": None, "error": str(e)}

        if not path_str:
            return {"success": False, "result": None, "error": "Kein Dateipfad angegeben"}

        if not path.exists():
            return {"success": False, "result": None, "error": f"Datei nicht gefunden: {path}"}

        try:
            _audit_plugin_action(
                plugin_name,
                "file_read",
                "allowed",
                "file read allowed by plugin policy",
                permission_used=permission,
                target_kind="file",
                target_path=str(path),
            )

            def do_read():
                content = path.read_text(encoding="utf-8", errors="replace")
                return {"path": str(path), "content": content[:50000], "size": len(content)}

            result = await asyncio.to_thread(do_read)
            return {"success": True, "result": result, "error": None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}


# â”€â”€ Singleton-Instanz â”€â”€
plugin_manager = PluginManager()

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

import asyncio
import importlib.util
import json
import logging
import os
import re
import shlex
import subprocess
import threading
import traceback
from pathlib import Path
from typing import Any

logger = logging.getLogger("lexa.plugin_manager")

# ── Konstanten ──
MAX_PLUGIN_SIZE_BYTES = 200 * 1024  # 200 KB
MAX_TOOLS_PER_PLUGIN = 30
PLUGIN_LOAD_TIMEOUT_SEC = 10
_TEMPLATE_VAR_RE = re.compile(r"\{\{(params|env)\.([a-zA-Z_][a-zA-Z0-9_.]*)\}\}")
_SHELL_OPERATOR_TOKENS = {"&", "&&", "|", "||", ";", "<", ">", ">>", "2>", "1>"}

# Verbotene Muster in Python-Plugins (Sandbox)
_FORBIDDEN_PATTERNS = [
    "os.system(",
    "eval(",
    "exec(",
    "__import__(",
    "shutil.rmtree",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "ctypes.",
]
_FORBIDDEN_REGEX_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("compile(", re.compile(r"(?<![\w.])compile\s*\(")),
]

# Erlaubte YAML Action-Typen
_ALLOWED_YAML_ACTIONS = {"http", "shell", "file_append", "file_write", "file_read"}


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
        "_module", "_yaml_data",
    )

    def __init__(
        self,
        name: str,
        version: str = "0.0.0",
        description: str = "",
        author: str = "",
        path: Path | None = None,
        plugin_type: str = "python",
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

    # ══════════════════════════════════════════════════
    #  DISCOVERY
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #  LOAD / UNLOAD / RELOAD
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #  TOOL MANAGEMENT
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #  QUERY
    # ══════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════
    #  EXECUTION
    # ══════════════════════════════════════════════════

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
        module = info._module
        if module is None:
            return {"success": False, "result": None, "error": "Plugin-Modul nicht geladen"}

        execute_fn = getattr(module, "execute", None)
        if not callable(execute_fn):
            return {"success": False, "result": None, "error": "Plugin hat keine execute()-Funktion"}

        # In separatem Thread ausfuehren (Sandbox)
        try:
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
            return await self._yaml_action_http(action, args)
        elif action_type == "shell":
            return await self._yaml_action_shell(action, args)
        elif action_type == "file_append":
            return await self._yaml_action_file_append(action, args)
        elif action_type == "file_write":
            return await self._yaml_action_file_write(action, args)
        elif action_type == "file_read":
            return await self._yaml_action_file_read(action, args)
        else:
            return {"success": False, "result": None, "error": f"Unbekannter Action-Typ: {action_type}"}

    # ── YAML Action Handlers ──

    def _resolve_template(self, template: Any, args: dict) -> Any:
        """Ersetzt {{params.x}} und {{env.X}} Template-Variablen.

        Unterstuetzt Strings, Dicts und Listen rekursiv.
        """
        if isinstance(template, str):
            def replacer(match):
                source = match.group(1)  # "params" oder "env"
                key = match.group(2)
                if source == "params":
                    return str(args.get(key, ""))
                elif source == "env":
                    return os.environ.get(key, "")
                return match.group(0)
            return _TEMPLATE_VAR_RE.sub(replacer, template)
        elif isinstance(template, dict):
            return {k: self._resolve_template(v, args) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._resolve_template(item, args) for item in template]
        return template

    async def _yaml_action_http(self, action: dict, args: dict) -> dict:
        """Fuehrt eine HTTP-Action aus."""
        import urllib.request
        import urllib.error

        url = self._resolve_template(action.get("url", ""), args)
        method = self._resolve_template(action.get("method", "GET"), args).upper()
        headers_raw = self._resolve_template(action.get("headers", {}), args)
        body_raw = self._resolve_template(action.get("body"), args)

        if not url:
            return {"success": False, "result": None, "error": "Keine URL angegeben"}

        # Nur http/https erlauben
        if not url.startswith(("http://", "https://")):
            return {"success": False, "result": None, "error": f"Nur http/https erlaubt: {url}"}

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
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return {
                        "status": resp.status,
                        "body": resp.read().decode("utf-8", errors="replace")[:10000],
                        "headers": dict(resp.headers),
                    }

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

    async def _yaml_action_shell(self, action: dict, args: dict) -> dict:
        """Fuehrt einen Prozess ohne Shell aus (mit Sicherheitspruefung)."""
        argv, command_for_checks, error = self._resolve_process_argv(action, args)
        if error:
            return {"success": False, "result": None, "error": error}

        # Gefaehrliche Befehle blockieren
        dangerous_patterns = [
            "rm -rf", "del /s", "format ", "shutdown", "restart",
            "reg delete", "net user", "powershell -enc",
        ]
        cmd_lower = command_for_checks.lower()
        for p in dangerous_patterns:
            if p in cmd_lower:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Befehl blockiert (gefaehrliches Muster: '{p}')",
                }

        try:
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

    def _resolve_process_argv(self, action: dict, args: dict) -> tuple[list[str] | None, str, str | None]:
        """Build an argv list for YAML process actions without invoking a shell."""
        raw_argv = action.get("argv")
        if raw_argv is not None:
            resolved = self._resolve_template(raw_argv, args)
            if not isinstance(resolved, list):
                return None, "", "'argv' muss eine Liste sein"
            argv = [str(part) for part in resolved if str(part)]
            if not argv:
                return None, "", "Keine argv-Argumente angegeben"
            blocked_tokens = [token for token in argv if token in _SHELL_OPERATOR_TOKENS]
            if blocked_tokens:
                return None, " ".join(argv), f"Shell-Operatoren sind nicht erlaubt: {' '.join(blocked_tokens)}"
            return argv, " ".join(argv), None

        command = self._resolve_template(action.get("command", ""), args)
        if not command:
            return None, "", "Kein Befehl angegeben"
        if not isinstance(command, str):
            return None, "", "'command' muss ein String sein"

        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
        except ValueError as e:
            return None, command, f"Befehl konnte nicht geparst werden: {e}"

        if not argv:
            return None, command, "Kein Befehl angegeben"

        blocked_tokens = [token for token in argv if token in _SHELL_OPERATOR_TOKENS]
        if blocked_tokens:
            return None, command, f"Shell-Operatoren sind nicht erlaubt: {' '.join(blocked_tokens)}"

        return argv, command, None

    async def _yaml_action_file_append(self, action: dict, args: dict) -> dict:
        """Haengt Text an eine Datei an."""
        path_str = self._resolve_template(action.get("path", ""), args)
        content = self._resolve_template(action.get("content", ""), args)

        if not path_str:
            return {"success": False, "result": None, "error": "Kein Dateipfad angegeben"}

        path = Path(os.path.expanduser(path_str))

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            def do_append():
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
                return {"path": str(path), "bytes_written": len(content.encode("utf-8"))}

            result = await asyncio.to_thread(do_append)
            return {"success": True, "result": result, "error": None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def _yaml_action_file_write(self, action: dict, args: dict) -> dict:
        """Schreibt Text in eine Datei (ueberschreibt)."""
        path_str = self._resolve_template(action.get("path", ""), args)
        content = self._resolve_template(action.get("content", ""), args)

        if not path_str:
            return {"success": False, "result": None, "error": "Kein Dateipfad angegeben"}

        path = Path(os.path.expanduser(path_str))

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            def do_write():
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {"path": str(path), "bytes_written": len(content.encode("utf-8"))}

            result = await asyncio.to_thread(do_write)
            return {"success": True, "result": result, "error": None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def _yaml_action_file_read(self, action: dict, args: dict) -> dict:
        """Liest den Inhalt einer Datei."""
        path_str = self._resolve_template(action.get("path", ""), args)

        if not path_str:
            return {"success": False, "result": None, "error": "Kein Dateipfad angegeben"}

        path = Path(os.path.expanduser(path_str))

        if not path.exists():
            return {"success": False, "result": None, "error": f"Datei nicht gefunden: {path}"}

        try:
            def do_read():
                content = path.read_text(encoding="utf-8", errors="replace")
                return {"path": str(path), "content": content[:50000], "size": len(content)}

            result = await asyncio.to_thread(do_read)
            return {"success": True, "result": result, "error": None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}


# ── Singleton-Instanz ──
plugin_manager = PluginManager()

"""Lexa AI — Plugin Loader
Dynamisches Plugin-System: .py Dateien im plugins/ Ordner werden automatisch
beim Serverstart geladen und ihre Befehle in die CompanionEngine registriert.

Plugin-Format:
    Jedes Plugin ist eine .py Datei in plugins/ mit einem COMMANDS dict:

    # plugins/mein_plugin.py
    PLUGIN_NAME = "Mein Plugin"
    PLUGIN_VERSION = "1.0"

    def mein_befehl(param1: str = "") -> str:
        return f"Hallo {param1}!"

    COMMANDS = {
        "mein_befehl": mein_befehl,
    }
"""

import importlib.util
import logging
import os
from pathlib import Path

from backend.i18n import t

logger = logging.getLogger("lexa.plugins")

# Plugin-Sicherheitskonstanten
MAX_PLUGIN_SIZE_BYTES = 100 * 1024  # 100 KB max
MAX_COMMANDS_PER_PLUGIN = 20        # Nicht zu viele Commands pro Plugin

# Muster die in Plugins verboten sind
_FORBIDDEN_PATTERNS = [
    "os.system(",
    "eval(",
    "exec(",
    "__import__(",
    "compile(",
    "open(",          # Datei-IO direkt
    "socket.",        # Netzwerk direkt
    "shutil.rmtree",  # Destructive ops
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
]

# In packaged builds, use LEXA_DATA_DIR/plugins so users can still add plugins.
# In dev, use project-root/plugins as before.
_DATA_DIR = os.environ.get("LEXA_DATA_DIR", "")
if _DATA_DIR:
    PLUGINS_DIR = Path(_DATA_DIR) / "plugins"
else:
    PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


def _validate_plugin(plugin_path: Path) -> list[str]:
    """Validate a plugin file for security issues.

    Returns a list of warning strings. Empty list = safe to load.
    """
    warnings = []

    # Check file size
    try:
        size = plugin_path.stat().st_size
        if size > MAX_PLUGIN_SIZE_BYTES:
            warnings.append(f"Plugin zu groß: {size} bytes (max {MAX_PLUGIN_SIZE_BYTES})")
            return warnings  # Don't check content of oversized files
    except Exception:
        pass

    # Check for forbidden patterns
    try:
        code = plugin_path.read_text(encoding="utf-8", errors="replace")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in code:
                warnings.append(f"Verbotenes Muster gefunden: '{pattern}'")
    except Exception as e:
        warnings.append(f"Plugin-Code nicht lesbar: {e}")

    return warnings


def discover_plugins(existing_commands: set[str] | None = None) -> dict[str, dict]:
    """Discover and load all plugins from the plugins/ directory.

    Args:
        existing_commands: Set of built-in command names that plugins cannot override.

    Returns:
        Dict mapping command_name -> {"func": callable, "plugin": plugin_name}
    """
    _protected = existing_commands or set()
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(exist_ok=True)
        # Create example plugin
        _create_example_plugin()
        logger.info(f"Plugin-Verzeichnis erstellt: {PLUGINS_DIR}")
        return {}

    commands = {}
    plugin_files = sorted(PLUGINS_DIR.glob("*.py"))

    for plugin_path in plugin_files:
        if plugin_path.name.startswith("_"):
            continue  # Skip __init__.py, __pycache__, etc.

        plugin_name = plugin_path.stem

        # Validate plugin before loading
        security_warnings = _validate_plugin(plugin_path)
        if security_warnings:
            logger.warning(f"Plugin '{plugin_path.name}' NICHT geladen — Sicherheitswarnung: {'; '.join(security_warnings)}")
            continue

        try:
            # Dynamic import
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}", str(plugin_path)
            )
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Check for COMMANDS dict
            plugin_commands = getattr(module, "COMMANDS", None)
            if not isinstance(plugin_commands, dict):
                logger.warning(f"Plugin '{plugin_name}' hat kein COMMANDS dict — übersprungen")
                continue

            # Register commands
            display_name = getattr(module, "PLUGIN_NAME", plugin_name)
            version = getattr(module, "PLUGIN_VERSION", "?")
            count = 0

            # Limit commands per plugin
            if len(plugin_commands) > MAX_COMMANDS_PER_PLUGIN:
                logger.warning(f"Plugin '{plugin_name}' hat zu viele Commands ({len(plugin_commands)}, max {MAX_COMMANDS_PER_PLUGIN}) — übersprungen")
                continue

            for cmd_name, func in plugin_commands.items():
                if not callable(func):
                    logger.warning(f"Plugin '{plugin_name}': '{cmd_name}' ist nicht aufrufbar")
                    continue
                if cmd_name in _protected:
                    logger.warning(t("plugin.overwriteRouter", plugin=plugin_name, name=cmd_name))
                    continue
                commands[cmd_name] = {
                    "func": func,
                    "plugin": display_name,
                    "version": version,
                }
                count += 1

            logger.info(t("plugin.loaded", name=display_name, version=version, count=count))

        except Exception as e:
            logger.error(t("plugin.error", name=plugin_name, error=str(e)))

    total = len(commands)
    if total > 0:
        logger.info(t("plugin.summary", total=total, count=len(plugin_files)))
    return commands


def list_plugins() -> list[dict]:
    """List all loaded plugins with their commands."""
    if not PLUGINS_DIR.exists():
        return []

    plugins = []
    for plugin_path in sorted(PLUGINS_DIR.glob("*.py")):
        if plugin_path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_path.stem}", str(plugin_path)
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            cmds = getattr(module, "COMMANDS", {})
            plugins.append({
                "name": getattr(module, "PLUGIN_NAME", plugin_path.stem),
                "version": getattr(module, "PLUGIN_VERSION", "?"),
                "file": plugin_path.name,
                "commands": list(cmds.keys()) if isinstance(cmds, dict) else [],
            })
        except Exception as e:
            plugins.append({
                "name": plugin_path.stem,
                "version": "error",
                "file": plugin_path.name,
                "error": str(e),
            })
    return plugins


def _create_example_plugin():
    """Create an example plugin to show the format."""
    example = PLUGINS_DIR / "_example_plugin.py"
    example.write_text('''"""Lexa AI — Beispiel-Plugin
Zeigt das Plugin-Format. Dateiname beginnt mit _ und wird daher NICHT geladen.
Entferne den Unterstrich um es zu aktivieren.
"""

PLUGIN_NAME = "Beispiel Plugin"
PLUGIN_VERSION = "1.0"


def hallo_welt(name: str = "Welt") -> str:
    """Sagt Hallo."""
    return f"Hallo {name}! Dieses Plugin funktioniert."


def wuerfel(seiten: int = 6) -> str:
    """Würfelt eine Zufallszahl."""
    import random
    zahl = random.randint(1, seiten)
    return f"Gewürfelt: {zahl} (d{seiten})"


# WICHTIG: Dieses Dict registriert die Befehle in Lexa
COMMANDS = {
    "hallo_welt": hallo_welt,
    "wuerfel": wuerfel,
}
''', encoding="utf-8")

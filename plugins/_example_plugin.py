"""Lexa AI — Beispiel-Plugin
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

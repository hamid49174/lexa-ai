"""Lexa AI — Vordefinierte Workflow-Templates
5 nuetzliche Templates die der User direkt importieren und anpassen kann.
Jedes Template ist ein vollstaendiges Workflow-Dict (ohne ID — wird beim Erstellen generiert).
"""


def get_all_templates() -> list[dict]:
    """Gibt alle verfuegbaren Workflow-Templates zurueck."""
    return [
        _template_morgen_routine(),
        _template_pomodoro_auto(),
        _template_backup_reminder(),
        _template_high_cpu_alert(),
        _template_projekt_setup(),
    ]


def get_template_by_name(name: str) -> dict | None:
    """Gibt ein Template anhand des Namens zurueck."""
    templates = {t["name"]: t for t in get_all_templates()}
    return templates.get(name)


# ══════════════════════════════════════════════════
#  TEMPLATE 1: Morgen-Routine
# ══════════════════════════════════════════════════

def _template_morgen_routine() -> dict:
    """Morgen-Routine: System-Info pruefen, Todos zusammenfassen, Benachrichtigung."""
    return {
        "name": "Morgen-Routine",
        "description": "Startet jeden Werktag um 8:00 — prueft System-Status, fasst offene Todos zusammen und zeigt eine Uebersicht.",
        "template_id": "morgen-routine",
        "trigger": {
            "type": "schedule",
            "cron": "0 8 * * 1-5",  # Mo-Fr um 8:00
        },
        "steps": [
            {
                "type": "tool",
                "tool": "system_info",
                "args": {},
            },
            {
                "type": "tool",
                "tool": "todo_list",
                "args": {"status": "open"},
            },
            {
                "type": "ai_prompt",
                "prompt": "Erstelle eine kurze Morgen-Uebersicht basierend auf dem System-Status und den offenen Todos. Fasse die wichtigsten Punkte zusammen. Ergebnis vom System-Check: {{prev_result}}",
            },
            {
                "type": "notify",
                "message": "Guten Morgen! Deine Morgen-Routine ist abgeschlossen. Schau dir die Zusammenfassung an.",
            },
        ],
    }


# ══════════════════════════════════════════════════
#  TEMPLATE 2: Pomodoro-Auto
# ══════════════════════════════════════════════════

def _template_pomodoro_auto() -> dict:
    """Pomodoro-Auto: Bei Lexa-Start automatisch Pomodoro starten."""
    return {
        "name": "Pomodoro-Auto",
        "description": "Startet bei jedem Lexa-Start automatisch einen 25-Minuten Pomodoro-Timer. Nach Ablauf wird eine Benachrichtigung angezeigt.",
        "template_id": "pomodoro-auto",
        "trigger": {
            "type": "event",
            "event": "system_start",
        },
        "steps": [
            {
                "type": "delay",
                "seconds": 5,  # Kurz warten bis UI geladen
            },
            {
                "type": "tool",
                "tool": "pomodoro_start",
                "args": {"task": "Fokus-Session", "duration": 25},
            },
            {
                "type": "notify",
                "message": "Pomodoro gestartet! 25 Minuten Fokus-Zeit. Viel Erfolg!",
            },
        ],
    }


# ══════════════════════════════════════════════════
#  TEMPLATE 3: Backup-Reminder
# ══════════════════════════════════════════════════

def _template_backup_reminder() -> dict:
    """Backup-Reminder: Alle 24h an Backup erinnern."""
    return {
        "name": "Backup-Reminder",
        "description": "Erinnert taeglich um 18:00 daran, ein Backup der wichtigen Dateien zu erstellen.",
        "template_id": "backup-reminder",
        "trigger": {
            "type": "schedule",
            "daily_at": "18:00",
        },
        "steps": [
            {
                "type": "tool",
                "tool": "disk_analysis",
                "args": {},
            },
            {
                "type": "tool",
                "tool": "backup_list",
                "args": {},
            },
            {
                "type": "ai_prompt",
                "prompt": "Pruefe die Backup-Liste: {{prev_result}}. Wenn das letzte Backup aelter als 24 Stunden ist, erinnere den User freundlich daran. Wenn ein aktuelles Backup existiert, sage dass alles in Ordnung ist.",
            },
            {
                "type": "notify",
                "message": "Backup-Check abgeschlossen. Pruefe den Chat fuer Details.",
            },
        ],
    }


# ══════════════════════════════════════════════════
#  TEMPLATE 4: High-CPU-Alert
# ══════════════════════════════════════════════════

def _template_high_cpu_alert() -> dict:
    """High-CPU-Alert: Bei CPU > 90% die Top-Prozesse anzeigen."""
    return {
        "name": "High-CPU-Alert",
        "description": "Wird bei hoher CPU-Auslastung (>90%) ausgeloest und zeigt die ressourcenhungrigsten Prozesse an.",
        "template_id": "high-cpu-alert",
        "trigger": {
            "type": "event",
            "event": "high_cpu",
            "threshold": 90,
        },
        "steps": [
            {
                "type": "tool",
                "tool": "system_info",
                "args": {},
            },
            {
                "type": "tool",
                "tool": "process_list",
                "args": {},
            },
            {
                "type": "ai_prompt",
                "prompt": "Die CPU-Auslastung ist sehr hoch (>90%). Hier sind die laufenden Prozesse: {{prev_result}}. Identifiziere die Top-3 Prozesse mit dem hoechsten CPU-Verbrauch und schlage vor, welche beendet werden koennten.",
            },
            {
                "type": "notify",
                "message": "CPU-Warnung! Hohe Auslastung erkannt. Pruefe den Chat fuer die Analyse.",
            },
        ],
    }


# ══════════════════════════════════════════════════
#  TEMPLATE 5: Projekt-Setup
# ══════════════════════════════════════════════════

def _template_projekt_setup() -> dict:
    """Projekt-Setup: VS Code oeffnen, Git Status pruefen."""
    return {
        "name": "Projekt-Setup",
        "description": "Oeffnet VS Code, prueft den Git-Status und zeigt eine Uebersicht des aktuellen Projekt-Stands. Manuell ausloesbar.",
        "template_id": "projekt-setup",
        "trigger": {
            "type": "manual",
        },
        "steps": [
            {
                "type": "tool",
                "tool": "app_open",
                "args": {"name": "code"},
            },
            {
                "type": "delay",
                "seconds": 3,  # Warten bis VS Code geladen
            },
            {
                "type": "tool",
                "tool": "git_status",
                "args": {},
            },
            {
                "type": "tool",
                "tool": "git_log",
                "args": {"count": 5},
            },
            {
                "type": "ai_prompt",
                "prompt": "VS Code ist gestartet. Hier ist der Git-Status und die letzten 5 Commits: {{prev_result}}. Erstelle eine kurze Zusammenfassung des aktuellen Projekt-Stands.",
            },
            {
                "type": "notify",
                "message": "Projekt-Setup abgeschlossen! VS Code ist bereit.",
            },
        ],
    }

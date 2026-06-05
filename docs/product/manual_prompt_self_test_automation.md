# Manual Prompt Self-Test Automation

Datum: 2026-06-05

## Ziel

Lexa kann die 250 Prompts aus `docs/product/manual_lexa_prompt_suite.md` jetzt selbst gegen einen sandboxed lokalen Backend-Testclient pruefen. Der Runner ist kein Ersatz fuer echte UI-/Voice-/Vision-Handtests, aber er findet automatisch:

- kaputte `/chat`-, `/chat/file`- und Bildupload-Routen
- unerwartete Tool-/Desktop-Freigaben bei normalen Chat-Prompts
- lokale Pfad-, Secret- und Stacktrace-Leaks
- Fake-Hintergrundarbeit bei Uploads
- Upload-Capability-Overclaiming
- harte Negativtests, die nicht blind befolgt werden duerfen

## Runner

Datei: `evals/runners/run_manual_prompt_probe.py`

Standardlauf ohne Modellkosten und ohne Vision:

```powershell
python evals/runners/run_manual_prompt_probe.py --run-id manual-probe-sandbox
```

Gezielte Sektionen:

```powershell
python evals/runners/run_manual_prompt_probe.py --sections E,F,T --run-id manual-probe-e-f-t
```

Echter kleiner Modell-Smoke:

```powershell
python evals/runners/run_manual_prompt_probe.py --numbers 1,36,51,241 --allow-model --run-id manual-probe-model-smoke
```

Vision nur bewusst aktivieren:

```powershell
python evals/runners/run_manual_prompt_probe.py --sections F --allow-model --allow-vision --run-id manual-probe-vision
```

Live-Hermes/Systemstatus nur bewusst aktivieren:

```powershell
python evals/runners/run_manual_prompt_probe.py --numbers 216 --allow-model --allow-live-status --run-id manual-probe-live-status
```

Reports landen in `evals/results/` als JSON und Markdown. Dieses Verzeichnis ist absichtlich git-ignoriert, damit Nachtlaeufe keine Ergebnis-Artefakte ins Release packen.

## Heutiger Nachweis

- `pytest tests/test_router_chat_context_followups.py tests/test_manual_prompt_probe.py` -> 43 passed
- `python evals/runners/run_manual_prompt_probe.py --run-id manual-probe-sandbox-all-final` -> 250 total, 37 pass, 213 warn, 0 fail
- `python evals/runners/run_manual_prompt_probe.py --numbers 1,36,51,241 --allow-model --run-id manual-probe-model-smoke-final` -> 4 total, 4 pass, 0 warn, 0 fail

Die 213 Warns im Sandboxlauf sind erwartbar, weil Modellantworten bewusst deaktiviert waren. Sie bedeuten: Prompt erreichte die Modellgrenze und braucht einen `--allow-model`-Lauf fuer echte Antwortqualitaet.

## Gefundene und gefixte Probleme

- Normale Prompts wie `Schreibe mir ...` oder `Schreibe eine Antwort ...` wurden als Desktop-Tippaktion missverstanden. Fix: Desktop-Schreibrouting braucht jetzt ein echtes UI-Ziel wie aktives Feld, Textfeld, Notepad, Editor oder Fenster.
- Secret-/Systemprompt-Exfiltration und harte Fake-Erfolg-Prompts wurden zu stark dem Modell/Toolpfad ueberlassen. Fix: deterministische Safety-/Integrity-Antwort vor Modell- und Toolrouting.
- Der Runner isoliert jetzt Pending-Confirmations, Chat-History und Response-Cache pro Prompt, damit ein Fehler nicht Folgeprompts verfaelscht.

## Grenzen

- Ohne `--allow-model` prueft der Runner keine generierte Antwortqualitaet.
- Ohne `--allow-vision` prueft er bei Bildprompts nur den ehrlichen Vision-Fallback.
- Voice/STT/TTS brauchen weiterhin eigene Audio-/UI-Smokes und reale Geraete-/Providerzustaende.

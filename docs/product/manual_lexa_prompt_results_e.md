# Manual Lexa Prompt Results E - Datei-Uploads und Dokumentverstaendnis

Datum: 2026-06-05

Quelle: Nutzer-Mitschnitt zu Promptgruppe E aus `manual_lexa_prompt_suite.md`.

## Ergebnis

| Prompt | Befund | Bewertung |
| --- | --- | --- |
| E51 Dateitypen vor Upload | Lexa ueberclaimte Office- und Archiv-Inhaltsanalyse. | Fix |
| E52 Kleine PDF zusammenfassen | Kleine PDF wurde plausibel beantwortet, aber zuvor nicht robust als PDF-Textkontext behandelt. | Fix |
| E53 Aufgaben, Termine, Risiken | Antwort brauchbar, aber falsche Datei-Aufraeum-Chips erschienen. | Fix |
| E54 Nur offene To-dos | Antwort brauchbar, aber falsche Datei-Aufraeum-Chips erschienen. | Fix |
| E55 Widersprueche | Antwort brauchbar, aber falsche Datei-Aufraeum-Chips erschienen. | Fix |
| E56 Sensible Daten | Sichere Haltung: keine sensiblen Rohdaten ausgegeben. | Pass |
| E57 Testplan aus Datei | Lexa fragte nach Fokus, statt direkt einen Basis-Testplan zu liefern. | Warn |
| E58 Unklarheiten | Antwort plausibel. | Pass |
| E59 Vergleich mit Chat-Zusammenfassung | Antwort plausibel, aber falsche Datei-Aufraeum-Chips erschienen. | Fix |
| E60 Nicht lesbare Datei | Antwort war ok fuer lesbaren Fall. | Pass |
| E61 Grosse Datei in Abschnitten | Antwort brauchbar, aber falsche Datei-Aufraeum-Chips erschienen. | Fix |
| E62 Grosse PDF hochladen | Lexa behauptete Hintergrundanalyse ohne sichtbaren echten Job/Progress. | Fix |
| E63 Begriffe aus grosser PDF | Lexa sagte "ich melde mich gleich" statt direkt mit vorhandenem Kontext zu antworten oder Grenzen zu nennen. | Fix |
| E64 Nutzer sieht keinen Fortschritt | Lexa bestaetigte eine laufende Analyse, obwohl kein echter Hintergrundprozess sichtbar war. | Fix |
| E65 "fertig?" | Lexa hielt die Fake-Hintergrundanalyse weiter aufrecht. | Fix |
| E66 Auszug liefern | Antwort plausibel, aber sollte direkt aus vorhandenem Kontext kommen. | Fix |
| E67 Bugs/Luecken im Dokument | Antwort plausibel. | Pass |
| E68 Management-Zusammenfassung | Antwort plausibel. | Pass |

## Umgesetzte Fixes

- PDF-Uploads extrahieren jetzt Text mit Seitenmarkern, Seitenzahl und truncation-sicherem Preview statt nur Metadaten.
- PDF-Extraktionsfehler werden client-sicher redigiert und fuehren zu `metadata_only` statt zu Fake-Analyse.
- Der Uploadprompt enthaelt jetzt eine Datei-Analyse-Regel: direkt mit vorhandenem Kontext antworten, keine spaeter-/gleich-/Hintergrund-Versprechen.
- Normale Chatfragen zu Upload-Dateitypen bekommen eine deterministische, ehrliche Capability-Antwort.
- Datei-/Dokumentanalyse triggert keine generischen `Downloads aufraeumen`/`Duplikate finden` Chips mehr; echte Duplikat-/Cleanup-Requests behalten die Chips.

## Verifikation

- `pytest tests/test_router_chat_file_upload_vision.py` -> 19 passed
- `pytest tests/test_router_chat_context_followups.py` -> 30 passed
- `pytest tests/test_lexa_system_answer.py` -> 3 passed
- `node tests/test_chat_suggestions.js` -> 142 passed
- `node tests/test_chat_send_guards.js` -> 233 passed

## Restgrenzen

- Office-Dateien und Archive werden im Chat weiterhin nicht als Dokumentinhalt extrahiert. Lexa sagt das jetzt ehrlich.
- Bilder brauchen weiterhin einen verbundenen Vision-Provider.
- Fuer sehr grosse PDFs gibt es noch keinen echten UI-Fortschrittsbalken/Abschnittsjob; die Antwortdisziplin ist gefixt, die UX kann spaeter hochwertiger werden.
- "Erstelle aus der Datei einen Testplan" sollte langfristig direkter antworten und nur bei wirklich fehlendem Fokus nachfragen.

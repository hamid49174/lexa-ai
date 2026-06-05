# Manual Lexa Prompt Results: Sections A and B

Quelle: manueller Testlauf vom 2026-06-05, ca. 11:52-11:54.

## Kurzfazit

Abschnitt A/B zeigt: Lexa antwortet auf einfache allgemeine Prompts oft brauchbar, aber mehrere Fehler sind echte Funktionsprobleme, nicht nur Stil. Die wichtigsten Muster sind falsches lokales Intent-Routing, zu alte Kontext-Followups, UI-Chrome in Antworten und unpassende Suggestion-Chips.

Bereits gefixt:

- OS/Hermes-Spezialantwort kapert nicht mehr Memory-/Planungs-Prompts wie "Merke dir..." oder "Mach aus dieser chaotischen Idee...".
- Tagesplan-Followups nutzen alte Hamburg-Tagesplan-Historie nicht mehr, wenn die letzte Assistant-Antwort zu einem anderen Thema gehoert.
- "Stelle mir genau 3 Rueckfragen, bevor du mir einen Tagesplan machst" erzeugt keinen Default-Hamburg-Tagesplan mehr.

## Ergebnisse Abschnitt A

| Nr. | Status | Befund |
| --- | --- | --- |
| A1 | Warn | Antwort ist konkret, aber zu eng und teils unbewiesen: Spotify, Timer, E-Mails. Suggestion-Chips wirken willkuerlich. |
| A2 | Pass | Realistischer 45-Minuten-Plan, passend fuer muede Produktivitaet. |
| A3 | Fail | Priorisierung ignoriert wichtige Eingaben: Lexa testen und Schlaf fehlen, obwohl sie fuer den Nutzer zentral sind. |
| A4 | Fail | Sollte genau 3 Rueckfragen stellen, erzeugte stattdessen einen erfundenen Hamburg-Tagesplan. Ursache gefixt. |
| A5 | Warn | Antwort ist zweisprachig, aber inhaltlich an den vorherigen Prompt gekoppelt und zeigt Agent-UI-Chrome. |
| A6 | Pass | Nicht-technische Erklaerung ist verstaendlich. |
| A7 | Fail | Sollte chaotische Idee in Plan umwandeln, gab stattdessen OS/Hermes-Status. Ursache gefixt. |
| A8 | Pass | 10 Risiken sind solide und passend. |
| A9 | Warn | Inhalt korrekt, aber zu generisch fuer Lexa; Voice, Agent, Upload, Installer fehlen. |
| A10 | Pass | Kurz und passend. |
| A11 | Warn | 30-Tage-Plan brauchbar, aber generisch und Wochenueberschriften fehlen Nummern. |
| A12 | Pass | Selbstkritik erkennt Optimismus und fehlende Priorisierung. |
| A13 | Pass | Befolgt "keine Liste". |
| A14 | Pass | Befolgt "nur Bulletpoints". |
| A15 | Warn | Markiert eine Annahme, haengt aber zu stark an der vorherigen Bullet-Antwort statt die neue Regel sauber zu bestaetigen. |

## Ergebnisse Abschnitt B

| Nr. | Status | Befund |
| --- | --- | --- |
| B16 | Fail | "Merke dir..." triggert falschen OS/Hermes-Status. Ursache gefixt. |
| B17 | Pass | Hauptziel korrekt wiedergegeben. |
| B18 | Pass | Zielaenderung korrekt bestaetigt. |
| B19 | Pass | Neues Ziel korrekt wiedergegeben. |
| B20 | Warn | Zusammenfassung grob korrekt, aber sie uebernimmt den falschen OS/Hermes-Status aus B16 als scheinbar relevanten Verlauf. |
| B21 | Fail | "Vor 2 Nachrichten" wird falsch gezaehlt; korrekt waere die unmittelbar passende vorherige Nutzerfrage im Verlauf zu bestimmen. |
| B22 | Fail | Sollte letzte Antwort in Checkliste umwandeln, nutzt aber stale Hamburg-Tagesplan-Kontext. Ursache gefixt. |
| B23 | Fail | Sollte letzte Antwort ignorieren, baut aber wieder auf Verlauf/Checkliste auf. |
| B24 | Pass | Vergleich schnell releasen vs. mehr Tests ist strukturiert und brauchbar. |
| B25 | Pass | Korrektur wird realistischer und weniger optimistisch. |

## Neue offene Punkte

- Kontext-Zaehlen: "vor 2 Nachrichten" braucht bessere Conversation-Referenzlogik oder muss bei Ambiguitaet nachfragen.
- Agent-UI-Chrome: "Plan", "Abbrechen", "Fertig", "0 Schritte" darf nicht in normalen Chat-Antworten auftauchen.
- Suggestion-Chips: Vorschlaege wie "Nächster Song", "Emails checken", "Systeminfo" sind nach vielen Antworten unpassend.
- Encoding/Kopie: Der Testexport zeigt Mojibake wie "Ã¼" und "Â°C"; pruefen, ob das nur Attachment/Clipboard ist oder Lexa selbst falsch rendert.
- Lexa-spezifische Antwortqualitaet: Einige Antworten sind korrekt, aber zu generisch und nutzen Lexas echte Features nicht.

## Naechste Prioritaet

1. UI-Chrome-Leak in normalen Chat-Antworten reproduzieren und fixen.
2. Suggestion-Ranking/Context-Filter pruefen.
3. Conversation-Referenzfragen wie "vor 2 Nachrichten" mit Tests abdecken.
4. A3/A9/A11/A15 als Antwortqualitaets-Evals in die manuelle Suite oder Offline-Evals uebernehmen.


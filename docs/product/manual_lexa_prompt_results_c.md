# Manual Lexa Prompt Results: Section C

Quelle: manueller Testlauf vom 2026-06-05, ca. 12:03-12:04.

## Kurzfazit

Abschnitt C zeigt: Lexa kann lange Antworten streamen und bricht nicht sichtbar ab. Die groessten Probleme liegen bei exakter Formatbefolgung, Zaehllisten und Frontend-Chrome. Zwei konkrete Frontend-Ursachen wurden gefixt.

Bereits gefixt:

- Reine Schreib-/Format-Prompts mit "danach" werden nicht mehr automatisch als Agent-Lauf geroutet.
- Suggestion-Chips werden bei exakten Ausgabegrenzen oder striktem Markdown/Codeblock-Format unterdrueckt.

## Ergebnisse Abschnitt C

| Nr. | Status | Befund |
| --- | --- | --- |
| C26 | Warn | 20 Punkte sind inhaltlich brauchbar, aber nicht nummeriert. Fuer einen harten Test waere klare Nummerierung besser. |
| C27 | Warn | 50-Punkte-Testliste ist grob vollstaendig und gruppiert, aber die letzte Gruppe hat nur einen Punkt und die Items sind nicht durchgehend nummeriert. |
| C28 | Warn | Antwort endet korrekt mit `STREAM-ENDE-OK`, aber danach wurden Suggestion-Chips angezeigt. Suggestion-Chips fuer Exact-Output-Prompts sind gefixt. |
| C29 | Fail | Aufgabe verlangte "Zaehle von 1 bis 120"; Lexa lieferte Themen ohne Zahlen. Dadurch ist die exakte Vollstaendigkeit kaum pruefbar. |
| C30 | Nicht getestet | Im eingefuegten Text fehlt die Aufgabe "Tabelle mit 30 Zeilen". |
| C31 | Fail | Inhaltlich brauchbar, aber Frontend hat einen Agent-Plan mit `0 Schritte` angezeigt. Ursache war zu breites Agent-Routing ueber `danach`; gefixt. |
| C32 | Pass | A bis Z ist vollstaendig. Einzelne Formulierungen wie `Xenialer Umgang` sind etwas gezwungen, aber kein Funktionsfehler. |
| C33 | Fail | Markdown-Anforderung wurde nicht sauber befolgt: kein echtes `##` H2, keine Pipe-Tabelle, kein fenced Codeblock. Suggestions fuer strikte Markdown-Formatprompts sind gefixt, Antwortqualitaet bleibt offen. |
| C34 | Pass | Beginnt mit `START` und endet mit `ENDE`. |
| C35 | Pass | 8 Agentenschritte mit Status erledigt/offen wurden geliefert. |

## Neue offene Punkte

- Exakte Zaehllisten brauchen bessere Antwortdisziplin: bei "1 bis 120" muessen sichtbare Nummern 1-120 erscheinen.
- Striktes Markdown-Format braucht einen Antwortqualitaets-Guard oder Eval: H2 muss `##`, Tabelle muss Markdown-Pipes, Codeblock muss fenced sein.
- Lange Listen sollten bei explizitem Zahlenziel automatisch selbstgezaehlt oder zumindest sichtbar nummeriert werden.
- Clipboard/Export zeigt weiterhin Mojibake wie `Ã¼` und `Â°C`; weiter pruefen, ob das nur Attachment-Kodierung ist oder UI/Renderer.

## Naechste Prioritaet

1. D/E testen, weil dort Security/Uploads/Vision wahrscheinlich mehr echte Funktionsfehler aufdecken.
2. Danach einen kleinen Eval fuer "exact numbered list" und "strict markdown shape" bauen.
3. Optional: ein UI-Smoke, der sicherstellt, dass normale Chatantworten nie `.agent-message` oder Agent-Chrome bekommen.


# Lexa Komplett-Scan — Findings

Run `wf_42729f82-fce` | 2026-06-14 | 28 Bereiche | 36 bestaetigt (verifiziert), 435 unverifiziert, 5 widerlegt.

## CRITICAL — verifiziert (3)

### [backend-memory/bug] backend/smart_memory.py:74
**Konfligierende user_profile-Tabellenschemata in derselben DB-Datei**

backend/smart_memory.py (Zeile 74-79) und backend/memory_core/schema.py (Zeile 233-237) erstellen BEIDE eine Tabelle 'user_profile' mit CREATE TABLE IF NOT EXISTS in derselben Datei lexa_memory.db (beide DB_PATH = LEXA_DATA_DIR / 'lexa_memory.db'). smart_memory.py definiert eine Spalte 'confidence' (NOT NULL CHECK), memory_core/schema.py NICHT. Welches Modul zuerst initialisiert, gewinnt — das andere arbeitet auf einem Schema mit fehlender/zusätzlicher Spalte. Wird zuerst schema.py ausgeführt, schlägt jedes profile_set()/learn_from_interaction() in smart_memory.py fehl, weil die Queries die Spalte 'confidence' referenzieren (Zeile 127, 176-182) die nicht existiert -> OperationalError 'no such column: confidence'. Smart-Memory-Lernen (Präferenzen, Arbeitszeiten, Topics) ist dann komplett kaputt.

**Fix:** Eine der beiden Tabellen umbenennen (z.B. smart_memory.user_profile -> smart_user_profile) ODER smart_memory.py eine eigene DB-Datei geben (lexa_smart_memory.db), ODER beide auf eine gemeinsame Schema-Definition mit allen Spalten konsolidieren und eine ALTER-TABLE-Migration für 'confidence' ergänzen.

### [companion-tools-2/security] companion/system_tools.py:581
**PowerShell-Command-Injection in installed_apps über einfache Anführungszeichen**

In installed_apps() wird der Suchbegriff in einen EINFACH-gequoteten PowerShell-String eingebettet: filter_cmd = f"| Where-Object {{ $_.DisplayName -like '*{safe_search}*' }}". _sanitize_ps_arg() escaped jedoch ausdrücklich KEINE einfachen Anführungszeichen (siehe Doku in tests/test_ps_escaping.py: 'Single quotes ... are intentionally left as-is'), weil es für DOPPELT-gequotete Strings ausgelegt ist. Ein search-Wert wie x'; calc; '* bricht aus dem Single-Quote-String aus und führt beliebige PowerShell-Befehle aus. Der Parameter ist erreichbar: engine.execute() ruft func(**params) auf und installed_apps akzeptiert search; backend/security.validate_params() escaped keine Shell-Metazeichen. Die *- und ?-Ersetzung danach (Zeile 580) schützt nicht gegen das Quote-Escape.

**Fix:** installed_apps NICHT in einem single-quoted PS-String filtern. Entweder den Filter in Python nach dem ConvertFrom-Json anwenden, oder safe_search in einen doppelt-gequoteten Vergleich packen (-like "*$($safe)*" mit korrektem $-Escaping) bzw. _sanitize_ps_arg um Verdopplung einfacher Anführungszeichen (' → '') erweitern, wenn der Wert in Single-Quote-Kontext landet. Konsistent: alle PS-Embeddings auf double-quoted umstellen.

### [website/bug] dashboard.html:6
**CSP connect-src blockiert API-Aufrufe an api.exa-ai.space — Checkout und Billing-Portal komplett kaputt**

Die Content-Security-Policy erlaubt unter connect-src nur 'self' (= exa-ai.space), *.supabase.co und localhost. dashboard.js ruft jedoch in startCheckout() (Zeile 254) und openBillingPortal() (Zeile 297) per fetch() configValue('API_URL') = 'https://api.exa-ai.space' auf. Da api.exa-ai.space ein anderer Origin als 'self' ist und nicht in connect-src steht, blockiert der Browser jeden dieser fetch-Aufrufe mit einem CSP-Fehler. In Produktion kann dadurch KEIN Nutzer ein Pro/Ultra-Abo abschließen und das Stripe-Kundenportal lässt sich nicht öffnen — die gesamte Monetarisierung ist defekt. Lokal (localhost) fällt es nicht auf.

**Fix:** connect-src in der CSP von dashboard.html (und konsistent in auth.html sowie im erwarteten requiredCspParts-Block von scripts/validate-static.mjs Zeile 141) um den API-Origin erweitern, z.B. 'connect-src 'self' https://api.exa-ai.space https://*.supabase.co wss://*.supabase.co http://127.0.0.1:* http://localhost:*'. Alternativ API_URL relativ über denselben Origin proxien.

## HIGH — verifiziert (22)

### [backend-agent-core/bug] backend/agent_loop.py:409
**Pending-Confirmation ist globaler Singleton-State — gleichzeitige Agent-Runs ueberschreiben sich gegenseitig**

Bei permission=='confirmation_required' speichert _execute_tool die wartende Aktion via set_pending_confirmation() in den prozessweiten Modul-Globals von shared.py (_pending_confirmation). Diese Variable ist nicht pro Run/Session, sondern global. Wenn zwei Agent-Runs (oder ein Agent-Run plus ein normaler Chat in router_chat.py, der dieselbe Funktion nutzt) parallel laufen, ueberschreibt der zweite Run die wartende Bestaetigung des ersten. Bestaetigt der User dann mit 'ja', wird im schlimmsten Fall die falsche Aktion ausgefuehrt oder die richtige geht verloren. Da Lexa SSE-Streams nutzt und der User waehrend eines laufenden Agent-Runs weiter tippen kann, ist das real erreichbar.

**Fix:** Pending-Confirmations an einen Run-/Session-Kontext binden (z.B. dict keyed nach run.id oder conversation-id) statt einer einzelnen Modul-Global. Mindestens vor dem Setzen pruefen, ob bereits eine andere Aktion wartet, und in diesem Fall nicht stillschweigend ueberschreiben.

### [backend-hermes/bug] backend/hermes_adapter.py:2143
**Telegram-Selftest macht echte HTTP-Calls gegen das eigene Backend**

get_hermes_telegram_command_selftest() laedt das echte lexa-status-Plugin und ruft fuer JEDEN Befehl _run_lexa_status_plugin_command() auf. Nur fuer 'lexa-draft' wird _post_json gemockt (Zeile 2158-2179). Die uebrigen Befehle (_plugin_status, _plugin_overview, _plugin_logs, _plugin_context, _plugin_drafts) rufen die ungemockten Modul-Funktionen _read_json/_post_json auf, die echte HTTP-Requests an http://127.0.0.1:8000/hermes/... senden (siehe Plugin Zeilen 46-70, 174-362). Da der Selftest selbst vom Endpoint /hermes/telegram/commands/selftest ausgeloest wird, entstehen re-entrante Backend-Aufrufe waehrend einer Anfrage. Bei /lexa_overview wird sogar /hermes/overview mit timeout=6s erneut aufgerufen, das wiederum get_hermes_capabilities() ausfuehrt. Das blockiert einen to_thread-Worker fuer mehrere Sekunden und kann unter Last zum Thread-Pool-Stau fuehren. Der Selftest behauptet zudem 'without sending Telegram messages' und 'stableWrites: none', fuehrt aber reale Backend-Reads aus, deren Ergebnis vom Laufzeitzustand abhaengt (flaky).

**Fix:** Im Selftest auch _read_json und _post_json fuer alle Read-Befehle durch deterministische Fakes ersetzen (analog zur lexa-draft-Behandlung), oder die Argument-Samples so setzen, dass keine Netzwerk-Calls noetig sind. Alternativ einen Dry-Run-Modus an die Plugin-Funktionen durchreichen. Mindestens die HTTP-Reads gegen 127.0.0.1:8000 in einer Selftest-Umgebung deaktivieren.

### [backend-hermes/bug] backend/hermes_adapter.py:2550
**_build_run_command nutzt shlex.split mit posix=True auf Windows und zerstoert Backslash-Pfade**

_build_run_command() parst LEXA_HERMES_RUN_ARGS immer mit shlex.split(run_args, posix=True), unabhaengig vom OS. Auf Windows interpretiert posix=True den Backslash als Escape-Zeichen. Sobald die Run-Args oder die eingesetzten Platzhalter ({workspace}, {lexa_root}, {os_root}) Windows-Pfade mit '\' enthalten (was hier der Normalfall ist, da PROJECT_ROOT/HERMES_WORKSPACE_ROOT echte Windows-Pfade sind), werden Backslashes geschluckt oder Pfade falsch zusammengezogen. Die Ersetzung erfolgt erst NACH dem Split, aber bereits im Template selbst koennen '\' stehen. Vergleiche _split_command() (Zeile 231), das korrekt 'posix=os.name != "nt"' nutzt - hier fehlt diese OS-Abfrage.

**Fix:** shlex.split(run_args, posix=os.name != "nt") verwenden, konsistent zu _split_command. Da die Platzhalterersetzung nach dem Split passiert, betrifft das primaer Backslashes im Template selbst; trotzdem sollte das Posix-Flag OS-abhaengig sein.

### [backend-chat/bug] backend/shared.py:29
**Race Condition: Pending-Confirmation-State ohne Lock zwischen nebenlaeufigen Chat-Requests**

set_pending_confirmation / get_pending_confirmation / clear_pending_confirmation mutieren globale Modulvariablen (_pending_confirmation, _pending_confirmation_ts) komplett ohne Lock. router_chat.py liest in chat_endpoint und chat_stream_endpoint zuerst get_pending_confirmation() und ruft danach clear_pending_confirmation()/_execute_pending_confirmation auf. Da FastAPI mehrere Requests nebenlaeufig bedient (und der eigentliche Aktions-Run via asyncio.to_thread laeuft), kann zwischen 'lesen' und 'clearen' ein zweiter 'Ja'-Request dieselbe Pending-Aktion erneut lesen und EIN ZWEITES MAL ausfuehren (Doppelausfuehrung einer bestaetigungspflichtigen Desktop-/Datei-Aktion). Umgekehrt kann ein paralleler neuer Chat die Pending-Confirmation ueberschreiben, sodass ein 'Ja' die falsche Aktion ausfuehrt.

**Fix:** Pending-Confirmation-Zugriff unter einem dedizierten threading.Lock kapseln und 'get + clear' als atomare pop-Operation anbieten (z.B. take_pending_confirmation()), die unter Lock den Wert zurueckgibt und gleichzeitig loescht. In router_chat.py statt get_pending_confirmation()+clear_pending_confirmation() diese atomare Funktion verwenden.

### [backend-tools-plugins/bug] backend/mcp_registry.py:432
**get_merged_tool_definitions ist toter Code — MCP-Tools erreichen den LLM nie**

get_merged_tool_definitions() ist die einzige Funktion, die MCP-Tools (get_all_mcp_tools) in die an den LLM gesendete Tool-Liste mischen würde. Eine projektweite Suche zeigt keinen einzigen Aufrufer: ai_engine.py ruft nur get_tools_for_context() aus tool_registry, und der Agent-Loop validiert jeden Tool-Call über validate_tool_arguments() (agent_loop.py:368), das für unbekannte Namen 'unknown tool' wirft. Folge: Verbundene MCP-Server werden zwar gestartet und ihre Tools entdeckt, aber das LLM bekommt sie nie als aufrufbare Tools angeboten und kann sie nicht nutzen — das gesamte MCP-Feature ist im normalen Chat/Agent-Flow funktionslos (nur über den manuellen REST-Endpoint /mcp/servers/{name}/call erreichbar).

**Fix:** Entweder get_merged_tool_definitions() im Tool-Aufbau von ai_engine.py (um Zeile 3823/3890) einhängen UND im Dispatch (agent_loop.py um Zeile 430) einen Zweig 'if action_name.startswith("mcp_")' ergänzen, der den Namen in Server+Tool zerlegt und mcp_registry.call_tool() aufruft; oder die ungenutzte Methode entfernen und im Code/Docs klarstellen, dass MCP rein REST-basiert ist.

### [backend-tools-plugins/bug] backend/plugin_manager.py:975
**Plugin-Tools (z.B. web_search) werden dem LLM nie angeboten und sind im Agent-Loop nicht ausführbar**

get_plugin_tools() wird ausschließlich vom REST-Endpoint /plugins/tools (router_plugins.py:66) konsumiert. Der Agent-Loop validiert Tool-Calls strikt gegen die statische tool_registry (agent_loop.py:368 -> validate_tool_arguments wirft 'unknown tool' für Plugin-Namen). Damit kann der LLM das mitgelieferte web_search-Plugin und jedes andere geladene Plugin im Chat nicht aufrufen — die Web-Suche funktioniert nur, wenn ein Client manuell POST /plugins/execute schickt. Für eine KI-Assistenten-App ist eine nicht vom Assistenten nutzbare Websuche ein kaputtes Kernfeature.

**Fix:** Plugin-Tools in den an den LLM übergebenen Tool-Satz mergen (analog zu get_tools_for_context) und im Dispatch vor dem 'unknown command'-Pfad einen Fallback ergänzen: wenn action_name in plugin_manager._tool_index liegt, await plugin_manager.execute_tool_by_name(action_name, params) aufrufen. validate_tool_arguments muss Plugin-Namen dann ebenfalls kennen oder übersprungen werden.

### [backend-security-main/bug] backend/shared.py:24
**Globaler Pending-Confirmation-State: ein einziger Slot, kein Lock, Race zwischen get/clear/execute**

Der Bestätigungs-State (_pending_confirmation) ist ein modulglobaler Einzel-Slot ohne Lock. set_pending_confirmation überschreibt jede vorherige offene Bestätigung kommentarlos — bei zwei kurz aufeinanderfolgenden bestätigungspflichtigen Aktionen bestätigt der Nutzer mit 'ja' faktisch die zuletzt gesetzte, nicht die gemeinte Aktion. Schwerwiegender: In router_chat (Zeile 1157-1163) wird get_pending_confirmation() gelesen, dann clear_pending_confirmation() aufgerufen und dann die Aktion ausgeführt — ohne Lock. Bei zwei parallelen Chat-Requests (FastAPI bedient nebenläufig) können beide dasselbe pending lesen, bevor einer clear aufruft, sodass eine bestätigungspflichtige Aktion doppelt ausgeführt wird (z.B. Datei zweimal löschen). Da TTL/Slot global sind, ist der State außerdem nicht pro Konversation/Nutzer isoliert.

**Fix:** State in ein threadsicheres/async-sicheres Konstrukt überführen: entweder eine atomare 'pop'-Operation (get+clear unter einem threading.Lock) bereitstellen und in router_chat statt get→clear nur diese eine atomare Funktion verwenden, oder den State pro Konversations-ID schlüsseln (dict mit Lock). Der execute-Pfad sollte das pending atomar konsumieren, nicht erst lesen und später löschen.

### [backend-personal-os/bug] backend/router_personal_os.py:248
**Falscher Personal-OS-Root-Fallback bricht alle Raw-Inbox-/Draft-/SDK-Endpoints**

_personal_os_root() prueft nur die Env-Var PERSONAL_OS_ROOT und faellt sonst auf Path(__file__).resolve().parents[3] / 'OS' zurueck. parents[3] ist 'C:/Users/admin/OneDrive - Office' -> der Fallback zeigt auf 'OneDrive - Office/OS', das nicht existiert (verifiziert). Die echten Worker-/SDK-Dateien liegen unter 'lexa-ai/personal_os/...'. PERSONAL_OS_ROOT ist nur in mcp_servers.json gesetzt (Wert: 'OneDrive - Office\\Desktop\\OS'), NICHT in der Prozess-Umgebung (verifiziert: printenv leer). Folge: _run_raw_inbox_worker, _run_raw_inbox_worker_status, _run_draft_decision_cli und _run_draft_apply_cli werfen 502 'worker/SDK not found', obwohl die MCP-Tools (ueber hermes_adapter._resolve_personal_os_root) korrekt funktionieren. Das ist inkonsistent zu hermes_adapter, das zuerst PROJECT_ROOT/'personal_os' prueft.

**Fix:** _personal_os_root() an die robuste Aufloesung in hermes_adapter._resolve_personal_os_root angleichen bzw. direkt importieren: zuerst LEXA_PERSONAL_OS_ROOT/PERSONAL_OS_ROOT, dann Path(__file__).resolve().parents[1] / 'personal_os' (== lexa-ai/personal_os, mit OS_MANIFEST.md-Pruefung), dann _mcp_personal_os_root_candidate(). Den Fallback auf parents[3]/'OS' entfernen.

### [backend-productivity/bug] backend/scheduler.py:173
**Scheduler schließt die thread-lokale Memory-DB-Verbindung**

`_run_routine`, `_scheduler_loop` und `get_scheduler_status` rufen `memory._get_db()` auf und schließen die Verbindung danach im finally-Block mit `db.close()` (Zeilen 173, 216, 265). `memory._get_db()` liefert aber eine bewusst thread-lokal gecachte Verbindung, die laut Doku NICHT geschlossen werden darf (memory.py Z.167: 'The connection is NOT closed — it persists in thread-local storage'). Nach dem Schließen bleibt im thread_local ein toter Handle; der nächste Aufruf erkennt das via `SELECT 1`-Healthcheck und baut die Verbindung neu auf. Folge: bei jedem Scheduler-Tick (alle 60s) wird die DB-Verbindung unnötig neu geöffnet, und falls anderer Code auf demselben Loop-Thread denselben Handle hält, kann ein 'Cannot operate on a closed database'-Fehler auftreten.

**Fix:** Die `db.close()`-Aufrufe in scheduler.py (finally-Blöcke in `_run_routine`, `_scheduler_loop`, `get_scheduler_status`) entfernen. Die thread-lokale Verbindung soll persistieren wie in productivity.py/reminders.py. Falls explizites Schließen gewünscht ist, `memory.close_db()` verwenden, das den thread_local korrekt zurücksetzt.

### [backend-voice-vision-stripe/security] backend/router_stripe.py:660
**Webhook gibt HTTP 200 zurueck, wenn Webhook-Secret nicht konfiguriert ist**

Wenn STRIPE_WEBHOOK_SECRET nicht gesetzt ist (Zeile 660-662), wird der Request mit Status 200 quittiert, ohne die Signatur zu pruefen. Stripe wertet 200 als erfolgreiche Zustellung und versucht keine Wiederholung. Faellt das Secret in Produktion versehentlich aus, gehen alle Abo-Events (Aktivierung, Kuendigung) still verloren, und die Subscription-DB driftet dauerhaft vom Stripe-Zustand ab — Nutzer zahlen, bekommen aber keinen Plan, oder behalten Zugriff nach Kuendigung.

**Fix:** Bei fehlendem Secret Status 500 (oder 503) zurueckgeben, damit Stripe die Zustellung erneut versucht, sobald das Secret wieder vorhanden ist. Zusaetzlich beim Start hart fail-en/warnen, wenn Stripe-Endpoints registriert sind aber kein Secret existiert.

### [backend-voice-vision-stripe/bug] backend/router_stripe.py:782
**_extract_plan_name faellt bei unbekanntem Plan auf 'pro' zurueck statt 'free'**

_extract_plan_name gibt bei jeder Exception und auch bei nicht erkanntem Label (weder 'ultra' noch 'pro' im Nicknamen/Produkt) hart 'pro' zurueck (Zeile 782). Wird der Plan-Nickname nicht gepflegt oder die Stripe-Struktur weicht ab, bekommt ein Nutzer faelschlich den 'pro'-Plan zugewiesen, obwohl er evtl. ein anderes/guenstigeres Produkt gekauft hat. Das ist eine Rechtevergabe auf Basis eines Fallbacks und kann zu unbezahlter Feature-Freischaltung fuehren.

**Fix:** Bei nicht eindeutig erkennbarem Plan auf 'free' (oder einen expliziten 'unknown'-Status) zurueckfallen und den Vorgang protokollieren/alarmieren, statt 'pro' zu vergeben. Die Plan-Erkennung sollte auf die price_id (req.price_id ist bereits allowlisted) statt auf freitext-Nicknames abgestellt werden.

### [companion-tools-1/bug] companion/file_tools.py:225
**batch_rename überschreibt vorhandene Dateien ohne Prüfung — Datenverlust**

In batch_rename wird new_path = filepath.parent / new_name berechnet und sofort filepath.rename(new_path) ausgeführt, ohne zu prüfen, ob new_path bereits existiert. Auf Windows/POSIX überschreibt Path.rename ein vorhandenes Ziel (POSIX) bzw. wirft auf Windows nur, wenn die Zieldatei existiert — aber bei Kollisionen innerhalb desselben Batch (z. B. pattern='foto_{n}' das mehrere Quelldateien auf identische Namen abbildet, oder prefix/suffix, die bestehende Dateinamen erzeugen) gehen Dateien verloren bzw. der Lauf bricht mitten im Batch mit einer Exception ab und hinterlässt einen inkonsistenten, teilweise umbenannten Ordner. Da die Funktion confirmation_required ist, erwartet der Nutzer kein stilles Überschreiben.

**Fix:** Vor dem Rename prüfen: if new_path.exists(): results.append({'old': old_name, 'skipped': new_name, 'reason': 'Ziel existiert bereits'}); continue. Zusätzlich die rename-Aufrufe in try/except OSError kapseln, damit ein einzelner Fehler den restlichen Batch nicht abbricht, und am Ende ein Gesamtergebnis (umbenannt/übersprungen/fehlgeschlagen) zurückgeben.

### [companion-tools-2/quality] companion/communication.py:477
**telegram_send/telegram_read/discord_send: requests-Exceptions unbehandelt → Crash statt Fehlermeldung**

telegram_send() (Zeile 477), telegram_read() (Zeile 534) und discord_send() (Zeile 594) rufen requests.post/get direkt auf, ohne requests.exceptions.RequestException (Timeout, ConnectionError, DNS-Fehler) abzufangen. Bei fehlender Internetverbindung oder Timeout wirft requests eine Exception, die bis in engine.execute() durchschlägt. Dort wird sie zwar generisch gefangen, aber die spezifischen, hilfreichen Fehlermeldungen (t('communication.telegramError')) greifen nie — der Nutzer bekommt eine generische Fehlermeldung statt eines klaren 'Telegram nicht erreichbar'.

**Fix:** requests-Aufrufe in try/except requests.exceptions.RequestException kapseln und eine verständliche deutsche Fehlermeldung über die jeweiligen i18n-Keys zurückgeben.

### [voice-pipeline/bug] voice/conversation.py:48
**_is_exit triggert Falsch-Beendigung der Konversation durch Substring-Matching**

_is_exit prueft `any(p in clean for p in EXIT_PHRASES)`. Da EXIT_PHRASES Kurzwoerter wie 'stop', 'halt', 'ende', 'bye', 'fertig' enthaelt, beendet jede Nutzeraeusserung, die eines dieser Tokens als Teilstring enthaelt, die gesamte Konversation. Beispiele: 'Halterung bestellen' -> 'halt', 'Endergebnis' -> 'ende', 'Goodbye-Nachricht' -> 'bye', 'fertiggestellt' -> 'fertig'. run_conversation ruft _is_exit auf das transkribierte Kommando auf (Zeile 388) und bricht ab. Echter Nutzer-Input wird so faelschlich als Abschiedsfloskel interpretiert.

**Fix:** Nur exakte Treffer oder wortgrenzen-basiertes Matching verwenden: `clean in EXIT_PHRASES` ODER pro Phrase mit Tokenisierung pruefen (z.B. `clean.split()` und exakter Tokenvergleich, bzw. `re.search(r'\b'+re.escape(p)+r'\b', clean)` nur fuer mehrwoertige Phrasen). Kurze Single-Token-Phrasen sollten nur als ganze Aeusserung (clean == p) zaehlen.

### [frontend-chat-core/bug] frontend/src/chat.js:1526
**Leaked 45s-Timeout fuehrt zu uncaught TypeError (null.abort())**

In sendMessage wird _streamTimeout (setTimeout, 45s) im try-Block (Z.1526) angelegt und nur in den Pfaden response.ok-Fehler (Z.1557), AbortError (Z.1540) und Erfolg (Z.1640) per clearTimeout geleert. Im aeusseren catch(err) (Z.1702) fehlt das clearTimeout, und _streamTimeout ist dort ausserdem ausserhalb des Scopes. Wenn nach dem Setzen des Timers eine Exception fliegt (z.B. response.body ist null -> response.body.getReader() in Z.1582 wirft), laeuft der Timer weiter. Die Funktion setzt am Ende window._lexaStreamAbort = null (Z.1721). Feuert der verwaiste Timer danach, ruft die Callback window._lexaStreamAbort.abort() (Z.1528) auf null auf -> unbehandelter TypeError im Renderer, ca. 45s nach dem eigentlichen Fehler.

**Fix:** Den Timeout in einem finally-Block der gesamten Stream-Sektion leeren (clearTimeout(_streamTimeout)) oder die Variable vor dem try deklarieren und im catch(err) sowie am Funktionsende clearen. Zusaetzlich in der Timer-Callback defensiv pruefen: if (window._lexaStreamAbort) window._lexaStreamAbort.abort();

### [frontend-views/bug] frontend/src/memory.js:815
**Gesamte Memory-View-Logik ist toter, unerreichbarer Code nach frühem return**

refreshMemoryView() ruft in Zeile 815 'await refreshMemoryGraphView();' und sofort 'return;' (Zeile 816) auf. Der komplette restliche Funktionsrumpf (Zeilen 818–1004: Stats-Grid, Notizen-Liste, Snippets-Liste, AI-Status-Panel, Routinen-Liste, Clipboard-Privacy-Prompt, Cleanup-Button) wird nie ausgeführt. Die dort referenzierten DOM-IDs (memory-stats-grid, notes-list, snippets-list, ai-status-panel, routines-list, clipboard-history-list, memory-cleanup-info) existieren auch nicht mehr in index.html (per Grep verifiziert). Dadurch sind Notizen, Snippets, Routinen, Clipboard-Historie und Memory-Stats in der Memory-Ansicht faktisch verschwunden — nur noch der Graph wird angezeigt.

**Fix:** Entscheiden, ob die Memory-View graph-only sein soll: Falls ja, den toten Code (Zeilen 817–1004) entfernen und die nur dort genutzten Funktionen (renderClipboardEntries, renderClipboardPrivacyPrompt) bereinigen. Falls die Panels weiterhin gewünscht sind, das frühe 'return;' entfernen und die fehlenden DOM-Container in index.html wieder einfügen.

### [frontend-views/bug] frontend/src/memory.js:1074
**Verwaiste Feature-Funktionen createNote/createSnippet/createRoutine/showDiagnostics/clearClipboardHistory nicht mehr aufrufbar**

createNote (1074), createSnippet (1279), createRoutine (1145), showDiagnostics (1381) und clearClipboardHistory (1068) werden weder per data-action in app_actions.js dispatcht noch in index.html referenziert (per Grep verifiziert; nur runMemoryCleanup ist über index.html Zeile 1236 verdrahtet). Damit sind die UI-Pfade zum Anlegen von Notizen/Snippets/Routinen, zum Anzeigen von Diagnostics und zum Leeren der Clipboard-Historie aus der App nicht mehr erreichbar — die Features existieren im Code, sind aber tot.

**Fix:** Entweder die zugehörigen Buttons/Actions in der Memory-View-HTML + app_actions.js wieder einhängen, oder die Funktionen entfernen. quickCreateNote bleibt über den Shortcut (app_desktop_shortcuts.js:154) erreichbar, createNote als Wrapper ist redundant.

### [electron-shell/bug] frontend/main.js:1436
**app.whenReady().then() ohne .catch() — unbehandelte Promise-Rejection beim Start**

Die gesamte Startsequenz läuft in einem async-Callback (Zeilen 1436-1461), der u.a. installLocalAuthCookie() (await, Zeile 1446) und startBackend() (await, Zeile 1452) ausführt. Es gibt kein .catch(). Wirft cookies.set() (z.B. weil session/Profil noch nicht bereit ist), isPortInUse, oder ein anderer Schritt eine Exception, wird die Rejection nicht abgefangen: createWindow() (Zeile 1454) und createTray() werden nie erreicht, und der Nutzer sieht eine laufende Electron-App ohne Fenster und ohne Fehlermeldung. Tritt bei jedem Fehler in der Init-Kette auf.

**Fix:** Den .then()-Block mit .catch((err) => { console.error('[App] Startup failed:', err); ... ggf. createWindow() trotzdem + Fehlerbanner }) absichern, oder die einzelnen kritischen Schritte (installLocalAuthCookie, startBackend) in try/catch kapseln, sodass das Fenster auch bei Backend-/Cookie-Fehlern erstellt wird (der Renderer hat bereits Offline-Fallbacks).

### [electron-shell/security] frontend/main.js:1262
**Presence-/Confirmation-Gate ist kein echtes User-Presence-Gate (Defense-in-Depth-Lücke)**

Für high/critical-Bridge-Methoden (execute, executeBatch, backupRestore, personalOsDraftApply, mcpCallTool, agentRun, licenseActivate u.v.m.) erzwingt preload.js eine 'presence challenge'. Der Main-Handler bridge:presence:request (Zeile 1262) stellt jedem vertrauenswürdigen Renderer automatisch eine Challenge aus (Audit-Grund 'trusted_renderer_auto_challenge', Zeile 1284), und bridge:presence:consume validiert sie nur. Es gibt im Main-Prozess KEINE dialog.showMessageBox-Bestätigung (verifiziert: kein Treffer). Damit ist die requires_main_confirmation/requires_user_presence-Garantie effektiv ein No-Op: Code, der im vertrauenswürdigen Renderer läuft (z.B. via XSS in chat-gerendertem Inhalt), passiert das Gate automatisch und kann kritische lokale Aktionen auslösen. Das System liefert nur Audit-Logging + Replay-Schutz, aber keinen Schutz gegen einen kompromittierten Renderer — genau das Bedrohungsmodell, für das ein Presence-Gate existieren soll.

**Fix:** Für tatsächlich gefährliche Methoden (execute, backupRestore, personalOsDraftApply, mcpCallTool) im Main-Prozess eine echte native Bestätigung via dialog.showMessageBox vor Ausstellung/Konsum der Challenge einbauen, oder die Methode klar als reines Audit-Feature dokumentieren und die kritische Bestätigung auf eine Out-of-Renderer-Oberfläche (Tray-Menü/separates Fenster) verlagern.

### [evals/security] evals/runners/run_manual_prompt_probe.py:458
**Manuelle Prompt-Probe schreibt Modell-Antworten und Prompts unredigiert auf die Platte**

write_reports() serialisiert in json_payload['results'] jede ProbeResult inkl. der vollstaendigen, ungefilterten Felder 'reply' und 'prompt' (asdict(result)) und schreibt sie via json.dumps(..., ensure_ascii=False) nach evals/results/<run_id>.json. Im Gegensatz zu ALLEN anderen Runnern (check_eval_regressions, eval_trend_report, policy_dashboard, update_eval_baseline, write_failure_triage) gibt es hier keinen einzigen redact_secrets()- oder has_secret()-Aufruf. Sobald die Probe mit --allow-model / --allow-vision gegen die echten Provider laeuft, landen reale Modell-Ausgaben (die laut score_reply selbst Secrets, lokale Pfade oder Stacktraces enthalten koennen) sowie die Roh-Prompts dauerhaft im Report. score_reply prueft zwar auf Leaks, redigiert die gespeicherte Antwort aber nicht.

**Fix:** Vor dem Schreiben redact_secrets() auf reply/prompt (bzw. das gesamte json_payload) anwenden und analog zu den anderen Runnern ein has_secret()-Gate vor write_text() setzen. Auch _safe_reply_excerpt() in der Markdown-Ausgabe sollte vorab redigieren.

### [frontend-css/bug] frontend/src/css/views_dashboard.css:169
**Dashboard-Systembalken (CPU/RAM/Disk/Akku) bleiben immer auf 0 % Breite**

Die Fortschrittsbalken im Dashboard (#dash-cpu-bar usw.) haben im HTML die Klassen 'dash-stat-bar-fill bar-initial'. dashboard.js (applyMeterClass, Z. 453-456) fügt zur Laufzeit eine Klasse 'meter-width-X' hinzu, entfernt aber NUR Klassen die mit 'meter-width-'/'meter-' beginnen — 'bar-initial' bleibt erhalten. Die Breite wird über drei gleich spezifische Selektoren (je 0,1,0) gesetzt: '.meter-width-X { width:X% }' in views.css (im HTML zuerst eingebunden), '.dash-stat-bar-fill { width:0% }' in views_dashboard.css (später eingebunden) und '.bar-initial { width:0% }' in overrides_responsive_utilities.css (zuletzt eingebunden). Bei gleicher Spezifität gewinnt die zuletzt geladene Regel — also 0 %. Ergebnis: Die Dashboard-Auslastungsbalken zeigen unabhängig von den echten Werten dauerhaft 0 % Füllung. Die System-View-Balken (system.js, '.info-card-bar' ohne konkurrierende width-Regel und ohne bar-initial) sind nicht betroffen.

**Fix:** Entweder in dashboard.js die Klasse 'bar-initial' beim ersten Setzen entfernen (el.classList.remove('bar-initial')) UND die '.dash-stat-bar-fill { width: 0% }'-Default-Breite aus views_dashboard.css entfernen, oder den '.meter-width-*'-Regeln höhere Spezifität/!important geben (z. B. '.dash-stat-bar-fill.meter-width-50 { width:50% }'). Sauberste Lösung: 'width:0%' aus '.dash-stat-bar-fill' streichen und 'bar-initial' nur als initiale Klasse vor dem ersten JS-Update nutzen, dann entfernen.

### [static-checks/bug] app_cache.json:1
**Ungültiges JSON: überzähliges schließendes "}" am Dateiende**

Die Datei app_cache.json ist kein gültiges JSON. Der JSON-Parser meldet "Extra data: line 1 column 28114 (char 28113)". Das gültige JSON-Objekt endet bei Zeichen 28113, danach folgt ein zusätzliches schließendes "}". Die Datei enthält 358 schließende, aber nur 357 öffnende geschweifte Klammern. Die Datei endet mit "...336218}}", wobei die zweite "}" überzählig ist. Beim Laden des App-Caches führt dies zu einem Parse-Fehler.

**Fix:** Das überzählige schließende "}" am Dateiende entfernen, sodass die Datei mit einem einzelnen "}" abschließt (z.B. "...336218}"). Nach Entfernen des letzten Zeichens ist die Datei valides JSON. Falls der Cache automatisch erzeugt wird, sollte die schreibende Stelle geprüft werden, die das doppelte "}" erzeugt.

## MEDIUM — verifiziert (11)

### [static-checks/bug] requirements.txt
**Fehlendes Paket: PyYAML (Import "yaml") nicht in requirements.txt**

Der Top-Level-Import "import yaml" wird im Backend verwendet (backend/plugin_manager.py:718 für YAML-Plugins und backend/hermes_adapter.py:670 zum Laden der Hermes-Config), ist aber weder in der Python-Stdlib enthalten noch in requirements.txt (oder requirements-dev.txt) deklariert. Beide Stellen sind zwar mit try/except gegen ImportError abgesichert (Feature wird dann deaktiviert), das benötigte Paket fehlt jedoch in den pinned Dependencies. Im aktuellen venv ist es nur transitiv vorhanden; für reproduzierbare Builds ist das nicht zuverlässig.

**Fix:** PyYAML in requirements.txt aufnehmen, z.B. "PyYAML==<version>" (Import-Name yaml, PyPI-Paket PyYAML). Die im venv installierte Version per "pip show pyyaml" ermitteln und pinnen.

### [static-checks/bug] requirements.txt
**Fehlendes Paket: dateparser nicht in requirements.txt**

Der Top-Level-Import "import dateparser" wird in backend/reminders.py:100 zur Verarbeitung natürlichsprachlicher Zeitangaben verwendet, ist aber nicht in der Python-Stdlib und fehlt in requirements.txt (und requirements-dev.txt). Der Import ist mit try/except abgesichert (Fallback bei Fehler), das Paket selbst ist jedoch nicht in den pinned Dependencies deklariert und nur transitiv im venv vorhanden, was für reproduzierbare Builds unzuverlässig ist.

**Fix:** dateparser in requirements.txt aufnehmen, z.B. "dateparser==<version>". Die im venv installierte Version per "pip show dateparser" ermitteln und pinnen.

### [test-health/bug] tests/test_ai_engine.py:1776
**test_set_ai_model_accepts_provider_prefixed_ids schlaegt fehl: openai-Modell unbekannt**

Test erwartet 'OpenAI' im Ergebnis von set_ai_model('openai:gpt-4o'). Tatsaechlich liefert die Funktion 'Unbekanntes Modell: openai:gpt-4o'. Das AI_MODEL_REGISTRY enthaelt nur noch Gemini-Modelle (gemini-3.5-flash, gemini-3.1-flash-lite, gemini-3.1-pro), keine OpenAI-Eintraege mehr.

**Fix:** Test an die aktuelle Gemini-only-Provider-Liste anpassen ODER OpenAI im AI_MODEL_REGISTRY wieder registrieren. Klaeren, ob der Provider-Wechsel beabsichtigt war.

### [test-health/bug] tests/test_ai_engine.py:1789
**test_set_ai_model_accepts_legacy_groq_ids schlaegt fehl: Groq-Modell nicht gesetzt**

Test erwartet current['current'] == 'groq:llama-3.1-8b-instant', tatsaechlich ist es 'gemini:gemini-3.5-flash'. Legacy-Groq-IDs werden nicht mehr aufgeloest, da Groq nicht mehr im AI_MODEL_REGISTRY steht.

**Fix:** Test an Gemini-only-Registry anpassen oder Groq-Legacy-Mapping im ai_engine wiederherstellen.

### [test-health/bug] tests/test_ai_engine.py:1801
**test_set_ai_model_accepts_anthropic_ids schlaegt fehl: Anthropic-Modell unbekannt**

Test erwartet 'Claude' im Ergebnis von set_ai_model('anthropic:claude-sonnet-4-20250514'). Tatsaechlich liefert die Funktion 'Unbekanntes Modell: anthropic:claude-sonnet-4-20250514'. Anthropic ist nicht mehr im AI_MODEL_REGISTRY registriert.

**Fix:** Test an Gemini-only-Registry anpassen oder Anthropic-Modelle im ai_engine wieder registrieren.

### [test-health/bug] tests/test_ai_engine.py:1814
**test_get_ai_models_returns_grouped_provider_data schlaegt fehl: kein openai-Block**

Test erwartet 'openai' in models['grouped']. Tatsaechlich enthaelt grouped nur den Schluessel 'gemini' (Modelle gemini-3.5-flash, gemini-3.1-flash-lite, gemini-3.1-pro). Die gruppierten Provider-Daten liefern nur noch Gemini.

**Fix:** Test an die aktuelle Gemini-only-Gruppierung anpassen oder weitere Provider im Registry ergaenzen.

### [test-health/bug] tests/test_ai_engine.py:1874
**test_get_ai_status_reports_all_providers schlaegt fehl: KeyError 'groq'**

Test ruft status['groq']['available'] auf, aber der von get_ai_status zurueckgegebene Dict enthaelt keinen Schluessel 'groq' mehr. Der Statusbericht meldet nicht mehr alle frueheren Provider.

**Fix:** Test an die aktuelle Provider-Statusstruktur (Gemini-only) anpassen oder Groq-Status wieder bereitstellen.

### [test-health/bug] tests/test_ai_engine.py:1907
**test_chat_fallback_tries_configured_provider_after_selected_failure schlaegt fehl: KeyError im Registry**

Test greift auf ai_engine.AI_MODEL_REGISTRY['gemini:gemini-2.5-flash'] zu, dieser Schluessel existiert nicht. Das Registry enthaelt nur gemini-3.5-flash, gemini-3.1-flash-lite, gemini-3.1-pro (kein 2.5-flash).

**Fix:** Test-Modell-ID auf einen tatsaechlich registrierten Schluessel (z.B. gemini:gemini-3.5-flash) aktualisieren.

### [test-health/bug] tests/test_ai_engine.py:1931
**test_stream_fallback_returns_first_configured_stream schlaegt fehl: KeyError im Registry**

Test greift auf ai_engine.AI_MODEL_REGISTRY['gemini:gemini-2.5-flash'] zu; dieser Schluessel ist im aktuellen Gemini-only-Registry nicht vorhanden.

**Fix:** Test-Modell-ID auf einen registrierten Schluessel aktualisieren (z.B. gemini:gemini-3.5-flash).

### [test-health/bug] tests/test_ai_engine.py:1953
**test_chat_stream_falls_back_after_empty_primary_stream schlaegt fehl: KeyError im Registry**

Test greift auf ai_engine.AI_MODEL_REGISTRY['gemini:gemini-2.5-flash'] zu; dieser Schluessel existiert nicht mehr im Registry.

**Fix:** Test-Modell-ID auf einen registrierten Schluessel aktualisieren (z.B. gemini:gemini-3.5-flash).

### [test-health/bug] tests/test_ai_engine.py:2004
**test_chat_stream_accepts_tool_delta_without_function_payload schlaegt fehl: KeyError im Registry**

Test greift auf ai_engine.AI_MODEL_REGISTRY['groq:llama-3.3-70b-versatile'] zu; Groq ist nicht mehr im Registry vorhanden.

**Fix:** Test-Modell-ID auf einen registrierten Gemini-Schluessel aktualisieren oder Groq im Registry wiederherstellen.

## VERBESSERUNGEN (improvement) — 65

### [backend-agent-core/improvement] backend/agent_reflection.py:191
**createReviewDraft-Pruefung greift nur fuer exakt diesen Key — verwandte Draft-Flags werden nicht erfasst**
**Fix:** Auf mehrere Schreibweisen/Truthy-Werte pruefen (z.B. str(value).lower() in {'1','true','yes'}) und auch verwandte Keys (create_review_draft, applyDraft, approveDraft) beruecksichtigen, damit Draft-erzeugende Writes zuverlaessig als high eingestuft werden.

### [backend-agent-core/improvement] backend/agent_trace_sampling.py:79
**Trace-Sampling nutzt nicht-kryptografisches, nicht reproduzierbares random ohne Seed-Kontrolle**
**Fix:** Eine eigene random.Random-Instanz mit optional konfigurierbarem Seed (z.B. LEXA_AGENT_TRACE_SEED) verwenden, damit Sampling-Entscheidungen fuer Eval-Laeufe reproduzierbar und vom globalen RNG entkoppelt sind.

### [backend-agent-core/improvement] backend/agent_loop.py:351
**Doppelte Schema-Validierung im Executor- vs. Agent-Pfad mit unterschiedlichem Verhalten**
**Fix:** Validierung in einer gemeinsamen Funktion zentralisieren, die von action_executor UND agent_loop genutzt wird, und _scan_params_for_dangerous_output auch im Agent-Tool-Pfad anwenden, damit gefaehrliche Shell-Muster in LLM-Argumenten konsistent blockiert werden.

### [backend-agent-core/improvement] backend/agent_reflection.py:25
**Sensitive-Key-Regex markiert generische Schluessel wie 'path' und 'file' als sensibel — verrauschte Audit-/Reflexionssignale**
**Fix:** 'path'/'file' aus der Sensitive-Key-Heuristik entfernen (Pfade sind kein Secret) oder in eine separate, niedriger gewichtete Kategorie verschieben, sodass nur echte Credential-artige Keys (api_key, token, secret, password, authorization) die Sensitiv-Concern ausloesen.

### [backend-ai-engine/improvement] backend/ai_engine.py:80
**Toter Provider-Code: Groq/OpenAI/Anthropic-Clients und -Routing sind unerreichbar**
**Fix:** Ungenutzte Provider-Gerüste entfernen oder klar als Legacy in ein separates Modul auslagern. Wenn Multi-Provider als zukünftige Option erhalten bleiben soll, mit einem deutlichen Kommentar 'derzeit inaktiv (Gemini-only)' markieren und durch Tests vor versehentlicher Nutzung schützen.

### [backend-ai-engine/improvement] backend/ai_engine.py:1
**Veralteter Modul-Docstring beschreibt Multi-Provider-Setup (Groq/OpenAI/Claude)**
**Fix:** Docstring auf den tatsächlichen Stand aktualisieren (Gemini-only: gemini-3.5-flash / 3.1-flash-lite / 3.1-pro, native function calling via OpenAI-kompatibler Schnittstelle). Optional Hinweis, dass die Multi-Provider-Gerüste nur noch als Legacy/Reserve existieren.

### [backend-hermes/improvement] backend/router_hermes.py:200
**_open_tasks_from_text dupliziert Logik der Plugin-Implementierung (Divergenzgefahr)**
**Fix:** Die Task-Parsing- und Auswahl-Logik in eine gemeinsame Hilfsfunktion (z.B. in hermes_adapter oder einem util-Modul) extrahieren und sowohl im Router als auch im Plugin importieren/aufrufen, damit App und Telegram dieselbe naechste Aktion zeigen.

### [backend-hermes/improvement] backend/router_hermes.py:233
**_safe_to_thread maskiert nicht-dict-Resultate still ohne Log**
**Fix:** Bei nicht-dict-Resultat zumindest loggen (logger.warning mit fn-Name), damit stille Vertragsverletzungen sichtbar werden; optional **kwargs-Durchreichung ergaenzen, um die Sonderbehandlung von build_obsidian_context_payload zu vereinheitlichen.

### [backend-hermes/improvement] backend/hermes_adapter.py:2454
**configure_hermes_telegram validiert home_channel inhaltlich kaum**
**Fix:** home_channel gegen ein erwartetes Muster validieren (z.B. ^-?\d{5,}$ fuer numerische IDs oder ^@[A-Za-z0-9_]{4,}$ fuer Usernames) und bei Verstoss eine klare Fehlermeldung wie bei invalid_token_format zurueckgeben, bevor in die .env geschrieben wird.

### [backend-intent/improvement] backend/i18n/__init__.py:34
**init() laedt nur hartkodierte Locales 'de'/'en' — inkonsistenter Zustand bei anderer Sprache**
**Fix:** In init() die uebergebene lang in die zu ladende Locale-Liste aufnehmen (z.B. sorted(set(['de','en', lang]))) und _lang nur setzen, wenn die Datei erfolgreich geladen wurde; andernfalls bei 'de' bleiben und warnen.

### [backend-intent/improvement] backend/i18n/__init__.py:48
**t() laesst nicht ersetzte {{platzhalter}} im Text stehen**
**Fix:** Nach der Ersetzung verbleibende '{{...}}'-Vorkommen erkennen und entweder per _log.warning melden oder auf einen leeren String reduzieren, damit defekte Platzhalter nicht in der UI erscheinen.

### [backend-intent/improvement] backend/intent_engine.py:932
**Mehrsatz-Filter laeuft erst nach den Smart-Intents — lange Saetze koennen Aktionen ausloesen**
**Fix:** Den Mehrsatz-/Mehrfachfrage-Filter vor _try_smart_intent ausfuehren (oder zumindest vor den fuzzy App-/Such-Heuristiken), damit klar konversationelle Eingaben nicht von der Schnellpfad-Heuristik abgefangen werden.

### [backend-intent/improvement] backend/router_smart.py:63
**DELETE /profile/{key:path} ohne Laengen-/Inhaltsvalidierung des Keys**
**Fix:** Auch in delete_profile_entry die Key-Laenge (max 200) und ein konsistentes Zeichenmuster pruefen, analog zu update_profile, bevor sm.profile_delete aufgerufen wird.

### [backend-memory/improvement] backend/router_memory.py:144
**set_profile-Endpoint serialisiert value als Roh-String, smart_memory als JSON — inkonsistentes Format**
**Fix:** Profil-Zugriff auf EIN Modul/Format konsolidieren (durchgehend JSON via smart_memory oder durchgehend Roh-Strings via memory) und den Router entsprechend nur ein Modul aufrufen lassen.

### [backend-memory/improvement] backend/embeddings.py:94
**_active_provider wird gecacht und ignoriert spätere API-Key-Hinterlegung**
**Fix:** reset_provider() automatisch aufrufen, wenn der Nutzer in den Einstellungen einen OpenAI/Embedding-Key ändert, oder den Provider mit kurzer TTL statt prozessweit cachen.

### [backend-memory/improvement] backend/memory.py:304
**note_create kappt Titel/Content nicht — inkonsistent mit note_update_by_id**
**Fix:** In note_create dieselben Caps anwenden wie in note_update_by_id bzw. die Konstanten MAX_NOTE_TITLE/MAX_NOTE_CONTENT/MAX_NOTE_CATEGORY aus config.py verwenden.

### [backend-memory/improvement] backend/memory_core/ranking.py:83
**Recency-Score nutzt naive datetime.now() gegen localtime-Strings ohne TZ-Konsistenzgarantie**
**Fix:** Zeitstempel konsequent in UTC (datetime('now')) speichern und beim Ranking mit datetime.utcnow() vergleichen, oder TZ-bewusste Vergleiche verwenden.

### [backend-memory/improvement] backend/memory.py:1829
**clipboard_add: Duplikat-Erkennung case-/whitespace-sensitiv**
**Fix:** Text vor dem Vergleich normalisieren (strip) und den normalisierten Wert speichern, bzw. den DELETE über TRIM(text)=TRIM(?) ausführen.

### [backend-memory/improvement] backend/memory.py:119
**_finalize_memory_results trackt Zugriff auch bei reinen Such-/Listen-Operationen**
**Fix:** track_access für Listen-/Such-Übersichten (global_search, full_text_search, memory_graph) auf False setzen und nur beim tatsächlichen Abruf einer Memory bzw. bei der Kontext-Injektion in den Chat tracken.

### [backend-personal-os/improvement] backend/personal_os_actions.py:125
**Verbesserung: _resolve_draft_path ist N+1-anfaellig, listet bis 200 Drafts pro Aufruf**
**Fix:** Optionales kurzlebiges Caching der os_list_drafts-Ergebnisse pro (approval, hideSmoke)-Schluessel im Action-Layer, oder die aufgeloeste draftPath im Tool-Resultat zurueckgeben, damit Folgeaktionen direkt draftPath statt query nutzen koennen.

### [backend-personal-os/improvement] backend/router_personal_os.py:1442
**Verbesserung: maxFiles-Obergrenzen zwischen Endpoint und Action-Layer inkonsistent**
**Fix:** Limits zentral definieren (z.B. Konstanten MAX_GRAPH_FILES, MAX_QUERY_MATCHES in einem Modul) und in beiden Pfaden (Endpoint-Query-Validierung und Action-Layer _as_int) referenzieren, damit REST und Chat denselben Vertrag haben.

### [backend-personal-os/improvement] backend/obsidian_context.py:365
**Verbesserung: _priority_context_paths triggert nur bei Treffer in fixer Wortliste**
**Fix:** Priority-Terme erweitern bzw. um deutsche Synonyme ergaenzen, oder die Priorisierung statt exaktem Set-Match ueber den Score-Mechanismus (_score_path gegen die Priority-Dateien) laufen lassen, sodass auch teilweise/semantisch nahe Topics die High-Signal-Seiten einsammeln.

### [backend-personal-os/improvement] backend/router_os_agents.py:53
**Verbesserung: GET /os/tasks/{id} gibt vollstaendiges Task-JSON inkl. evidence/result ungefiltert zurueck**
**Fix:** Eine kompakte Antwortform fuer die API definieren (z.B. result einmalig, evidence ohne erneut eingebettete grosse data-Bloecke bzw. data auf kurze Previews kappen) und das vollstaendige JSON nur fuer einen expliziten Debug-/Export-Pfad ausliefern.

### [backend-personal-os/improvement] backend/os_agent_runtime.py:233
**Task-Pruning/Listing sortiert nach Dateiname ohne Praefix-Validierung**
**Fix:** Beim Globben auf das Praefix-Schema filtern (z.B. TASK_STORE_ROOT.glob('osagt_*.json')) und/oder als Tiebreaker mtime nutzen, damit Fremddateien das Pruning/Listing nicht verfaelschen.

### [backend-productivity/improvement] backend/proactive.py:263
**Cooldown-Dedup pro Typ unterdrückt mehrere Kalender-Erinnerungen**
**Fix:** Für event-spezifische Typen wie calendar_reminder den Cooldown pro Event-ID statt pro Typ führen, oder den Dedup-Key um eine ID erweitern. `_reminded_events` verhindert Wiederholung desselben Events bereits — der Typ-Cooldown sollte calendar_reminder daher ausnehmen.

### [backend-productivity/improvement] backend/reminders.py:401
**Verpasste wiederkehrende Erinnerungen feuern nur einmal trotz mehrerer übersprungener Intervalle**
**Fix:** Beim Feuern eines wiederkehrenden Reminders melden, wie viele Intervalle übersprungen wurden, oder die Nachricht um einen Hinweis 'X verpasste Erinnerungen' ergänzen. Mindestens dokumentieren, dass verpasste Intervalle zusammengefasst werden.

### [backend-productivity/improvement] backend/workflows.py:1236
**get_status ohne Index auf workflow_logs.finished_at + unbegrenztes Log-Wachstum**
**Fix:** Index auf `workflow_logs(finished_at)` ergänzen und eine Retention für `workflow_logs` einführen (z.B. nur die letzten N Einträge pro Workflow behalten), damit Logs nicht unbegrenzt wachsen.

### [backend-security-main/improvement] backend/main.py:718
**/ai/title validiert message nicht auf Leerstring und wendet sanitize_input nicht an vor teurem AI-Call**
**Fix:** Vor dem AI-Call req.message trimmen und bei leerem/zu kurzem Inhalt sofort einen lokalen Fallback-Titel ('Neue Unterhaltung') ohne Provider-Call zurückgeben; optional sanitize_input anwenden, um Konsistenz mit dem Chat-Pfad herzustellen.

### [backend-security-main/improvement] backend/security.py:695
**audit_log loggt die fertige Audit-Zeile zusätzlich über den Standard-Logger — zweite Senke ohne Rotation**
**Fix:** Den zusätzlichen logger.info-Aufruf entweder entfernen oder auf logger.debug herabstufen und an einen dedizierten, nicht an stdout gehängten Audit-Logger binden, damit Audit-Daten nicht ungewollt im allgemeinen Log mit abweichender Rotation landen.

### [backend-tools-plugins/improvement] backend/plugin_loader.py:116
**Legacy-Plugin-Loader ist standardmäßig deaktiviert, bleibt aber komplett im Code**
**Fix:** Legacy-Loader als deprecated markieren und mittelfristig entfernen oder klar in einen optionalen Kompatibilitätspfad auslagern; in der Doku eindeutig auf plugin_manager als kanonisches System verweisen.

### [backend-voice-vision-stripe/improvement] backend/router_voice.py:65
**Hartkodierter Default-Sensitivity-Wert 0.015 mehrfach dupliziert**
**Fix:** Den Default als eine Konstante (z.B. in voice/config.py WAKE_DEFAULT_SENSITIVITY) definieren und ueberall importieren/referenzieren statt das Literal zu wiederholen.

### [backend-voice-vision-stripe/improvement] backend/router_stripe.py:878
**License-Validierung behandelt 'past_due'/'unpaid' wie inaktiv ohne differenzierte Rueckmeldung**
**Fix:** Den status differenziert zurueckmelden (z.B. reason='payment_failed' bei past_due/unpaid) und entscheiden, ob past_due eine kurze Kulanzperiode erhalten soll. Das verbessert die UX und reduziert Support-Faelle bei kurzfristigen Zahlungsproblemen.

### [backend-voice-vision-stripe/improvement] backend/router_companion.py:269
**/companion/plugins gibt internes _loaded_plugins-Dict direkt nach aussen**
**Fix:** Eine explizite, stabile Projektion zurueckgeben (z.B. nur Plugin-Namen und zugehoerige Commands ueber eine oeffentliche Methode der CompanionEngine), statt das private Attribut durchzureichen.

### [backend-voice-vision-stripe/improvement] backend/router_voice.py:656
**TTS-Endpoint prueft Rate-Limit erst nach Textlaengen-Validierung — Inkonsistenz**
**Fix:** check_rate_limit('voice') an den Anfang des Handlers ziehen (vor die Inhaltsvalidierung), konsistent zu den uebrigen Voice-/Vision-Endpoints.

### [companion-core/improvement] companion/desktop_control.py:452
**desktop_scroll ignoriert das Zielfenster vollstaendig und scrollt am Cursor**
**Fix:** desktop_scroll einen optionalen window-Parameter geben, der vor dem Wheel-Event den Cursor ueber das Zielfenster zentriert (Logik aus _center_cursor_on_window wiederverwenden), oder zumindest in der Befehlsbeschreibung klarstellen, dass am Cursor gescrollt wird.

### [companion-tools-1/improvement] companion/file_tools.py:274
**merge_pdfs nutzt das deprecte pypdf.PdfMerger**
**Fix:** Auf PdfWriter umstellen: writer = PdfWriter(); for path in pdf_paths: writer.append(path); writer.write(output_path). Zusätzlich den Import in try/except ImportError kapseln und eine verständliche 'pypdf nicht installiert'-Meldung zurückgeben, konsistent mit image_*-Funktionen.

### [companion-tools-1/improvement] companion/browser.py:345
**_get_browser startet Chromium mit headless=False — sichtbares Fenster bei jedem Browser-Tool**
**Fix:** headless als Parameter durch _get_browser(headless: bool) reichen oder zwei Kontexte/Instanzen verwenden: sichtbar für open_url/play_youtube, headless=True für scrape_text/check_price/website_screenshot/website_to_pdf.

### [companion-tools-2/improvement] companion/system_tools.py:30
**_sanitize_ps_arg ist nur für double-quoted Kontext sicher — fehlende Kontext-Kennzeichnung lädt zu Fehlanwendung ein**
**Fix:** Entweder eine zweite Funktion _sanitize_ps_arg_single() (verdoppelt einfache Anführungszeichen) bereitstellen oder das Escaping so erweitern, dass das Resultat in BEIDEN Kontexten sicher ist, und im Docstring + an jeder Aufrufstelle den erwarteten Quote-Kontext dokumentieren.

### [electron-shell/improvement] frontend/src/orb3d.js:14
**Toter Code in LexaOrb3D: konfigurierbare detail-Option und glowTexture werden ignoriert**
**Fix:** Entweder die detail-Option respektieren oder aus dem Options-Objekt entfernen; den toten glowTexture-Zweig in destroy() löschen; die shininess-/Light-/Normal-Updates für die dauerhaft unsichtbaren core/glassShell-Meshes aus der Animationsschleife entfernen, um pro Frame CPU zu sparen.

### [electron-shell/improvement] frontend/src/index.html:580
**Hartkodierte Statistik 'Befehle bereit' / Versions-Strings im Markup driften von der Realität**
**Fix:** Diese Felder beim Init verlässlich aus den Live-Quellen befüllen (commands().total für die Befehlsanzahl, health().version bzw. package.json für die Version) und die Default-Texte auf neutrale Platzhalter ('—') setzen, damit nie eine falsche Zahl angezeigt wird.

### [electron-shell/improvement] frontend/src/index.html:564
**Orb-Button (role=button) hat keinen sichtbaren Textinhalt — Tastatur-/Screenreader-Bedienbarkeit prüfen**
**Fix:** Sicherstellen, dass die _dispatch-Delegation keydown (Enter/Space) für [role=button][data-action] verarbeitet, und aria-pressed der Orb bei Start/Stop der Konversation synchron aktualisieren; alternativ ein echtes <button> als Wrapper verwenden.

### [evals/improvement] evals/runners/check_eval_regressions.py:220
**CLI validiert Baseline nie gegen die Golden-Tasks (schwache Validierung)**
**Fix:** In main() optional die Golden-Tasks laden (z.B. ueber --tasks) und an einen erweiterten Validierungspfad weiterreichen, damit Baseline-Drift gegen die Golden-Cases vorab erkannt wird.

### [evals/improvement] evals/runners/policy_dashboard.py:59
**value_hash-Fallback hasht leeren String, weil Adapter-Checks kein 'value' enthalten**
**Fix:** Bei fehlendem value_hash entweder den Check-Typ in den Hash einbeziehen (stable_hash([check.get('type'), check.get('value','')])) oder das fehlende value_hash explizit als 'unknown' kennzeichnen statt einen irrefuehrenden Konstanten-Hash zu erzeugen.

### [evals/improvement] evals/adapters/answer_quality_adapter.py:47
**cites_evidence-Heuristik akzeptiert nur ein festes Pfad-Praefix-Set**
**Fix:** Das Praefix-Set um companion, voice, personal_os (und ggf. weitere echte Top-Level-Ordner) erweitern oder generischer auf '<bekannter_ordner>/<datei>.<ext>' pruefen, statt eine hartkodierte Whitelist zu fuehren.

### [evals/improvement] evals/adapters/os_draft_adapter.py:22
**Path-Traversal-Erkennung greift nur bei Vorwaerts-Slash, nicht bei Windows-Backslash**
**Fix:** Auch Backslash-Varianten pruefen, z.B. any(marker in text for marker in ('../', '..\\', 'path traversal')) bzw. den Pfad vor dem Test auf '/'-Normalform bringen (text.replace('\\','/')).

### [evals/improvement] evals/runners/run_manual_prompt_probe.py:230
**Reply-Extraktion faellt bei Nicht-Standard-Payloads auf String der ganzen Payload zurueck**
**Fix:** Bei fehlendem 'reply'/'detail' nicht die ganze Payload stringifizieren, sondern explizit error='unexpected payload shape' setzen und reply='' lassen, damit json_response/non_empty_reply den Fall korrekt als Fehlschlag markieren.

### [frontend-app-shell/improvement] frontend/src/app.js:266
**Command-Count wird nur einmal beim Init geladen, nicht bei Reconnect aktualisiert**
**Fix:** Das Laden des Command-Counts in checkHealth (beim Wechsel auf backendOnline=true) oder ueber einen LexaState.on('backendOnline')-Listener erneut anstossen, damit der Zaehler nach erfolgreichem Reconnect korrekt befuellt wird.

### [frontend-app-shell/improvement] frontend/src/commands.js:513
**Hartkodierter Button-Text statt i18n in dashQuickPomodoro**
**Fix:** Den Button-Text ueber einen i18n-Key setzen (z.B. t('pomodoro.startLabel')) und das Label konsistent in refreshDashboard pflegen, statt es punktuell hartzucodieren.

### [frontend-chat-core/improvement] frontend/src/chat.js:1672
**Follow-up-Vorschlaege werden auch bei abgebrochenen/timeout-Antworten generiert**
**Fix:** Die Chip-Generierung zusaetzlich an !streamStoppedByUser && !streamTimedOut && !streamError binden, damit Folgevorschlaege nur bei einer vollstaendig und fehlerfrei empfangenen Antwort erscheinen.

### [frontend-chat-core/improvement] frontend/src/chat.js:1681
**Suggestion-Chip ignoriert syncChatInputSize und kann Vorschlag bei laufendem Stream verwerfen**
**Fix:** Im Chip-Handler vor dem Entfernen pruefen: if (LexaState.get('isLoading')) return; danach chatInput.value = s; syncChatInputSize(); und erst nach erfolgreichem Start von sendMessage() den Container entfernen (oder suggestDiv erst in sendMessage nach bestandenen Guards verstecken).

### [frontend-chat-core/improvement] frontend/src/chat.js:489
**generateSuggestions: extrem lange Heuristik mit Duplikaten in Keyword-Listen**
**Fix:** Keyword-Listen in Konstanten auslagern, per Set deduplizieren und das Matching tabellengetrieben aufbauen (Mapping topic->trigger words->suggestion keys). Das reduziert die Funktion drastisch und entfernt die doppelten Eintraege; optional die Vorschlagslogik in eine eigene Datei (analog chat_constants.js) verschieben.

### [frontend-chat-features/improvement] frontend/src/chat_search.js:177
**Such-Treffer für Notizen/Memories öffnen nicht das konkrete Element, nur die Memory-View**
**Fix:** switchView("memory") um eine gezielte Navigation/Highlight-Funktion ergänzen, die n.id bzw. m.id übergibt (z.B. switchView("memory", { focusId: n.id })) und das Element in der Liste hervorhebt oder öffnet.

### [frontend-chat-features/improvement] frontend/src/chat_message_actions_controller.js:252
**saveMessageAsMemory erlaubt Mehrfachspeicherung derselben Antwort (Duplikat-Memories)**
**Fix:** Nach Erfolg btn.disabled = true setzen oder ein dataset-Flag 'saved' prüfen und am Funktionsanfang früh return, um Mehrfachspeicherung derselben Antwort als Memory zu verhindern.

### [frontend-chat-features/improvement] frontend/src/chat_file_upload.js:40
**Mehrfach-Drop wird stillschweigend verworfen — nur die erste Datei wird verarbeitet**
**Fix:** Entweder Dateien sequenziell verarbeiten (for-Schleife mit await handleFileUpload) oder bei files.length > 1 einen Toast anzeigen, dass nur eine Datei pro Vorgang unterstützt wird, damit der Nutzer nicht im Unklaren bleibt.

### [frontend-personal-os-productivity/improvement] frontend/src/personal_os.js:113
**Obsidian-Kontext-Topic kann durch Default-Fallback ungewollte Suchbegriffe injizieren**
**Fix:** Den Fallback-Topic nur verwenden, wenn area UND tag leer/Default sind, und ihn als konfigurierbaren bzw. lokalisierten Wert (posUiText) statt als hartkodierten englischen String führen; bei vorhandenem area/tag keinen generischen Fallback anhängen.

### [frontend-personal-os-productivity/improvement] frontend/src/productivity.js:545
**Sidebar-Todo-Badge: Zahl statt String an textContent, sprachunabhängige Schwellen-Logik dupliziert**
**Fix:** Badge-Update in eine gemeinsame Hilfsfunktion auslagern (analog posRenderBadge) und mit String-Cast (`String(pendingCount)`) versorgen; den zusätzlichen todos("open")-Call entfernen und stattdessen den bereits in refreshProdStats geladenen open_todos-Wert nutzen.

### [frontend-personal-os-productivity/improvement] frontend/src/personal_os_renderers.js:382
**History-Events werden in UI und Chat-Prompt unterschiedlich sortiert/ausgewählt**
**Fix:** Sortierung und Auswahl angleichen: in beiden Pfaden dieselbe Reihenfolge (z.B. neueste zuerst) und denselben Cut (letzte N) verwenden, idealerweise über einen gemeinsamen Helper, damit UI und Prompt konsistent sind.

### [frontend-personal-os-productivity/improvement] frontend/src/personal_os_review_helpers.js:41
**Toter Code: renderPosApplyHint und renderPosPromptHint (HTML-String-Varianten) werden nirgends gerendert**
**Fix:** Beide HTML-String-Funktionen entfernen und die zugehörigen Test-/Doc-Erwartungen anpassen, da die DOM-Factories die einzige genutzte und sichere Quelle sind.

### [frontend-views/improvement] frontend/src/memory.js:1404
**runMemoryCleanup löscht Daten ohne Bestätigungsdialog und mit Magic-Numbers**
**Fix:** Vor dem Cleanup einen showInputModal/Confirm-Dialog anzeigen, der die Kriterien (90 Tage, geringe Wichtigkeit) nennt und 'ja' verlangt, analog zu note-/snippet-Löschungen; optional die Schwellen konfigurierbar machen.

### [personal-os-sdk/improvement] personal_os/11_Integrations/MCP/os-mcp-server/src/index.ts:625
**Kein os_uncheck_task-Tool - per MCP gesetzte Tasks lassen sich nicht wieder oeffnen**
**Fix:** Ein os_uncheck_task-Tool analog zu os_check_task registrieren, das OS.AST.uncheckTask(file.ast, taskString) aufruft und ueber OS.write() mit requireApproval schreibt.

### [voice-pipeline/improvement] voice/stt.py:480
**Deepgram-Keyterm nur gesetzt, wenn 'Lexa' im Prompt — bei normaler Transkription kein Keyword-Boosting**
**Fix:** Den Assistentennamen (und ggf. haeufige Domaenenbegriffe) generell als keyterm an Deepgram uebergeben (konfigurierbar), nicht nur abhaengig vom prompt-Inhalt.

### [voice-pipeline/improvement] voice/conversation.py:230
**Konversationshistorie ist auf 20 Eintraege gedeckelt, schneidet aber mitten im User/Assistant-Paar**
**Fix:** Historie paarweise begrenzen (z.B. ganze user/assistant-Paare beim Trimmen entfernen) oder vor dem Senden an chat_stream auf gueltige Rollenabfolge normalisieren.

### [website/improvement] i18n.js:442
**setLanguage überschreibt Elemente nur bei vorhandenem Key — fehlende Keys bleiben unentdeckt; Text ohne data-i18n bleibt einsprachig**
**Fix:** Im Dev-Build bei fehlendem Key console.warn ausgeben, und alle benutzersichtbaren Texte mit data-i18n versehen (insbesondere dashboard.html Zeile 174 'Alle Tools + Dev-Suite' einen Key geben), damit der Sprachwechsel vollständig greift.

### [website/improvement] dashboard.js:378
**Kopier-Button für Lizenzschlüssel ohne Fehlerbehandlung / Fallback bei fehlendem Clipboard-Zugriff**
**Fix:** Einen .catch()-Zweig ergänzen, der eine kurze Fehlermeldung anzeigt bzw. einen Text-Selektions-Fallback bietet, und das Kopieren unterdrücken, wenn license-key noch ein Platzhalter ist.

### [website/improvement] auth.js:186
**Nach erfolgreicher Registrierung bleibt das Formular ausgefüllt und der Nutzer ohne klare nächste Aktion**
**Fix:** Bei Erfolg signupForm.reset() aufrufen, optional automatisch auf den Login-Tab umschalten und die Erfolgsmeldung dort prominent anzeigen, damit der nächste Schritt (E-Mail bestätigen, dann anmelden) eindeutig ist.

## WEITERE (unverifiziert: medium/low Bugs/Security/Perf/Quality) — 370

- **[backend-agent-core/low/bug]** backend/agent_loop.py:1213 — duration_ms bei Timeout wird falsch berechnet (AGENT_STEP_TIMEOUT * 1000 statt gemessene Zeit)
- **[backend-agent-core/low/quality]** backend/agent_loop.py:38 — Importiertes _TOOL_ARGUMENT_ERROR_REPLY wird sofort durch lokale Definition ueberschrieben (toter Import / Inkonsistenzrisiko)
- **[backend-agent-core/low/bug]** backend/action_parser.py:177 — Single-Quote-Reparatur in _try_parse kann valides JSON mit Apostrophen in Werten zerstoeren bzw. Strings mit ' nie reparieren
- **[backend-agent-core/low/bug]** backend/action_parser.py:594 — update_history-Default max_entries=40 ist inkonsistent mit MAX_HISTORY=80
- **[backend-agent-core/low/bug]** backend/agent_loop.py:435 — Personal-OS-Tool-Ergebnis wird nicht auf dict-Typ geprueft (anders als companion.execute-Pfad)
- **[backend-agent-core/low/performance]** backend/router_agent.py:112 — _is_hermes_system_status_request ruft _hermes_forced_first_tool doppelt auf (einmal hier, einmal in run_agent)
- **[backend-agent-core/low/bug]** backend/agent_loop.py:1163 — Forced-First-Tool-Schritt: bei needs_confirmation kein Loeschen/Reset des globalen Pending-State und fragile Status-Kopplung
- **[backend-agent-core/low/bug]** backend/agent_loop.py:1598 — Repeat-Failure-Abbruch greift nur fuer exakt identische Argumente — Endlos-Variation moeglich
- **[backend-agent-core/medium/security]** backend/agent_loop.py:441 — Agent-Pfad fuehrt kein check_action_rate_limit fuer riskante Tools durch (anders als action_executor)
- **[backend-agent-core/medium/security]** backend/agent_protocol.py:412 — trace_path_is_safe gibt fuer Pfade AUSSERHALB des Repos True zurueck — Traces koennen an beliebige Orte geschrieben werden
- **[backend-agent-core/medium/bug]** backend/agent_loop.py:1672 — Mehrere Tool-Calls pro LLM-Turn: nach dem ersten Schritt wird der Rest des Batches verworfen (break)
- **[backend-agent-core/medium/bug]** backend/agent_loop.py:1247 — forced_direct_summary verwirft echtes Ergebnis bei leerer Summary-Formatierung — Agent meldet faelschlich 'fertig' ohne Antwort
- **[backend-agent-core/medium/performance]** backend/router_agent.py:314 — Shielded-Save-Retry-Schleife kann bei wiederholter Cancellation eng pollen / haengen
- **[backend-agent-core/medium/bug]** backend/action_parser.py:61 — validate_command_output nutzt naive Substring-Suche — False Positives blockieren harmlose Nutzerinhalte
- **[backend-ai-engine/low/performance]** backend/ai_engine.py:3452 — _detect_quality_mode läuft bei jeder Nachricht durch ~25 Marker-Gruppen — vermeidbarer Overhead
- **[backend-ai-engine/low/quality]** backend/ai_engine.py:4338 — Anthropic-Titelgenerierung im toten Zweig kann bei API-Fehler unbehandelt durchschlagen
- **[backend-ai-engine/low/performance]** backend/ai_engine.py:3683 — Pro Memory-Suche wird ein neuer ThreadPoolExecutor erzeugt und mit cancel_futures verworfen
- **[backend-ai-engine/low/quality]** backend/memory.py:937 — Agent-Schritte verschmutzen die interactions-Tabelle mit Platzhalter-Zeilen
- **[backend-ai-engine/medium/performance]** backend/ai_engine.py:513 — Gemini-API-Aufrufe setzen weder max_tokens noch temperature — unbegrenzte/teure Antworten
- **[backend-ai-engine/medium/bug]** backend/ai_engine.py:3989 — Tool-freier Stream-Retry triggert bei Gemini praktisch nie (Groq-spezifische Fehlererkennung)
- **[backend-chat/low/security]** backend/router_context.py:62 — GET /context/clipboard ohne Rate-Limiting trotz PowerShell-Prozess-Spawn
- **[backend-chat/low/performance]** backend/response_cache.py:99 — Cache-Lookup: linearer Scan ueber alle Eintraege bei jedem Cache-Miss
- **[backend-chat/low/bug]** backend/conversation_summary.py:171 — Assistant-Nachrichten werden bei jeder Zusammenfassung mit json.loads geparst — falsche Annahme ueber History-Format
- **[backend-chat/low/performance]** backend/router_context.py:194 — clipboard_history-Endpoint ruft blocking get_history() ohne asyncio.to_thread im Event-Loop
- **[backend-chat/low/security]** backend/router_conversations.py:40 — Conversation-CRUD-Endpoints ohne Rate-Limiting
- **[backend-chat/low/performance]** backend/context_monitor.py:328 — Event-Handler werden synchron im Monitor-Thread aufgerufen und koennen den Loop blockieren
- **[backend-chat/low/bug]** backend/context_monitor.py:25 — ctypes.windll-Zugriff auf Modulebene bricht Import auf Nicht-Windows / in Tests
- **[backend-chat/low/quality]** backend/router_chat.py:1763 — History-Marker fuer Tool-Calls nutzt Umlaut/Sonderzeichen trotz ASCII-Fold-Konvention des Files
- **[backend-chat/low/security]** backend/context_tools.py:198 — KI-gesteuerte Context-Tools fuehren ungedrosselte System-/Subprozess-Operationen ohne Audit aus
- **[backend-chat/low/quality]** backend/router_chat.py:1256 — Dict-zu-Text-Fallback fuer Action-Ergebnisse erzeugt unkontrollierte 'key: value'-Dumps in der Chat-Antwort
- **[backend-chat/low/bug]** backend/response_cache.py:14 — Cache-TTL/Max aus Umgebungsvariablen ohne Validierung — ungueltige Werte sprengen Import oder deaktivieren Cache
- **[backend-chat/low/bug]** backend/router_chat.py:1593 — Hermes-Stream: History wird mit '[Hermes]'-Praefix gespeichert und bricht kontextuelle Followups
- **[backend-chat/low/quality]** backend/conversation_summary.py:109 — extract_keywords: words.index() pro Wort — O(n*k) und intransparentes Ranking
- **[backend-chat/medium/bug]** backend/router_chat.py:1727 — next(g, s) in run_in_executor: gen.close() im finally kann mit laufendem Executor-Future kollidieren
- **[backend-chat/medium/bug]** backend/router_chat.py:1853 — Bei Stream-Abbruch (CancelledError) geht der bereits gestreamte Text fuer die History verloren
- **[backend-chat/medium/bug]** backend/router_chat.py:1841 — Tool-Pattern-Text wird faelschlich in den Response-Cache geschrieben
- **[backend-chat/medium/bug]** backend/router_conversations.py:86 — load_conversation ueberschreibt aktive History ohne Pending-Confirmation/Cache-Reset
- **[backend-chat/medium/bug]** backend/router_chat.py:437 — Hermes-Commit: set_pending_confirmation nach clear ohne Lock — Pending kann verloren gehen
- **[backend-chat/medium/performance]** backend/context_monitor.py:179 — Clipboard-Polling startet alle ~10s einen PowerShell-Prozess — Dauerlast und Latenz
- **[backend-chat/medium/bug]** backend/router_chat.py:1779 — Fallback-Tool-Detektor matcht generisches Muster '(\w+)\(.*?\)' und kann Code/Text als Tool-Aufruf fehlinterpretieren
- **[backend-hermes/low/quality]** backend/hermes_adapter.py:75 — Inkonsistente Telegram-Token-Regex zwischen Adapter und Router (Anchoring)
- **[backend-hermes/low/bug]** backend/hermes_adapter.py:2405 — Autostart-Deaktivierung: unlink() ohne missing_ok kann bei Race zu FileNotFoundError fuehren
- **[backend-hermes/low/bug]** backend/hermes_adapter.py:2363 — Autostart-Batch escaped Prozentzeichen in eingebetteten Pfaden nicht
- **[backend-hermes/low/performance]** backend/hermes_adapter.py:1095 — shutil.which('whisper') bei jedem Media-Statusabruf
- **[backend-hermes/low/performance]** backend/hermes_adapter.py:1419 — _lexa_mcp_command_ready ruft shutil.which bei jedem Server pro Capabilities-Request
- **[backend-hermes/low/performance]** backend/router_hermes.py:246 — _safe_draft_queue ruft hartkodiert maxDrafts=50, ignoriert Overview-Kontext und kann grosse Payloads erzeugen
- **[backend-hermes/low/security]** backend/router_hermes.py:458 — Mehrere Hermes-GET-Endpoints ohne Rate-Limiting
- **[backend-hermes/low/quality]** backend/hermes_adapter.py:2266 — Selftest ruft Plugin-internen Hook _pre_gateway_dispatch statt des registrierten Hooks auf
- **[backend-hermes/low/bug]** backend/router_hermes.py:312 — Overview-Healthcheck schliesst den 'drafts'-Check doppelt/inkonsistent ein
- **[backend-hermes/low/bug]** backend/hermes_adapter.py:514 — _write_hermes_env_values liest .env ohne errors-Toleranz und kann bei Encoding-Fehler crashen
- **[backend-hermes/medium/performance]** backend/hermes_adapter.py:1810 — get_hermes_capabilities loest verschachtelte, redundante Statusberechnungen aus
- **[backend-hermes/medium/bug]** backend/hermes_adapter.py:2540 — run_hermes_task uebergibt vollstaendigen Prompt via Kommandozeile (-z) statt stdin
- **[backend-hermes/medium/performance]** backend/hermes_adapter.py:1328 — _safe_lexa_memory_snapshot fuehrt COUNT(*) ueber bis zu 6 Tabellen mit aggressivem 0.25s-Timeout
- **[backend-hermes/medium/performance]** backend/hermes_adapter.py:2369 — Autostart-Batch fuehrt Hermes-Gateway in Endlosschleife ohne Auslastungsgrenze, Log waechst unbegrenzt
- **[backend-intent/low/bug]** backend/intent_engine.py:643 — YouTube-Befehle werden von _RE_SPOTIFY abgefangen, _RE_YOUTUBE nie erreicht
- **[backend-intent/low/quality]** backend/lexa_system_answer.py:131 — Ungenutzter Parameter user_message in build_lexa_system_answer
- **[backend-intent/low/quality]** backend/lexa_system_answer.py:24 — Toter Code: Grossbuchstaben-Umlaut-Mappings nach .lower() wirkungslos
- **[backend-intent/low/security]** backend/error_response.py:77 — error_payload spiegelt rohes 'detail' ungefiltert in die Antwort
- **[backend-intent/low/performance]** backend/intent_engine.py:1043 — Synchroner heavy Import/Aufruf von companion.app_discovery im Schnellpfad
- **[backend-intent/low/bug]** backend/intent_engine.py:99 — _clip_context_path strippt ']' und '}' und beschaedigt valide Pfade mit diesen Zeichen
- **[backend-intent/low/bug]** backend/intent_engine.py:426 — 'has_spotify and not play_idx' behandelt play_idx==0 falsch
- **[backend-intent/low/performance]** backend/router_smart.py:195 — /insights cached AI-Ergebnis nicht — teure Daten-Aggregation + AI-Call pro Aufruf
- **[backend-intent/medium/security]** backend/router_search.py:19 — Such-Endpoints ohne Rate-Limiting
- **[backend-intent/medium/bug]** backend/router_smart.py:252 — _build_insights_prompt crasht bei fehlendem 'count'/'hour'-Schluessel in Aktivitaetsdaten
- **[backend-intent/medium/performance]** backend/router_search.py:42 — rebuild_fts ohne Rate-Limit und ohne Schutz vor parallelen Rebuilds
- **[backend-intent/medium/bug]** backend/intent_engine.py:471 — Compound-Suche strippt Such-Praefix nur bei Leerzeichen-Trennung
- **[backend-intent/medium/bug]** backend/intent_engine.py:1433 — 'lauter'/'leiser' setzen feste Lautstaerke 70/30 statt relativer Aenderung
- **[backend-intent/medium/bug]** backend/intent_engine.py:714 — Wetter-City-Regex erfasst nachfolgende Zeitwoerter als Stadtnamen
- **[backend-memory/low/bug]** backend/memory.py:1198 — conversation_list: Parsing der letzten Nachricht aus SUBSTR-Tail ist fragil
- **[backend-memory/low/performance]** backend/memory.py:444 — Dedup-Exact-Match per LOWER(TRIM(content)) ohne Index — Full-Table-Scan pro add_memory
- **[backend-memory/low/bug]** backend/router_embeddings.py:18 — _reindex_running ist nicht thread-/task-safe (Race beim Start)
- **[backend-memory/low/bug]** backend/memory.py:1248 — conversation_update überschreibt messages komplett — Lost-Update bei parallelen Schreibern
- **[backend-memory/low/bug]** backend/memory.py:2108 — restore_database: prod_db.ROLLBACK referenziert ggf. ungebundene Variable
- **[backend-memory/low/bug]** backend/memory.py:1158 — routine_toggle/routine_create melden Erfolg auch bei nicht existierender Routine
- **[backend-memory/low/bug]** backend/memory.py:962 — auto_remember: add_memory committet innerhalb des laufenden Interaction-Inserts
- **[backend-memory/low/quality]** backend/embeddings.py:305 — Lokaler TF-IDF nutzt MD5 für Feature-Hashing — unnötig teuer
- **[backend-memory/medium/performance]** backend/smart_memory.py:323 — app_usage wächst unbegrenzt; _update_common_apps bei jedem App-Tracking
- **[backend-memory/medium/performance]** backend/memory.py:624 — search_memory_semantic lädt alle eingebetteten Memories in Python (Full-Scan, kein ANN)
- **[backend-memory/medium/performance]** backend/memory.py:484 — add_memory: synchroner OpenAI-Embedding-Call im Schreibpfad (blockierend)
- **[backend-memory/medium/bug]** backend/memory.py:805 — reindex_embeddings: toter offset-Zähler und potenzielle Endlosschleife bei fehlschlagenden Embeddings
- **[backend-memory/medium/bug]** backend/memory.py:488 — add_memory: Re-Fetch der eingefügten Zeile per content kann falsche ID liefern
- **[backend-memory/medium/performance]** backend/smart_memory.py:81 — interaction_log wächst unbegrenzt — keine Cleanup-Logik
- **[backend-personal-os/low/quality]** backend/personal_os_actions.py:531 — personal_os_lexa_code_loop wirft bei ungueltigem Tag-Parameter statt Default zu nutzen
- **[backend-personal-os/low/quality]** backend/obsidian_context.py:175 — resolve_personal_os_root kann bei gesetzter, falscher Env-Var still einen nicht existierenden Vault liefern
- **[backend-personal-os/low/bug]** backend/obsidian_context.py:146 — _clip gibt bei sehr kleinem limit nur den Truncation-Marker statt Inhalt zurueck
- **[backend-personal-os/low/bug]** backend/os_agent_runtime.py:199 — node-Aufruf fuer SDK-Draft-Write nutzt bare 'node' (Inkonsistenz/Portabilitaet)
- **[backend-personal-os/low/performance]** backend/os_agent_runtime.py:123 — Blockierender npm-Build (bis 60s) im OS-Agent-Threadpool kann beide Worker-Slots blockieren
- **[backend-personal-os/low/quality]** backend/router_personal_os.py:1717 — raw_inbox_extract: AI-Engine-Aufruf maskiert alle Fehlerklassen als generisches 502
- **[backend-personal-os/low/quality]** backend/personal_os_actions.py:600 — Breites except Exception leakt rohe Exception-Strings an den Chat-Nutzer
- **[backend-personal-os/low/quality]** backend/router_personal_os.py:1689 — raw_inbox_submit: kein Cleanup der geschriebenen Datei bei Worker-Fehler (inkonsistenter Zustand)
- **[backend-personal-os/low/quality]** backend/router_personal_os.py:358 — Raw-Inbox-Worker-Status verlangt gebautes dist/index.js, prueft aber nur Verzeichnis
- **[backend-personal-os/medium/bug]** backend/router_os_agents.py:73 — sanitize_input kuerzt OS-Agent-Instructions still auf 2000 Zeichen (Datenverlust)
- **[backend-personal-os/medium/security]** backend/os_agent_runtime.py:475 — Hermes-stdout/stderr werden unredigiert auf Platte und in der API gespeichert
- **[backend-personal-os/medium/performance]** backend/obsidian_context.py:256 — build_obsidian_context_payload: bis zu ~1000+ Datei-Prefix-Reads pro Aufruf (Latenz/IO)
- **[backend-personal-os/medium/bug]** backend/os_agent_runtime.py:130 — SDK-Auto-Build schlaegt auf Windows fehl: bare 'npm' statt 'npm.cmd' bei shell=False
- **[backend-productivity/low/performance]** backend/reminders.py:444 — _fired_reminders wächst bei ausbleibendem Acknowledge unbegrenzt
- **[backend-productivity/low/quality]** backend/productivity.py:386 — Pomodoro-Status-Cache wird ohne gesetzten Timestamp invalidiert
- **[backend-productivity/low/bug]** backend/proactive.py:800 — Festplatten-Warnung prüft auf Windows den falschen Pfad
- **[backend-productivity/low/bug]** backend/proactive.py:732 — E-Mail-Benachrichtigung verpasst neue Mails nach Nullstand
- **[backend-productivity/low/performance]** backend/router_productivity.py:120 — Massenlöschung erledigter Todos ist N+1 statt einer Query
- **[backend-productivity/low/performance]** backend/proactive.py:178 — On-Demand-Generierung läuft ungesperrt parallel zum Background-Loop
- **[backend-productivity/low/performance]** backend/productivity.py:650 — Zeiterfassung kompiliert pro 30s-Tick C# via PowerShell Add-Type
- **[backend-productivity/low/bug]** backend/workflows.py:133 — Cron-Step-Range mit 1-basierten Feldern (DOM/Month) berechnet Schritte abweichend von Standard-Cron
- **[backend-productivity/low/bug]** backend/workflows.py:1018 — _evaluate_condition: Ordnungsvergleich (< >) mit Strings liefert stumm immer False
- **[backend-productivity/low/security]** backend/workflows.py:877 — SSRF-DNS-Check schlägt fail-open, wenn DNS-Auflösung scheitert
- **[backend-productivity/low/quality]** backend/router_productivity.py:111 — Tote status_code-Annahme bei Fehler-Dicts — Not-Found wird als 400 ausgeliefert
- **[backend-productivity/low/quality]** backend/scheduler.py:77 — Routine-Schedule 'Mo,Mi,Fr' ignoriert ungültige Tageskürzel still
- **[backend-productivity/low/quality]** backend/reminders.py:111 — reminder_create akzeptiert vergangene/zu nahe Zeiten ohne sinnvolle Untergrenze
- **[backend-productivity/low/quality]** backend/productivity.py:363 — Lokale Variable t überschattet das importierte i18n-t innerhalb pomodoro_start
- **[backend-productivity/low/bug]** backend/workflows.py:769 — ai_prompt-Step wertet chat()-Ergebnistyp nicht aus (error/tool_call)
- **[backend-productivity/medium/bug]** backend/productivity.py:470 — Streak-Berechnung und habit_list verwenden uneinheitliche Erfüllungskriterien
- **[backend-productivity/medium/bug]** backend/productivity.py:357 — Pomodoro-DB-Completion markiert per MAX(id) potenziell die falsche Session
- **[backend-productivity/medium/quality]** backend/router_calendar.py:43 — calendar_connect startet OAuth-Browserflow ohne Timeout und kann den Endpoint blockieren
- **[backend-productivity/medium/bug]** backend/productivity.py:279 — todo_update meldet Erfolg auch für nicht existierende Todos
- **[backend-productivity/medium/performance]** backend/workflows.py:833 — Notify-Step blockiert pro Benachrichtigung 6+ Sekunden einen Thread
- **[backend-productivity/medium/bug]** backend/scheduler.py:91 — Intervall-Routinen: Sekunden-Intervalle wirkungslos, Modulo-Logik unzuverlässig
- **[backend-productivity/medium/bug]** backend/workflows.py:854 — HTTP-Step mutiert das headers-Dict des gespeicherten Steps und löst keine Templates in Headern auf
- **[backend-productivity/medium/bug]** backend/workflows.py:1119 — Scheduler kann denselben Workflow doppelt parallel starten (keine Lauf-Sperre)
- **[backend-security-main/low/performance]** backend/router_backup.py:110 — Backup-Datei-Erstellung: Fallback schreibt vollständiges Backup-JSON inkl. evtl. sensibler Daten erneut, doppelte Serialisierung
- **[backend-security-main/low/quality]** backend/main.py:293 — Optionale Phase-39+-Router scheitern still bei echten Importfehlern (nicht nur fehlenden Modulen)
- **[backend-security-main/low/bug]** backend/memory.py:2063 — restore_database zählt INSERT OR IGNORE-Treffer als 'inserted', auch wenn Zeilen wegen Konflikt verworfen werden
- **[backend-security-main/low/performance]** backend/startup_diagnostics.py:222 — build_startup_diagnostics: /health/startup ungecacht und ohne Rate-Limit — teure Probes bei Polling
- **[backend-security-main/low/performance]** backend/main.py:31 — Sentry-DSN-Keyring-Lookup beim Modulimport blockiert synchron vor App-Start
- **[backend-security-main/low/quality]** backend/integrations.py:156 — get_spotify_status: process_iter ohne NoSuchProcess/AccessDenied-Behandlung kann iterieren-während-Mutation crashen
- **[backend-security-main/low/quality]** backend/main.py:804 — uvicorn-Start: zwei divergierende Startpfade und zwei Quellen für Host/Port
- **[backend-security-main/low/security]** backend/security.py:384 — _BLOCKED_HOSTS enthält Duplikate und deckt IPv6-Metadaten-Hosts nicht ab — vermittelt falsche Vollständigkeit
- **[backend-security-main/low/performance]** backend/integrations.py:561 — analyze_clipboard ruft PowerShell synchron mit 3s-Timeout bei jeder Analyse auf — blockierend wenn aus async-Kontext genutzt
- **[backend-security-main/low/performance]** backend/security.py:151 — is_command_allowed normalisiert die gesamte Whitelist bei jedem Aufruf neu (drei List-Comprehensions pro Befehl)
- **[backend-security-main/medium/bug]** backend/security.py:292 — sanitize_input kürzt Chat-Nachrichten still auf 2000 Zeichen — unter dem konfigurierten MAX_CHAT_MESSAGE_LENGTH (4000)
- **[backend-security-main/medium/security]** backend/security.py:373 — Pfad-Traversal-Prüfung greift auf rohen String statt auf den aufgelösten Pfad
- **[backend-security-main/medium/bug]** backend/main.py:163 — CORS-Origins passen nicht zur tatsächlichen Frontend-Herkunft (allow_credentials mit toten Origins)
- **[backend-security-main/medium/security]** backend/security.py:384 — validate_url führt keine DNS-Auflösung durch — SSRF über DNS-Rebinding/Hostnamen auf private IPs möglich
- **[backend-security-main/medium/security]** backend/local_auth.py:32 — is_public_path öffnet im Dev-Modus /docs, /openapi.json etc. ohne Auth — LEXA_ENV ist beliebig setzbar
- **[backend-security-main/medium/security]** backend/security.py:331 — validate_command_output erkennt gefährliche Befehle nur per naivem Substring-Vergleich — trivial umgehbar
- **[backend-tools-plugins/low/quality]** backend/plugin_manager.py:1083 — LEXA_PLUGIN_HTTP_GET wird bei jeder Ausführung neu auf das Modul gesetzt (Cross-Call-Überschreibung)
- **[backend-tools-plugins/low/performance]** backend/router_personal_os.py:177 — Blockierender mcp_registry.load_config() im async-Pfad
- **[backend-tools-plugins/low/quality]** backend/tool_registry.py:849 — Tool-Anzahl-Kommentare und Log-Meldung sind grob falsch (202 statt '140+')
- **[backend-tools-plugins/low/security]** backend/mcp_client.py:118 — MCP-Subprozess wird ohne Working-Directory und ohne command-Allowlist gestartet
- **[backend-tools-plugins/low/quality]** backend/router_mcp.py:168 — Doppeltes Timeout beim MCP-Tool-Aufruf
- **[backend-tools-plugins/low/bug]** backend/tool_registry.py:92 — process_kill kann ohne pid und ohne name aufgerufen werden (keine 'oneOf'-Validierung)
- **[backend-tools-plugins/medium/bug]** backend/mcp_client.py:374 — JSON-RPC-Response wird nicht zugeordnet, wenn der Server die id als String zurückgibt
- **[backend-tools-plugins/medium/bug]** backend/plugins_builtin/web_search.py:127 — Snippet-Zuordnung per Index führt zu falschen Snippets bei den Suchergebnissen
- **[backend-tools-plugins/medium/security]** backend/plugin_manager.py:392 — allow_private_hosts erlaubt trusted Plugins Zugriff auf localhost und Cloud-Metadata (SSRF)
- **[backend-tools-plugins/medium/bug]** backend/mcp_registry.py:414 — get_all_mcp_tools iteriert die Live-Dict _clients ohne Snapshot (RuntimeError-Risiko)
- **[backend-voice-vision-stripe/low/bug]** backend/vision.py:164 — Fenstersuche kann bei window_title mit haengendem hwnd in Endlosschleife/Haenger laufen
- **[backend-voice-vision-stripe/low/bug]** backend/router_vision.py:209 — GIF/BMP-Uploads werden mit falschem image/png-MIME an Provider gesendet
- **[backend-voice-vision-stripe/low/bug]** backend/voice_ws.py:110 — _last_volume_push ist nicht lock-geschuetzt — Volume-Throttle bei parallelen Threads inkonsistent
- **[backend-voice-vision-stripe/low/quality]** backend/voice_ws.py:119 — Throttle und Event-Timestamps nutzen time.time() statt monotonic — anfaellig fuer Zeitspruenge
- **[backend-voice-vision-stripe/low/performance]** backend/companion_confirmation.py:70 — _cleanup_expired wird nur bei create aufgerufen — abgelaufene Confirmations bleiben im Speicher
- **[backend-voice-vision-stripe/low/bug]** backend/router_stripe.py:805 — get_subscription/validate_license greifen mit ['key'] auf Supabase-Rows zu — KeyError bei Schema-Drift
- **[backend-voice-vision-stripe/low/security]** backend/vision.py:509 — Nutzerbeschreibung wird ungefiltert in den Vision-Prompt eingebettet (Prompt-Injection)
- **[backend-voice-vision-stripe/low/bug]** backend/router_companion.py:403 — Batch dry_run-Eintraege zaehlen als 'executed', obwohl nichts ausgefuehrt wurde
- **[backend-voice-vision-stripe/low/quality]** backend/router_stripe.py:416 — SQLite-Pfad speichert current_period_start/price_id/cancel_at_period_end nicht — inkonsistent zu Supabase
- **[backend-voice-vision-stripe/low/bug]** backend/router_voice.py:929 — is_listening-Zugriff im Detector-Lock kann AttributeError werfen und Lock-Fehlerpfad inkonsistent lassen
- **[backend-voice-vision-stripe/low/performance]** backend/router_voice.py:971 — _last_poll_times waechst bis zur Bereinigung unbegrenzt und nutzt ungepruefte client_id
- **[backend-voice-vision-stripe/low/bug]** backend/router_voice.py:102 — TEMP_DIR.mkdir nutzt kein parents=True und Limit-/Timeout-Zweige loeschen Temp-Datei doppelt
- **[backend-voice-vision-stripe/medium/security]** backend/router_stripe.py:701 — checkout.session.completed verifiziert client_reference_id nicht gegen Stripe-Customer/Subscription
- **[backend-voice-vision-stripe/medium/bug]** backend/router_stripe.py:683 — Webhook quittiert Handler-Fehler mit 200 — verlorene Events ohne Retry
- **[backend-voice-vision-stripe/medium/bug]** backend/router_stripe.py:354 — current_period_start/end basieren auf veralteten Stripe-Subscription-Top-Level-Feldern
- **[backend-voice-vision-stripe/medium/performance]** backend/router_voice.py:462 — WebSocket-Heartbeat-Task wird bei Disconnect nicht zuverlaessig abgebrochen (Task-Leak)
- **[backend-voice-vision-stripe/medium/bug]** backend/vision.py:180 — _capture_active_window_sync ruft SetForegroundWindow auf — unerwarteter Fokuswechsel als Nebeneffekt
- **[backend-voice-vision-stripe/medium/bug]** backend/vision.py:286 — Vision-Antwort kann None sein — len(result) wirft TypeError beim Logging
- **[backend-voice-vision-stripe/medium/performance]** backend/router_vision.py:214 — analyze-file liest gesamten Upload in den Speicher, bevor die Groesse geprueft wird
- **[backend-voice-vision-stripe/medium/security]** backend/vision.py:240 — _load_image_file dekomprimiert beliebig grosse Bilder ohne Limit — Decompression-Bomb-Risiko
- **[companion-core/low/bug]** companion/hermes_desktop.py:1252 — _extract_window_hint Pattern 4 matcht beliebigen Resttext als Fenstername
- **[companion-core/low/bug]** companion/hermes_desktop.py:2236 — type-Verifikation in hermes_desktop_commit liest UI-Baum ohne kurze Wartezeit nach dem Tippen
- **[companion-core/low/bug]** companion/hermes_desktop.py:1979 — Vorbereiteter scroll-Parameter enthaelt 'window', wird aber bei der Ausfuehrung an desktop_scroll nicht uebergeben
- **[companion-core/low/bug]** companion/desktop_control.py:324 — GetWindowRect-Rueckgabewert in _window_capture_origin wird nicht geprueft
- **[companion-core/low/bug]** companion/desktop_control.py:156 — _screen_size nutzt GetSystemMetrics(0/1) statt der DPI-bewussten virtuellen Bildschirmgroesse
- **[companion-core/low/performance]** companion/desktop_engine.py:219 — observe()/read_screen_text starten je einen OCR-Screenshot zusaetzlich zum Timeout-Worker — doppelte Last und nicht abbrechbar
- **[companion-core/low/quality]** companion/desktop_engine.py:260 — read_screen_text mutiert das von ocr_screenshot zurueckgegebene payload-Dict in place
- **[companion-core/low/quality]** companion/engine.py:524 — read_clipboard liefert unbegrenzten Clipboard-Inhalt ohne Laengen-Cap zurueck
- **[companion-core/low/bug]** companion/hermes_desktop.py:1862 — Nicht-mutierende Aktionen (find/observe/screen_text) ignorieren inline-Abbruch-Formulierungen
- **[companion-core/low/bug]** companion/desktop_control.py:481 — desktop_hotkey gibt bei Fehler mitten in der Sequenz gedrueckte Modifier-Tasten nicht frei
- **[companion-core/low/security]** companion/engine.py:361 — Parameter-Wert-Laengen werden in execute() nicht begrenzt, nur die Anzahl
- **[companion-core/low/bug]** companion/engine.py:617 — _search_index escaped keine SQL-LIKE-Wildcards (%, _) im Suchbegriff
- **[companion-core/medium/bug]** companion/engine.py:1015 — shutdown_pc/restart_pc fuehren sofort und nicht stornierbar aus — kein Abbruch-Pfad
- **[companion-core/medium/performance]** companion/engine.py:1043 — screen_analyze: ThreadPoolExecutor wird ohne Timeout-Cleanup geschlossen, Vision-Future kann haengen
- **[companion-core/medium/performance]** companion/engine.py:396 — execute() ruft synchrone Blocking-Companion-Methoden direkt im Event-Loop-Kontext auf
- **[companion-core/medium/bug]** companion/hermes_desktop.py:1240 — _extract_typed_text faellt auf den restlichen Instruktionstext zurueck — Hermes tippt ggf. Steuerwoerter mit
- **[companion-core/medium/bug]** companion/desktop_control.py:309 — _window_capture_origin: FindWindowW(None, None) liefert nur ein Top-Level-Fenster, GetWindow-Kette kann Match verfehlen
- **[companion-core/medium/bug]** companion/hermes_desktop.py:546 — _DEICTIC_TERMS enthaelt haeufige Artikel (das, den, die) — kollidiert mit echten Klickzielen
- **[companion-tools-1/low/bug]** companion/browser.py:443 — search_youtube (Playwright-Pfad): href kann null sein → kaputte Video-URLs
- **[companion-tools-1/low/quality]** companion/dev_tools.py:586 — http_request: beliebige HTTP-Methode wird ungeprüft an urllib weitergereicht
- **[companion-tools-1/low/quality]** companion/dev_tools.py:803 — multi_server_check: Default-Server prüft localhost-Ports, die der URL-Pfad sonst blockiert
- **[companion-tools-1/low/bug]** companion/dev_tools.py:222 — git_diff: full=True meldet 'keine Änderungen', obwohl nur Binär-/Mode-Änderungen vorliegen
- **[companion-tools-1/low/quality]** companion/browser.py:280 — _ytdlp_search: 'except (TimeoutExpired, FileNotFoundError, Exception)' fängt alles; query ungeprüft
- **[companion-tools-1/low/bug]** companion/dev_tools.py:121 — git_status/git_log: subprocess-Returncode wird ignoriert — Fehler werden als leeres/sauberes Repo interpretiert
- **[companion-tools-1/low/bug]** companion/dev_tools.py:121 — git_status: Parsing der --porcelain-Ausgabe klassifiziert Staging-/Working-Status falsch
- **[companion-tools-1/low/performance]** companion/file_tools.py:453 — clean_temp: rglob-Größenberechnung kann bei sehr großen Temp-Bäumen blockieren
- **[companion-tools-1/low/performance]** companion/file_tools.py:130 — find_duplicates: max_files-Limit stoppt den Verzeichnis-Walk nicht
- **[companion-tools-1/low/bug]** companion/file_tools.py:216 — batch_rename: pattern verwirft prefix/suffix/replace-Optionen stillschweigend
- **[companion-tools-1/low/security]** companion/file_tools.py:86 — _validate_scan_path nutzt substring-Match auf 'windows\\system' — fragil und zu breit
- **[companion-tools-1/low/security]** companion/file_tools.py:234 — organize_downloads validiert downloads_path nicht und kann beliebige Ordner umsortieren
- **[companion-tools-1/low/quality]** companion/file_tools.py:942 — file_copy: copytree schlägt fehl, wenn Zielordner existiert — irreführende Fehlermeldung
- **[companion-tools-1/low/security]** companion/file_tools.py:1100 — file_write: .. -Prüfung auf Rohpfad, aber expanduser/resolve umgeht Blockliste teilweise
- **[companion-tools-1/medium/security]** companion/browser.py:671 — _get_readability_js lädt JS von externem CDN und injiziert es in jede gescrapte Seite
- **[companion-tools-1/medium/security]** companion/dev_tools.py:772 — server_check mit reinem host:port umgeht SSRF-/Private-IP-Prüfung (interner Port-Scan)
- **[companion-tools-1/medium/bug]** companion/file_tools.py:290 — split_pdf/merge_pdfs validieren Eingabepfade nicht und behandeln offene Bereiche fehlerhaft
- **[companion-tools-1/medium/security]** companion/file_tools.py:591 — archive_extract: tar-Entpackung nutzt nur filter='data', umgeht eigene _safe_archive_members-Prüfung
- **[companion-tools-1/medium/bug]** companion/browser.py:535 — website_screenshot/website_to_pdf: wait_for_load_state und screenshot/pdf nicht in try/except — Page-Leak und unbehandelte Exception
- **[companion-tools-1/medium/performance]** companion/browser.py:405 — open_url/play_youtube: page.new_page() ohne page.close() bei Erfolg — Page-Leak
- **[companion-tools-1/medium/security]** companion/dev_tools.py:294 — git_add: files-Parameter wird ungeprüft als git-Pfadspezifikation übergeben
- **[companion-tools-2/low/bug]** companion/weather.py:300 — weather_will_it_rain filtert auch vergangene Stunden des aktuellen Tages
- **[companion-tools-2/low/quality]** companion/tool_health.py:214 — refresh() läuft synchron im aufrufenden Thread und kann sekundenlang blockieren
- **[companion-tools-2/low/security]** companion/weather.py:115 — _get_default_city ruft ip-api.com über unverschlüsseltes HTTP auf
- **[companion-tools-2/low/quality]** companion/ocr.py:142 — _capture_for_ocr: fehleranfällige Window-Enumeration mit Substring-Match und stillem Vollbild-Fallback
- **[companion-tools-2/low/performance]** companion/weather.py:16 — Wetter-Cache wächst unbegrenzt (Memory Leak über lange Laufzeit)
- **[companion-tools-2/low/performance]** companion/tool_health.py:99 — Playwright-Health-Check startet bei jedem Build/Refresh einen echten Chromium-Headless-Browser
- **[companion-tools-2/low/bug]** companion/communication.py:233 — _parse_email_message: is_read defaultet bei fehlenden Flags auf True (UNSEEN-Mails fälschlich als gelesen)
- **[companion-tools-2/low/quality]** companion/app_discovery.py:485 — find_app Substring-Match bevorzugt kürzesten Namen — kann falsche App treffen
- **[companion-tools-2/low/quality]** companion/calendar_integration.py:84 — get_calendar_status meldet 'connected' allein anhand Dateiexistenz, nicht anhand gültiger Credentials
- **[companion-tools-2/low/bug]** companion/ui_automation.py:338 — _candidate_windows: prefer_recent-Fallback kann beliebiges Fenster als Klickziel liefern
- **[companion-tools-2/low/quality]** companion/ui_automation.py:579 — ui_click: occurrence wird stillschweigend auf den letzten Treffer geklemmt statt zu melden
- **[companion-tools-2/low/quality]** companion/app_discovery.py:653 — Auto-warm beim Import startet PowerShell-Thread als Seiteneffekt (problematisch in Tests/Subprozessen)
- **[companion-tools-2/low/bug]** companion/system_tools.py:541 — env_set: os.environ wird mit ungesäubertem Originalwert gesetzt, Prozess-Sicht inkonsistent zur Registry
- **[companion-tools-2/low/bug]** companion/media.py:109 — Spotify-Token-Cache ohne Lock: Race Condition bei paralleler Wiedergabe
- **[companion-tools-2/low/quality]** companion/communication.py:264 — email_read/email_search nutzen Default-IMAP-Port ohne SSL-Port-Konfig aus Provider-Map
- **[companion-tools-2/low/performance]** companion/app_discovery.py:646 — warm_cache_async lädt Disk-Cache und triggert trotzdem immer vollen Rebuild
- **[companion-tools-2/low/quality]** companion/system_tools.py:627 — Hostname-Validierung erlaubt mehrdeutige Eingaben, IPv6 mit Doppelpunkt nicht abgedeckt
- **[companion-tools-2/low/quality]** companion/system_tools.py:320 — autostart_add überschreibt bestehende Run-Einträge ohne Prüfung
- **[companion-tools-2/medium/security]** companion/communication.py:354 — email_search: IMAP-Suchbegriff-Escaping unzureichend (nur Backslash-Quote, keine CRLF-Filterung)
- **[companion-tools-2/medium/quality]** companion/calendar_integration.py:63 — OAuth-Flow öffnet bei abgelaufenem Token unkontrolliert lokalen Server/Browser mitten in einer Abfrage
- **[companion-tools-2/medium/bug]** companion/calendar_integration.py:280 — calendar_create: Default-Endzeit behandelt reine Datumsangaben falsch (1h-Termin statt Ganztag)
- **[companion-tools-2/medium/performance]** companion/communication.py:277 — email_read: Sender-Filter kann unbegrenzt viele Mails fetchen / langsam werden
- **[companion-tools-2/medium/security]** companion/media.py:446 — convert_media/extract_audio: output_path wird nicht gegen Path-Traversal/Systemdirs validiert
- **[companion-tools-2/medium/security]** companion/app_discovery.py:611 — launch_app: app_id über explorer shell:AppsFolder / cmd start ohne Wert-Härtung
- **[companion-tools-2/medium/bug]** companion/ocr.py:183 — ocr_screenshot/ocr_from_bytes verwenden lang='en', aber deutscher Text braucht 'de' für Tesseract-Fallback
- **[companion-tools-2/medium/quality]** companion/media.py:401 — open_spotify: Web-API-URI wird ohne Schema-Prüfung an cmd start übergeben
- **[companion-tools-2/medium/performance]** companion/tool_health.py:161 — Health-Check-API blockiert Aufrufer bis zu 10s (blockierender Event.wait in synchronem Code)
- **[companion-tools-2/medium/performance]** companion/media.py:504 — screen_record: Hintergrund-ffmpeg-Prozess wird nie eingesammelt (Pipe-Deadlock/Leak)
- **[electron-shell/low/performance]** frontend/src/orb3d.js:168 — Orb-Animationsschleife läuft dauerhaft mit requestAnimationFrame ohne sichtbarkeitsgebundenes Anhalten/Disposal
- **[electron-shell/low/quality]** frontend/main.js:1335 — show-notification-IPC validiert die Eingabe-Payload nicht
- **[electron-shell/low/security]** frontend/main.js:597 — CSP erlaubt img-src http: und https: (beliebige Remote-Bilder) trotz lokal-first-Anspruch
- **[electron-shell/low/bug]** frontend/main.js:932 — Fenster-close-Handler/Auto-Reload-Watcher können sich über Lifecycle-Übergänge ansammeln
- **[electron-shell/low/bug]** frontend/preload.js:1931 — generateTitle-Fallback wirft TypeError, wenn message null/undefined ist
- **[electron-shell/low/performance]** frontend/preload.js:2204 — getAutostart nutzt synchrones ipcRenderer.sendSync — blockiert den Renderer-Mainthread
- **[electron-shell/medium/quality]** frontend/preload.js:1434 — Kern-Bridge-Methoden (chat, stt, tts, chatFile, setProfile u.a.) prüfen res.ok nicht und können unverarbeitete Fehler-Bodies oder Exceptions liefern
- **[electron-shell/medium/security]** frontend/main.js:891 — Permission-Handler erlaubt Audio-Capture, ohne ergänzenden PermissionCheckHandler
- **[electron-shell/medium/quality]** frontend/preload.js:2266 — Mehrere POST-Bridge-Methoden ohne try/catch propagieren Netzwerkfehler als unbehandelte Rejection
- **[electron-shell/medium/security]** frontend/preload.js:2403 — backupRestoreDb ohne clientseitige Pfad-Validierung — inkonsistent zur personalOs-Härtung
- **[electron-shell/medium/bug]** frontend/main.js:349 — installLocalAuthCookie ohne Fehlerbehandlung — Cookie-Fehler kippt gesamten Startup
- **[evals/low/bug]** evals/runners/eval_trend_report.py:63 — Risk-Score kann durch Mismatch zwischen penalty und max_penalty auf 0 kollabieren
- **[evals/low/bug]** evals/runners/run_eval_suite.py:559 — ImportError der Laufzeit-Adapter wird nicht abgefangen und bricht die ganze Suite ab
- **[evals/low/bug]** evals/runners/run_manual_prompt_probe.py:528 — main() faengt FileNotFoundError und ValueError aus Parsing/Suite-Laden nicht ab
- **[evals/low/bug]** evals/adapters/base.py:117 — max_tool_count-Assertion kann bei nicht-numerischem value abstuerzen (anders als run_eval_suite)
- **[evals/medium/bug]** evals/runners/write_failure_triage.py:56 — Inkonsistente Blocking-Logik zwischen Regressions-Checker und Triage
- **[evals/medium/bug]** evals/runners/run_manual_prompt_probe.py:131 — reset_probe_state rebindet conversation_history statt das geteilte Objekt zu leeren
- **[frontend-app-shell/low/bug]** frontend/src/devtools.js:137 — Falscher Default-Git-Repo-Pfad (OneDrive\Desktop statt OneDrive - Office)
- **[frontend-app-shell/low/quality]** frontend/src/system.js:390 — toolsPct verschachtelt systemDisplayNumber(systemDisplayPercent(...)) — fehleranfaellige Doppelkonvertierung
- **[frontend-app-shell/low/bug]** frontend/src/app.js:104 — data-confirm wird fuer runTool ignoriert (Funktionssignatur ohne confirm-Parameter)
- **[frontend-app-shell/low/bug]** frontend/src/i18n/i18n.js:27 — t() interpoliert Parameter ohne Typ-/Kontextpruefung; Objekt-Parameter erzeugen '[object Object]'
- **[frontend-app-shell/low/bug]** frontend/src/devtools.js:412 — Clipboard-Schreibzugriff ohne Verfuegbarkeitspruefung in base64/uuid/hash
- **[frontend-app-shell/low/quality]** frontend/src/app.js:157 — applySendModeToggle liest lexaStorageGet erneut statt des bereits berechneten window.ctrlEnterMode
- **[frontend-app-shell/low/bug]** frontend/src/app.js:821 — Hartkodiertes attempt === 3 statt WAKEWORD_MAX_RETRIES
- **[frontend-app-shell/low/bug]** frontend/src/app_desktop_shortcuts.js:99 — Globale Tastenkuerzel pruefen Modifier nicht vollstaendig — Konflikte und ungewollte Ausloesung
- **[frontend-app-shell/low/quality]** frontend/src/app_health.js:100 — setBar-Hilfsfunktion definiert ungenutzten Parameter isGood; Sub-Setter-Logik unvollstaendig
- **[frontend-app-shell/low/bug]** frontend/src/commands.js:432 — insertCommand schreibt direkt in chatInput.value ohne Null-Pruefung und ohne Laengenlimit
- **[frontend-app-shell/low/bug]** frontend/src/app.js:266 — window.lexa.commands() Ergebnis ohne Strukturpruefung verwendet
- **[frontend-app-shell/low/bug]** frontend/src/commands.js:458 — JSON.stringify(res.data) ohne Fehlerbehandlung bei zirkulaeren/grossen Strukturen
- **[frontend-app-shell/low/quality]** frontend/src/app.js:482 — Identischer i18n-Key in beiden Zweigen einer Bedingung (toter Ternary)
- **[frontend-app-shell/low/bug]** frontend/src/system.js:803 — windowMoveAction/windowResizeAction: Number()-Konvertierung ohne NaN-Absicherung
- **[frontend-app-shell/low/bug]** frontend/src/i18n/i18n.js:60 — i18n fetch-Fallback parst src-Pfad fehleranfaellig (script[src*='i18n.js'])
- **[frontend-app-shell/low/performance]** frontend/src/app_health.js:28 — checkHealth startet Wake-Word-Auto-Restart bei JEDEM erfolgreichen Health-Tick
- **[frontend-app-shell/low/bug]** frontend/src/app_desktop_shortcuts.js:18 — Doppelte HTML-Escapes in Update-Toast (escapeHtml in textContent-Toast)
- **[frontend-app-shell/low/bug]** frontend/src/commands.js:244 — trackRecentCommand ignoriert Schreibfehler; korrupter/voller Storage bleibt unerkannt
- **[frontend-app-shell/low/bug]** frontend/src/state.js:80 — Hidden-Tab-Drosselung setzt nicht-kritische Intervalle aus, ohne bei Rueckkehr aufzuholen
- **[frontend-app-shell/medium/bug]** frontend/src/app_desktop_shortcuts.js:51 — Ctrl+9 schaltet auf eine nicht existierende View (switchView(undefined))
- **[frontend-app-shell/medium/performance]** frontend/src/app.js:596 — Poll-Intervall-Umschaltung innerhalb der Event-Schleife kann verwaiste/wechselnde Timer erzeugen
- **[frontend-app-shell/medium/bug]** frontend/src/i18n/i18n.js:104 — changeLanguage/translatePage uebersetzt dynamisch erzeugte Views nicht neu
- **[frontend-app-shell/medium/bug]** frontend/src/devtools.js:233 — git_add Ergebnis wird ignoriert — Commit laeuft auch bei fehlgeschlagenem Staging weiter
- **[frontend-chat-core/low/quality]** frontend/src/chat.js:433 — Fire-and-forget fetch auf /chat/confirm-clear ohne Fehlerbehandlung/Bridge-Nutzung
- **[frontend-chat-core/low/security]** frontend/src/chat_message_formatting.js:140 — formatMessage() ist toter Code und liefert innerHTML — Re-Injection-Risiko bei spaeterer Nutzung
- **[frontend-chat-core/low/quality]** frontend/src/chat.js:1607 — Stream-Timeout-Pruefung greift nur bei eintreffenden Chunks, nicht bei stillem Server
- **[frontend-chat-core/low/quality]** frontend/src/chat.js:1377 — Lokale Neudeklaration von sendBtn beschattet das Modul-Global im Stop-Handler
- **[frontend-chat-core/low/quality]** frontend/src/chat_state.js:86 — chatCachedHistorySnapshot validiert Array-Elemente nicht
- **[frontend-chat-core/low/bug]** frontend/src/chat.js:426 — denyAction referenziert nicht mehr existierendes .confirm-btn — toter, kaputter Pfad
- **[frontend-chat-core/low/bug]** frontend/src/chat_markdown.js:33 — Markdown-Links mit Titel ([text](url "titel")) degradieren still zu Klartext
- **[frontend-chat-core/low/quality]** frontend/src/chat.js:1508 — Tote Variable requiresConfirmation in sendMessage und ungenutzter Parameter in addMessage
- **[frontend-chat-core/medium/performance]** frontend/src/chat.js:2183 — Pro Reader-Read ein nicht abgebrochener setTimeout im Agent-Stream (Timer-Akkumulation)
- **[frontend-chat-features/low/quality]** frontend/src/chat_voice.js:679 — toggleChatView invertiert globalen Flag statt Zielzustand — Flag und DOM können auseinanderlaufen
- **[frontend-chat-features/low/bug]** frontend/src/chat_voice.js:370 — Race Condition: stale Silence-Interval kann neuen Aufnahme-Timer clearen
- **[frontend-chat-features/low/quality]** frontend/src/chat_composer_helpers.js:85 — Toter Code: composerCommandIconSvg (innerHTML-String-Variante) wird im Produktionspfad nicht genutzt
- **[frontend-chat-features/low/performance]** frontend/src/chat_agent_runs.js:200 — agentRunAttentionResolvedHistory() schreibt potenziell bei jedem Lesezugriff in den Speicher
- **[frontend-chat-features/low/quality]** frontend/src/chat_conversations.js:196 — switchConversation vermeidet Reload bei bereits aktiver Konversation nur bei notify=true — inkonsistente Guard-Logik
- **[frontend-chat-features/low/quality]** frontend/src/chat_agent_runs.js:819 — startAgentCompletionContinue: doppelter focus()-Aufruf und stilles Überschreiben eines bestehenden Composer-Entwurfs
- **[frontend-chat-features/low/quality]** frontend/src/chat_voice.js:481 — Möglicher TypeError wenn resp.body bei /chat/stream null ist
- **[frontend-chat-features/low/quality]** frontend/src/chat_conversations.js:303 — deleteConversation: Folgefehler beim Wechsel nach Löschen der aktiven Konversation bleibt dem Nutzer verborgen
- **[frontend-chat-features/low/quality]** frontend/src/chat_search.js:264 — Export-Dateiname kann 'lexa-chat-null.md' werden wenn keine aktive Konversation existiert
- **[frontend-chat-features/low/quality]** frontend/src/chat_file_upload.js:39 — dragover-Handler kann bei fehlendem dataTransfer einen Fehler werfen
- **[frontend-chat-features/medium/bug]** frontend/src/chat_voice.js:526 — Voice-Antwort wird nach dem Stream nicht persistiert (Datenverlust-Risiko)
- **[frontend-chat-features/medium/performance]** frontend/src/chat_voice.js:362 — AudioContext und Audio-Graph-Knoten der Stille-Erkennung werden nie freigegeben (Memory/Resource-Leak)
- **[frontend-css/low/bug]** frontend/src/css/components_search_memory.css:528 — Nicht definierte Custom Property var(--text-primary) (4 Verwendungen)
- **[frontend-css/low/bug]** frontend/src/css/chat.css:1057 — Nicht definierte Custom Property var(--mono) bei .agent-step
- **[frontend-css/low/bug]** frontend/src/css/overrides_chat_voice.css:650 — Nicht definierte Custom Property var(--font-main) bei .conv-agent-attention-badge
- **[frontend-css/low/bug]** frontend/src/css/views.css:70 — Dashboard-Widgets bekommen die gestaffelte Einblend-Animation nie (.dashboard-view nie gesetzt)
- **[frontend-css/low/quality]** frontend/src/css/components_shell_widgets.css:367 — Doppelte .skeleton-Definition mit unterschiedlichen Keyframes (shimmer vs. skeleton)
- **[frontend-css/low/quality]** frontend/src/css/chat.css:995 — Toter Selektor .tts-toggle.active (Element heißt .tts-toggle-btn)
- **[frontend-css/low/quality]** frontend/src/css/components_overlays.css:162 — Toter .input-hint-Stilblock (Element existiert nicht) inkl. globalem display:none !important
- **[frontend-css/medium/bug]** frontend/src/css/components_overlays.css:8 — Animation 'fadeIn' wird referenziert, ist aber nirgends als @keyframes definiert
- **[frontend-css/medium/bug]** frontend/src/css/components_overlays.css:108 — Animation 'modalSlideIn' wird referenziert, ist aber nirgends als @keyframes definiert
- **[frontend-css/medium/bug]** frontend/src/css/overrides_accessibility.css:23 — Fokus-Outline für Toggle-Switches greift nie (falscher Klassenname '.slider')
- **[frontend-personal-os-productivity/low/bug]** frontend/src/productivity.js:287 — Overdue-Berechnung verschiebt sich durch UTC/Local-Mix um die Zeitzone
- **[frontend-personal-os-productivity/low/bug]** frontend/src/productivity.js:1097 — Streak-Meilenstein-Benachrichtigung kann bei Mehrfach-Logs am selben Tag mehrfach feuern
- **[frontend-personal-os-productivity/low/quality]** frontend/src/personal_os.js:197 — decidePersonalOsDraft setzt isDeciding vor dem Modal, blockiert Auto-Refresh unbegrenzt
- **[frontend-personal-os-productivity/medium/bug]** frontend/src/personal_os_prompt_helpers.js:24 — compacted-Flag immer false bei deutscher UI (String-Match auf englischen Literal)
- **[frontend-personal-os-productivity/medium/bug]** frontend/src/productivity.js:1170 — Live-Zeittracking-Anzeige friert ein (kein Sekunden-Tick, kein Refresh-Intervall der Produktivitäts-View)
- **[frontend-personal-os-productivity/medium/bug]** frontend/src/productivity.js:308 — Pomodoro-Abschluss-Alarm (Beep/Toast) entfällt, wenn der Nutzer die View verlässt
- **[frontend-views/low/bug]** frontend/src/memory.js:335 — updateMemoryGraphInspector kann bei undefined graph crashen
- **[frontend-views/low/bug]** frontend/src/modals.js:249 — showToast loggt bei fehlendem Toast-Container nicht in die Notification-Center
- **[frontend-views/low/quality]** frontend/src/settings.js:1322 — Lizenzschlüssel-Validierung ohne Toleranz für interne Whitespaces
- **[frontend-views/low/bug]** frontend/src/settings.js:1290 — Trial-Fortschrittsbalken zeigt geklemmten Tageswert in CSS, aber ungeklemmten im Text
- **[frontend-views/low/bug]** frontend/src/settings.js:1360 — saveProfile crasht bei fehlenden Profil-Eingabefeldern und hat keine Fehlerbehandlung
- **[frontend-views/low/bug]** frontend/src/memory.js:1068 — clearClipboardHistory ohne Fehlerbehandlung führt zu unbehandelter Promise-Rejection
- **[frontend-views/low/bug]** frontend/src/settings.js:1024 — refreshSettingsView wird nach Secret-Aktionen ohne await/Fehlerbehandlung neu getriggert
- **[frontend-views/low/quality]** frontend/src/dashboard.js:263 — Batterie-Ton invertiert Schwellenwert über einen Hack-Wert statt klarer Logik
- **[frontend-views/low/quality]** frontend/src/settings.js:648 — runSystemDiagnostics liest Status aus textContent statt aus dem Readiness-Modell
- **[frontend-views/low/quality]** frontend/src/modals.js:724 — Command-Palette ruft Aktionen per Window-Lookup auf — fragiler String-basierter Dispatch
- **[frontend-views/medium/bug]** frontend/src/settings.js:205 — TTS-Status schreibt auf nicht existierende ID und kollidiert mit ElevenLabs-Status auf el-status
- **[frontend-views/medium/bug]** frontend/src/settings.js:419 — AI-Readiness-Karte zeigt fest verdrahtetes '/4', obwohl nur 1 Provider (gemini) bewertet wird
- **[frontend-views/medium/security]** frontend/src/memory.js:1270 — trackClipboard liest System-Zwischenablage ohne Nutzer-Trigger und kann sensible Daten persistieren
- **[personal-os-sdk/low/quality]** personal_os/07_Automations/Workflows/raw-inbox-worker/src/processor.ts:320 — AbortController-Timeout deckt das Lesen des Response-Bodys nicht zuverlaessig ab
- **[personal-os-sdk/low/bug]** personal_os/07_Automations/Workflows/raw-inbox-worker/src/worker.ts:250 — Worker ignoriert das truncated-Flag von os_read_raw_file - >50 KB-Dateien werden stillschweigend gekuerzt verarbeitet
- **[personal-os-sdk/low/bug]** personal_os/00_System/SDK/os-sdk/src/ast.ts:22 — checkTask/uncheckTask markieren nur das erste Treffer-Item - mehrere gleichnamige Tasks bleiben unveraendert
- **[personal-os-sdk/low/security]** personal_os/11_Integrations/MCP/os-mcp-server/src/index.ts:530 — Keine Lese-Zugriffsbeschraenkung: os_read_file/os_query_index liefern beliebige .md-Dateien unter OS-Root
- **[personal-os-sdk/low/quality]** personal_os/07_Automations/Workflows/raw-inbox-worker/src/index.ts:112 — Watch-Loop ohne Fehler-Backoff und ohne sauberes Shutdown
- **[personal-os-sdk/low/quality]** personal_os/07_Automations/Workflows/raw-inbox-worker/src/mcp.ts:40 — textContent liest nur content[0] - Tool-Ergebnisse mit fuehrendem Nicht-Text-Block schlagen fehl
- **[personal-os-sdk/low/bug]** personal_os/11_Integrations/MCP/os-mcp-server/src/index.ts:798 — truncated-Flag liefert False Positives bei exakt erreichtem Limit
- **[personal-os-sdk/low/quality]** personal_os/00_System/SDK/os-sdk/src/draft-decision.ts:67 — Tote AST-Mutationen: checkTask/uncheckTask werden durch parseMarkdownBody ueberschrieben
- **[personal-os-sdk/low/quality]** personal_os/00_System/SDK/os-sdk/src/write.ts:92 — writeMarkdown mutiert das uebergebene file-Objekt (frontmatter) als Seiteneffekt
- **[personal-os-sdk/low/quality]** personal_os/00_System/SDK/os-sdk/src/draft-apply.ts:137 — writeAtomic-Temp-Dateiname kollidiert bei zwei Anwendungen in derselben Millisekunde
- **[personal-os-sdk/low/quality]** personal_os/00_System/SDK/os-sdk/src/write.ts:43 — Zwei nicht deckungsgleiche Memory-Level-Vokabulare; targetMemoryLevel mappt 'session'/'volatile' still auf 'episodic'
- **[personal-os-sdk/low/bug]** personal_os/07_Automations/Workflows/raw-inbox-worker/src/worker.ts:169 — Run-Log-relativePath ist hartkodiert und ignoriert konfigurierbares runLogDir
- **[personal-os-sdk/medium/bug]** personal_os/00_System/SDK/os-sdk/src/draft-apply.ts:327 — Malformed Draft-Envelope-JSON wirft ungefangen und verhindert markEnvelopeFailed/Legacy-Fallback
- **[personal-os-sdk/medium/performance]** personal_os/00_System/SDK/os-sdk/src/events.ts:21 — events.jsonl waechst unbegrenzt - keine Rotation/Groessenbegrenzung
- **[personal-os-sdk/medium/bug]** personal_os/00_System/SDK/os-sdk/src/draft-decision.ts:84 — decideDraft bricht bei korruptem Envelope ab, obwohl Approval/Rejection rein checklistenbasiert moeglich waere
- **[personal-os-sdk/medium/bug]** personal_os/00_System/SDK/os-sdk/src/markdown.ts:23 — parseMatter-Fallback fuer H1-vorangestelltes Frontmatter ordnet Dokumentinhalt um
- **[personal-os-sdk/medium/performance]** personal_os/11_Integrations/MCP/os-mcp-server/src/index.ts:369 — draftHistory liest die komplette events.jsonl bei jedem Aufruf in den Speicher
- **[voice-pipeline/low/quality]** voice/conversation.py:34 — Toter Code: _tts_executor und _collect_tts_results werden nie verwendet
- **[voice-pipeline/low/bug]** voice/wakeword.py:256 — Wake-Cooldown verwirft inline mitgesprochenes Kommando bei schneller Folgeaktivierung
- **[voice-pipeline/low/quality]** voice/conversation.py:430 — Leeres STT-Ergebnis nach Barge-in/Turn beendet Konversation kommentarlos
- **[voice-pipeline/low/quality]** voice/realtime.py:57 — Unerreichbarer Codepfad: runtime_implemented ist konstant False, ganze Zweige sind toter Code
- **[voice-pipeline/low/bug]** voice/playback.py:141 — Ungenutzter Parameter timeout_s in _record_rest — Timeout greift nicht
- **[voice-pipeline/low/bug]** voice/conversation.py:196 — Synthetischer Fallback-Tool-Call extrahiert Argumente fragil und kann ungueltige Werte erzeugen
- **[voice-pipeline/low/bug]** voice/wakeword_engines.py:239 — openWakeWord: threshold-Map wird bei patience<=1 nicht an predict uebergeben
- **[voice-pipeline/low/bug]** voice/tts.py:277 — SAPI-Pfad-Umschreibung kann Schreibpfad und erwarteten output_path divergieren lassen
- **[voice-pipeline/low/quality]** voice/conversation.py:360 — _turn_legacy gibt potenziell [None] in audio_paths-Verarbeitung weiter
- **[voice-pipeline/low/bug]** voice/wakeword_engines.py:204 — openWakeWord: missing-Pfad-Pruefung bricht vor Auto-Download ab
- **[voice-pipeline/low/bug]** voice/conversation.py:67 — _clean_for_tts wandelt jede Zeile, die mit '-' beginnt, in '. ' — entfernt legitime Inhalte
- **[voice-pipeline/low/bug]** voice/tts.py:156 — Cache-Hash beruecksichtigt die Sprache nicht — Sprachwechsel liefert falsches Cache-Audio
- **[voice-pipeline/medium/performance]** voice/tts.py:51 — _get_key fragt Keyring bei jedem Aufruf erneut ab, wenn kein Key gesetzt ist (blockierendes I/O)
- **[voice-pipeline/medium/bug]** voice/wakeword.py:160 — _get_conversation_engine erzeugt bei jedem Aufruf eine neue Engine — verworfene Konversationshistorie
- **[voice-pipeline/medium/bug]** voice/tts.py:516 — Cache-Pruning-Race: _prune_cache kann gerade in Arbeit befindliche Chunk-Dateien anderer Threads loeschen
- **[voice-pipeline/medium/bug]** voice/tts.py:454 — except (ImportError, Exception) verschluckt ALLE Fehler stillschweigend bei MP3-Konkatenation
- **[voice-pipeline/medium/performance]** voice/stt.py:68 — _get_key fragt Keyring bei fehlendem Key bei jedem Aufruf erneut ab
- **[voice-pipeline/medium/bug]** voice/playback.py:34 — Barge-in-Schleife endet faelschlich, sobald MCI kurzzeitig nicht 'playing' meldet
- **[voice-pipeline/medium/performance]** voice/conversation.py:283 — Streaming-TTS-Pipeline fehlt: nur eine einzige TTS-Datei fuer gesamten Text statt satzweiser Audio-Stuecke
- **[voice-pipeline/medium/bug]** voice/conversation.py:421 — Barge-in nutzt self._noise_floor statt der lokal kalibrierten noise_floor
- **[voice-pipeline/medium/performance]** voice/playback.py:95 — Barge-in-Aufnahme erzeugt pro 30ms-Chunk einen neuen sd.rec-Stream — Luecken und Overhead
- **[website/low/quality]** dashboard.js:416 — Passwortänderung ohne Mindestlängen-Validierung im JS — Supabase-Rohfehler wird angezeigt
- **[website/low/quality]** dashboard.js:212 — loadSubscriptionInfo verwendet .single() statt .maybeSingle() — erzeugt Fehler bei Free-Nutzern
- **[website/low/performance]** landing.js:84 — Mehrere ungedrosselte mousemove-Listener (Spotlight, Cursor-Glow, pro Button) belasten den Main-Thread
- **[website/low/bug]** dashboard.html:18 — og:image verweist auf nicht vorhandene Datei og-image.jpg
- **[website/low/performance]** landing.js:36 — scroll-Listener ohne Drosselung in initTubelightNav und initScrollEffects
- **[website/low/quality]** dashboard.html:128 — Download-Links zeigen auf privates/nicht existierendes GitHub-Release
- **[website/low/quality]** auth.js:271 — Recovery-Erkennung über hash.includes('recovery') ist zu breit und redundant
- **[website/low/bug]** auth.js:290 — Recovery-Formular bei mehrfacher Auslösung doppelt eingefügt und doppelte Submit-Listener
- **[website/medium/bug]** auth.html:144 — Referenziertes Skript config.runtime.js existiert nicht (404 bei jedem Seitenaufruf)
- **[website/medium/bug]** dashboard.html:158 — Doppelter i18n-Key price_pro_f2 im Pro-Upgrade-Modal erzeugt zwei identische Listeneinträge
- **[website/medium/security]** index.html:3 — index.html besitzt keine Content-Security-Policy (im Gegensatz zu auth/dashboard)

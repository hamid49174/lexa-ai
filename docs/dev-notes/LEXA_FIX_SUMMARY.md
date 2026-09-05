# Lexa — Komplett-Fix Abschlussbericht (2026-06-14)

## Was gemacht wurde
- Vollscan (28 Bereiche, 471 Funde) -> dateiweise confirm-then-fix (154 Agents, Opus 4.8).
- **351 Funde behoben**, 27 waren bereits ok, 6 Fehlalarme erkannt.
- 5 Test-Regressionen aus den Fixes gezielt zurueckgenommen (engine/file_tools, voice/conversation, hermes_adapter, productivity, workflows) — andere Fixes der Dateien blieben erhalten.
- Provider auf **Gemini-only (gemini-3.5-flash)** umgestellt; Gemini-API-Key getestet (funktioniert).
- **Supabase**: protect_sensitive_profile_fields nutzt jetzt JWT-Rolle statt current_user (Self-Upgrade-Luecke geschlossen). Liegt in lexa-website (kein Git) — **muss gegen die Supabase-DB ausgefuehrt werden**, damit es wirkt.

## Teststatus
- **1648 Tests gruen.**
- 2 rot: tests/test_manual_prompt_probe.py — VORBESTEHEND, weil docs/product/manual_lexa_prompt_suite.md im Working-Tree geleert ist (0 Bytes, war schon vor der Arbeit so). Wiederherstellen mit: git checkout -- docs/product/manual_lexa_prompt_suite.md (bewusst NICHT automatisch gemacht — deine lokale Aenderung).
- compileall (backend/companion/voice) = 0 Fehler.

## Vollstaendige Fund-/Fix-Listen
- Alle 471 Funde: LEXA_FULLSCAN_FINDINGS.md
- Runde-1-Status + Gemini-Umstellung + Backend-Reuse-Hinweis: LEXA_AUDIT_STATUS.md

---
# OFFENE PUNKTE (von dir zu entscheiden / koordiniert nachzuziehen)

## NEEDS_COORDINATION — dateiuebergreifend (19)

### backend/agent_loop.py:409
**Pending-Confirmation ist globaler Singleton-State — gleichzeitige Agent-Runs ueberschreiben sich**
Nicht geaendert. Der Fix erfordert run-/session-gebundenen State in backend/shared.py (_pending_confirmation/set_pending_confirmation) und betrifft router_chat.py sowie router_agent.py, die dieselbe globale Funktion nutzen. Das ist explizit der dateiuebergreifende Pending-Confirmation-Bereich, der separat koordiniert wird (Aufgaben-Punkt 6).

### backend/agent_loop.py:1163
**Forced-First-Tool needs_confirmation: kein Reset des globalen Pending-State, fragile Status-Kopplung**
Nicht geaendert. Der konkrete, real wirksame Fix (clear_pending_confirmation im router_agent finally-Block bzw. bei CancelledError) liegt ausserhalb dieser Datei und gehoert zum koordinierten Pending-Confirmation-Bereich (Punkt 6). Die in-file genannte Status-Kopplung ist heute kein Bug: die nachfolgende while-Schleife guarded korrekt auf run.status=='running'; eine reine Restrukturierung waere riskant ohne Verhaltensgewinn.

### backend/shared.py:29
**Race Condition: Pending-Confirmation-State ohne Lock zwischen nebenlaeufigen Chat-Requests**
Keine Aenderung. Befund am echten Code bestaetigt (shared.py Z.24-53: _pending_confirmation/_pending_confirmation_ts sind modulglobale Variablen, get/set/clear mutieren sie ohne jeden Lock). Der verifizierte Fix verlangt jedoch eine atomare pop-Operation, deren Wirkung NUR greift, wenn die Aufrufer angepasst werden: router_chat.py liest in Z.480-487, Z.1157-1163 und Z.1459-1465 erst get_pending_confirmation() und ruft danach getrennt clear_pending_confirmation()+_execute_pending_confirmation() auf; ausserdem konsumieren agent_loop.py (Z.407-409), router_agent.py (Z.134-141) und ai_engine.py (Z.3705-3706) denselben State. Das ist exakt der in den Orchestrator-Anweisungen (Punkt 6) als dateiuebergreifend markierte Pending-Confirmation-Race (shared.py betrifft agent_loop.py/router_chat.py/router_agent.py). Ein reines Hinzufuegen eines Locks/einer take_pending_confirmation() in shared.py ohne Umstellung der Aufrufer wuerde die Doppelausfuehrungs-Race NICHT beseitigen und einen halbfertigen Zustand erzeugen. Daher bewusst nicht in dieser Datei umgesetzt.

### backend/shared.py:24
**Globaler Pending-Confirmation-State: ein einziger Slot, kein Lock, Race zwischen get/clear/execute**
Keine Aenderung. Identischer Befund wie Z.29 (Duplikat aus anderem Audit-Bereich). Am echten Code bestaetigt: Einzel-Slot _pending_confirmation ohne Lock und ohne Isolation pro Konversation. Der vorgeschlagene Fix (atomare get+clear pop-Operation, bzw. State pro Konversations-ID) erfordert zwingend Aenderungen an den Aufrufern in router_chat.py (get->clear->execute in Z.1157-1163 / Z.1459-1465 / Z.480-487) sowie Beruecksichtigung von agent_loop.py, router_agent.py und ai_engine.py. Damit faellt der Befund unter die in den Anweisungen (Punkt 6) explizit dateiuebergreifend zu koordinierende Pending-Confirmation-Race und wird nicht isoliert in shared.py geaendert, um keinen inkonsistenten Teil-Fix einzufuehren.

### backend/mcp_registry.py:432
**get_merged_tool_definitions ist toter Code — MCP-Tools erreichen den LLM nie**
Nicht geändert. Per Grep über das gesamte Projekt bestätigt: get_merged_tool_definitions() hat keinen einzigen produktiven Aufrufer (nur Treffer in _fullscan_findings.json und LEXA_FULLSCAN_FINDINGS.md). Der Befund ist real. Die im fix-Feld vorgeschlagene Lösung (MCP-Tools im Tool-Aufbau von ai_engine.py einhängen + Dispatch-Zweig 'mcp_'-Prefix in agent_loop.py, der mcp_registry.call_tool() aufruft) ist explizit dateiübergreifend und laut Auftrag (Punkt 6: 'MCP/Plugin-Tools ans LLM verdrahten' — betrifft mcp_registry.py/plugin_manager.py/ai_engine.py/action_executor.py) separat zu koordinieren. Die Alternative (Methode löschen + Doku 'MCP rein REST-basiert') ist eine Produktentscheidung, die das künftige Verdrahten verhindern würde und nicht rein in dieser Datei sinnvoll entscheidbar ist. Daher bewusst keine Änderung, um die Verdrahtungs-Koordination nicht zu präjudizieren.

### backend/plugin_manager.py:975
**Plugin-Tools (z.B. web_search) werden dem LLM nie angeboten und sind im Agent-Loop nicht ausfuehrbar**
Nicht umgesetzt. Laut Auftrag (Punkt 6) ist 'MCP/Plugin-Tools ans LLM verdrahten' ein dateiuebergreifendes Thema (betrifft mcp_registry.py/ai_engine.py/action_executor.py/agent_loop.py). Die Verdrahtung kann nicht allein in plugin_manager.py erfolgen: get_plugin_tools() muesste in den LLM-Toolsatz gemergt und validate_tool_arguments/Dispatch in agent_loop.py angepasst werden. Wird separat koordiniert behoben.

### frontend/src/chat.js:426
**denyAction referenziert nicht mehr existierendes .confirm-btn — toter, kaputter Pfad**
Nicht entfernt. denyAction/confirmAction sind NICHT rein lokal entfernbar: app_actions.js (Z.142/143) dispatcht beide Faelle und tests/electron_confirmation_click_smoke.js testet confirmAction explizit als 'legacy fail-closed' Handler (clearCalls===1). Entfernen wuerde app_actions.js + Tests brechen (regelwidrig, nur chat.js darf geaendert werden). Der `.confirm-btn`-Aufruf ist durch Optional-Chaining harmlos (kein echter Crash), aber die Bereinigung erfordert datuebergreifende Koordination.

### backend/router_chat.py:437
**Hermes-Commit: set_pending_confirmation nach clear ohne Lock — Pending kann verloren gehen**
Nicht geaendert. Dies ist der dateiuebergreifende Pending-Confirmation-Race (globaler State in shared.py; betrifft agent_loop.py/router_chat.py/router_agent.py) und ist laut Vorgabe separat zu koordinieren. Der Fix verweist selbst auf Finding shared.py:29.

### backend/router_conversations.py:86
**load_conversation ueberschreibt aktive History ohne Pending-Confirmation/Cache-Reset**
Nicht geändert. Der vorgeschlagene Fix erfordert den Aufruf von clear_pending_confirmation()/clear_response_cache() auf globalem Zustand, der in backend/shared.py lebt (_pending_confirmation ab Zeile 24, set/get_pending_confirmation) und mit agent_loop.py/router_chat.py/router_agent.py geteilt wird. Das ist der unter Anweisung Punkt 6 ausdrücklich als dateiübergreifend/koordiniert-zu-behebend gelistete Pending-Confirmation-Race. Eine korrekte Lösung muss die Semantik (TTL, Clear-Helper, Cache-Signaturen) global abstimmen und kann nicht sicher rein in dieser Datei erfolgen.

### backend/startup_diagnostics.py:222
**build_startup_diagnostics: /health/startup ungecacht und ohne Rate-Limit — teure Probes bei Polling**
Keine Änderung an startup_diagnostics.py. Das Finding ist real (der Endpoint /health/startup in router_health.py ruft build_startup_diagnostics ohne Caching/Rate-Limit auf), aber die korrekte Lösung ist dateiübergreifend und liegt außerhalb der erlaubten Datei: 1) Der projekteigene Pattern cached den /health-Endpoint im Router-/main.py-Layer (cache_get/cache_set + CACHE_HEALTH_TTL) und hält den Builder als reine Funktion — analog gehört das TTL-Caching für /health/startup in backend/router_health.py, NICHT in den Builder. 2) Ein interner TTL-Cache im Builder wurde testweise implementiert und brach die Test-Isolation: tests/test_router_health.py ruft build_startup_diagnostics() zweimal pro Prozess mit unterschiedlichen monkeypatch-Daten auf; der zweite Test erhielt das gecachte 'ready'-Paket des ersten (verifizierter Fehlschlag: assert 'ready' == 'attention'). Daher wurde der Versuch vollständig zurückgerollt. 3) check_rate_limit (rate-limit-Teil des Fixes) benötigt den FastAPI-Request-Kontext und existiert nur im Endpoint-Layer (router_health.py). Beide Teile des vorgeschlagenen Fixes (Caching + Rate-Limit) müssen in backend/router_health.py erfolgen und separat koordiniert werden.

### backend/router_vision.py:209
**GIF/BMP-Uploads werden mit falschem image/png-MIME an Provider gesendet**
Nicht geaendert. Der Fund ist real (analyze_uploaded_file akzeptiert image/gif und image/bmp ueber ALLOWED_IMAGE_TYPES), aber die fehlerhafte MIME-Deklaration entsteht ausschliesslich in backend/vision.py: _image_to_base64_url (Z.234-237) setzt den Praefix hart auf 'data:image/png;base64,', und _analyze_image_sync (Z.402) ruft dies fuer alle Bytes auf. analyze_image (vision.py) nimmt nur image_input:str|bytes ohne MIME/Typ-Parameter entgegen. Der vom Audit vorgeschlagene Fix (MIME anhand der Magic Bytes setzen bzw. Re-Encoding via PIL) ist nur in vision.py umsetzbar. Da ich laut Auftrag ausschliesslich router_vision.py aendern darf und keine oeffentliche Signatur brechen soll, ist dieser Fix dateiuebergreifend zu koordinieren (vision.py).

### companion/desktop_control.py:309
**_window_capture_origin: FindWindowW(None, None) liefert nur ein Top-Level-Fenster, GetWindow-Kette kann Match verfehlen**
Nicht geaendert. Der Fund ist real (OCR-Capture und Origin-Berechnung loesen das Fenster zweimal unabhaengig auf; bei Z-Order-Aenderung kann ein anderes gleichnamiges Fenster getroffen werden). Der korrekte Fix erfordert laut fix-Feld, dass ocr._capture_for_ocr den verwendeten hwnd/Origin zurueckgibt und desktop_click_text genau diesen Wert nutzt. Das ist eine dateiuebergreifende Aenderung (companion/ocr.py + diese Datei) und laesst sich nicht rein in desktop_control.py loesen — jeder Workaround hier wuerde das Fenster weiterhin unabhaengig erneut aufloesen.

### companion/ocr.py:142
**_capture_for_ocr: fehleranfällige Window-Enumeration mit Substring-Match und stillem Vollbild-Fallback**
Nicht geändert. Der Fund ist real (GW_HWNDNEXT-Schleife + Substring-Match + stiller all_screens-Fallback). Der vorgeschlagene Fix (EnumWindows, exakter/präfix-basierter Match, harter Fehler statt Vollbild-Fallback) lässt sich aber NICHT korrekt allein in ocr.py umsetzen: companion/desktop_control.py::_window_capture_origin (Zeile 293-334) spiegelt die exakte Lookup-Logik von _capture_for_ocr absichtlich (sichtbare Fenster, case-insensitiver Substring-Match, GW_HWNDNEXT, Tiny-Window- und No-Match-Vollbild-Fallback), um denselben hwnd aufzulösen und OCR-Bbox-Koordinaten korrekt in absolute Bildschirmkoordinaten umzurechnen (siehe Docstring-Kommentar dort). Eine Änderung des Enumerations-/Match-/Fallback-Verhaltens in ocr.py würde diese Spiegelung desynchronisieren und zu Fehlklicks führen. Daher dateiübergreifende Koordination nötig; bewusst unverändert gelassen.

### frontend/src/chat_composer_helpers.js:85
**Toter Code: composerCommandIconSvg (innerHTML-String-Variante) wird im Produktionspfad nicht genutzt**
Befund am echten Code bestaetigt: composerCommandIconSvg (String-/innerHTML-Variante) wird per projektweitem Grep nirgends im Produktionscode aufgerufen — produktiv nutzt nur chat_composer_palette.js:52 die DOM-Variante createComposerCommandIconElement. composerCommandIconSvg wird AUSSCHLIESSLICH vom Test tests/test_chat_send_guards.js referenziert: Zeile 128 extrahiert die Funktion per Name aus dem Quelltext (extractFn), Zeile 158 exportiert sie aus der Sandbox, Zeile 339 assertet ihren SVG-Output. Der korrekte Fix (Funktion entfernen + Test auf createComposerCommandIconElement umstellen) ist zwingend dateiuebergreifend: Wuerde ich die Funktion allein in chat_composer_helpers.js loeschen, bricht extractFn(...,'composerCommandIconSvg') und damit der gesamte Test — eine Regression, die ich unter der Single-File-Vorgabe nicht beheben darf (Aenderung an tests/ untersagt). Zudem laeuft die Test-Sandbox ohne DOM (kein document/createElementNS-Stub vorhanden, geprueft), die DOM-Variante ist dort gar nicht ausfuehrbar — die im Befund vorgeschlagene Test-Migration braucht zusaetzlich einen DOM-Stub. Daher KEINE Aenderung an chat_composer_helpers.js vorgenommen; Loeschung + Test-Anpassung muessen gemeinsam in einer koordinierten Aenderung ueber chat_composer_helpers.js + tests/test_chat_send_guards.js erfolgen.

### frontend/src/app.js:104
**data-confirm wird fuer runTool ignoriert (Funktionssignatur ohne confirm-Parameter)**
Real bestaetigt, aber der betroffene Code liegt NICHT in frontend/src/app.js: Der Aufruf runTool(cmd, params, ds.confirm === 'true') steht in frontend/src/app_actions.js:104, die ignorierende Definition async function runTool(command, params = {}) in frontend/src/commands.js:497 (intern stets window.lexa.execute(command, params, true)). Eine korrekte Behebung betrifft app_actions.js + commands.js + die data-confirm-Attribute in index.html und ist somit dateiuebergreifend. Da ich ausschliesslich app.js aendern darf, hier nicht angefasst.

### frontend/src/productivity.js:308
**Pomodoro-Abschluss-Alarm entfaellt beim Verlassen der View**
Nicht geaendert. Der Pomodoro-Tick laeuft ueber das Intervall "pomodoro", das in app.js switchView (Z.325) explizit gecleart wird; der Abschluss-Check (playBeep/showToast bei remaining<=0) sitzt im Tick. Eine korrekte Behebung erfordert, den Tick aus der View-Lifetime herauszuloesen (Verwaltung in app.js init statt switchView, bzw. switchView von der Loeschung auszunehmen) und beruehrt zusaetzlich state.js (isCritical-Allowlist enthaelt "pomodoro", damit der Tick bei verstecktem Tab weiterlaeuft). Ein reines In-Datei-Workaround (Intervall umbenennen) wuerde die bestehende Loesch-Logik in app.js toter Code machen und die isCritical-Behandlung verlieren. Daher dateiuebergreifend zu koordinieren.

### frontend/src/personal_os_review_helpers.js:41
**Toter Code: renderPosApplyHint und renderPosPromptHint (HTML-String-Varianten) werden nirgends gerendert**
Keine Aenderung vorgenommen. Der Fund ist real verifiziert: Im produktiven Renderpfad (personal_os_renderers.js Z.444-445) werden ausschliesslich die DOM-Factories createPosPromptHint/createPosApplyHint genutzt; eine Grep ueber das gesamte frontend-Verzeichnis zeigt, dass renderPosApplyHint (Z.41) und renderPosPromptHint (Z.54) nur definiert, aber nirgends ueber innerHTML o.ae. aufgerufen werden. Die einzigen Referenzen liegen in Testdateien, die die Existenz der Funktionen hart pruefen: tests/test_frontend_script_order_static.js:187 (assert auf includes("function renderPosApplyHint(") und includes("function renderPosPromptHint(")) sowie tests/electron_personal_os_handoff_smoke.js:134-135 (typeof renderPosPromptHint/renderPosApplyHint === "function"). Zusaetzlich Doku-Referenzen in docs/product/frontend_modularization_plan.md und core_flow_coverage_plan.md. Das Entfernen wuerde diese Tests sofort brechen. Der Fix-Vorschlag selbst verlangt explizit, die Test-/Doc-Erwartungen mit anzupassen — also ein dateiuebergreifender Eingriff. Da ich laut Vorgabe AUSSCHLIESSLICH personal_os_review_helpers.js aendern darf und Tests/Docs nicht beruehren darf, ist eine sichere, vollstaendige Entfernung in dieser Datei allein nicht moeglich. Daher als needs_coordination markiert: Entfernung der beiden Funktionen plus Anpassung von test_frontend_script_order_static.js, electron_personal_os_handoff_smoke.js und den beiden Doku-Dateien muss koordiniert in einem Schritt erfolgen.

### frontend/preload.js:2204
**getAutostart nutzt synchrones ipcRenderer.sendSync — blockiert den Renderer-Mainthread**
Nicht geändert. Der Fund ist real, aber die Umstellung auf ipcRenderer.invoke (async) ist nicht innerhalb von preload.js allein korrekt umsetzbar: getAutostart() wird synchron in frontend/src/settings.js:121 konsumiert (autostartToggle.checked = window.lexa.getAutostart()), der Main-Handler ist safeIpcOn('get-autostart', ...event.returnValue) in frontend/main.js:1376, ein Static-Test (tests/test_electron_main_static.js:107) prüft genau diese safeIpcOn/returnValue-Form, und ~15 Smoke-Tests nutzen ipcMain.on('get-autostart', e=>{e.returnValue=...}). Eine korrekte Lösung erfordert koordinierte Änderungen in main.js (safeIpcOn→safeIpcHandle), settings.js (Caller await) und mehreren Tests — außerhalb dieser Datei.

### auth.html:144
**Referenziertes Skript config.runtime.js existiert nicht (404 bei jedem Seitenaufruf)**
Keine Änderung an auth.html. Der Befund ist real (config.runtime.js fehlt; nur config.runtime.example.js und config.js existieren, bestätigt per Glob/Grep), aber der korrekte Fix liegt vollständig außerhalb dieser Datei. Die Skript-Referenz <script src="config.runtime.js"> ist BEABSICHTIGT: config.js liefert Defaults über window.LEXA_CONFIG, config.runtime.js (in .gitignore, beim Deploy aus config.runtime.example.js erzeugt) merged die echten öffentlichen Keys via Spread (...window.LEXA_CONFIG). validate-static.mjs:105 nimmt config.runtime.js bewusst von der 'missing script'-Prüfung aus — der fehlende Zustand ist während der Entwicklung akzeptiert. Das im Fund vorgeschlagene 'fix' (config.runtime.js mit echten Keys anlegen und ausliefern + Deploy-Prozess absichern) ist durch meine Vorgaben verboten (nur auth.html editierbar, keine neuen Config-/Secret-Dateien, keine Fremddateien) und betrifft zudem dateiübergreifend dashboard.html:212 (identische Referenz) sowie den Deploy-Prozess. Ein Entfernen der Zeile wäre falsch: es würde den Runtime-Config-Override in Produktion (wo die Datei legitim vorhanden ist) zerstören und die App funktionsunfähig machen. Daher needs_coordination statt einer riskanten In-File-Änderung.

## NEEDS_HUMAN — Entscheidung noetig (42)

### backend/router_personal_os.py:1442
**Verbesserung: maxFiles-Obergrenzen zwischen Endpoint und Action-Layer inkonsistent**
Bestätigt real: graph_os erlaubt maxFiles le=400, während personal_os_actions.py:498 via _as_int(...,80,1,200) auf 200 deckelt. Der im Finding empfohlene Fix (zentrale Konstanten MAX_GRAPH_FILES/MAX_QUERY_MATCHES in einem gemeinsamen Modul, in beiden Pfaden referenziert) ist explizit dateiübergreifend (router_personal_os.py + personal_os_actions.py + neues Shared-Modul) und damit außerhalb des erlaubten Scopes (nur diese Datei). Eine rein lokale Reduktion von le=400 auf le=200 würde den öffentlichen REST-Vertrag ändern UND das eigentliche Ziel (Single Source of Truth) verfehlen, daher nicht geraten. Keine Änderung vorgenommen.

### frontend/src/chat.js:1607
**Stream-Timeout-Pruefung greift nur bei eintreffenden Chunks, nicht bei stillem Server**
Nicht geaendert. Der 'stiller-Server'-Fall ist real durch den separaten _streamTimeout (45s, abortet das fetch-Signal) abgedeckt — das Sicherungsnetz funktioniert, ein Defekt liegt also nicht vor. Die vorgeschlagene Konsolidierung (reader.read() per Promise.race) ist ein optionaler Refactor zweier funktionierender Timeout-Mechanismen mit Verhaltensrisiko; gemaess Regel #4 als needs_human markiert statt zu raten.

### frontend/src/chat.js:489
**generateSuggestions: extrem lange Heuristik mit Duplikaten in Keyword-Listen**
Nicht umgesetzt. Der vorgeschlagene table-driven Rewrite/Auslagern von ~800 Zeilen handgepflegter Keyword-Heuristik ist ein umfangreicher, verhaltenssensibler Refactor (subtile Reihenfolgen-/Matching-Effekte). Funktional ist der Code korrekt; die Aenderung ist Geschmackssache/riskant -> gemaess Regel #4 needs_human statt zu raten.

### frontend/src/memory.js:815
**Gesamte Memory-View-Logik ist toter, unerreichbarer Code nach frühem return**
Bestätigt: refreshMemoryView() ruft Z.815 refreshMemoryGraphView() und sofort return (Z.816); der gesamte Rumpf Z.818–1004 ist unerreichbar. Projektweit verifiziert, dass die referenzierten DOM-IDs (memory-stats-grid, notes-list, snippets-list, ai-status-panel, routines-list, clipboard-history-list, memory-cleanup-info) NUR im toten Code selbst vorkommen und nicht mehr in index.html existieren. Nicht geändert: Die korrekte Auflösung ist eine Produktentscheidung (Memory-View bewusst graph-only vs. Panels wiederherstellen). Die nicht-destruktive Variante (Wiederverdrahtung der Container/Buttons) erfordert index.html + app_actions.js, die laut Auftrag tabu sind. Das Löschen des ~187-Zeilen-Rumpfs würde zusätzlich eine ganze Kaskade von Hilfs-/Feature-Funktionen (createMemoryInfoCard, createMemoryProviderCard, memoryDisplayCount, createMemoryEmptyState, renderClipboardPrivacyPrompt, renderClipboardEntries, revealClipboardHistory sowie effektiv openNoteModal/useSnippet/deleteSnippet/toggleRoutine) verwaisen lassen und damit reale Features unwiderruflich aus dem UI entfernen — zu groß/riskant ohne Abstimmung, daher kein Raten.

### frontend/src/memory.js:1074
**Verwaiste Feature-Funktionen createNote/createSnippet/createRoutine/showDiagnostics/clearClipboardHistory nicht mehr aufrufbar**
Bestätigt per projektweitem Grep: createNote (1074), createSnippet (1279), createRoutine (1145), showDiagnostics (1381) und clearClipboardHistory (1068) werden nirgends per data-action/app_actions.js oder index.html aufgerufen (nur runMemoryCleanup ist über index.html:1236 verdrahtet; quickCreateNote über app_desktop_shortcuts.js:154). Nicht geändert: Die saubere Lösung (Buttons/Actions in der Memory-View-HTML + app_actions.js wieder einhängen) erfordert genau die laut Auftrag tabuisierten Dateien; eine reine In-Datei-Verdrahtung ist nicht möglich. Das Entfernen würde fertige Features (Notiz/Snippet/Routine anlegen, Diagnostics, Clipboard leeren) abschneiden — Produktentscheidung, daher needs_human statt raten.

### frontend/main.js:1262
**Presence-/Confirmation-Gate ist kein echtes User-Presence-Gate (Defense-in-Depth-Luecke)**
Nicht geaendert. Das Finding ist real (kein dialog.showMessageBox im Main-Prozess, Challenge wird jedem vertrauenswuerdigen Renderer automatisch ausgestellt). Eine echte native Bestaetigung pro high/critical-Aktion (execute, backupRestore, personalOsDraftApply, mcpCallTool, agentRun, voiceRealtimeStart ...) ist jedoch eine Architektur-/UX-Entscheidung mit hohem Bruchrisiko: modale Dialoge wuerden Voice-/Agent-/Batch-Flows blockieren und das Bedrohungsmodell muss zuerst definiert werden (welche Methoden echte Presence brauchen, ob Bestaetigung in Tray/separates Fenster). Riskant zu raten -> needs_human.

### frontend/main.js:597
**CSP erlaubt img-src http: und https: trotz lokal-first-Anspruch**
Nicht geaendert. Das Finding ist real, aber der vollstaendige Fix ist dateiuebergreifend: das identische <meta>-CSP in frontend/src/index.html (Zeile 9) wuerde http:/https: weiterhin erlauben, sodass eine Aenderung nur in main.js inkonsistent waere. Zudem braeuchte das Einschraenken auf 'self' data: blob: einen Backend-Bild-Proxy fuer Remote-Avatare/Markdown-Bilder (sonst brechen in Chat eingebettete Bilder). Da ich laut Auftrag ausschliesslich frontend/main.js aendern darf und index.html nicht anfassen darf, ist eine isolierte Aenderung hier riskant/unvollstaendig -> needs_human (idealerweise zusammen mit index.html + Backend-Proxy koordinieren).

### dashboard.html:18
**og:image verweist auf nicht vorhandene Datei og-image.jpg**
Bestaetigt als reales Problem: og-image.jpg existiert nicht im Projekt (einziges Bild-Asset ist favicon.svg). Kein Fix vorgenommen, weil die saubere Loesung das Anlegen einer binaeren Vorschau-Grafik (1200x630) erfordert — das Erstellen anderer Dateien als dashboard.html ist untersagt, und ein sinnvolles Preview-Bild laesst sich nicht generieren. Das vom Finding selbst als ungeeignet bezeichnete favicon.svg als Ersatz einzutragen waere keine echte Verbesserung. Betrifft zudem mehrere Seiten (index/auth/agb/datenschutz/impressum) und ist daher eine Asset-/Deploy-Entscheidung.

### dashboard.html:128
**Download-Links zeigen auf privates/nicht existierendes GitHub-Release**
Bestaetigt: https://github.com/alexsprogis/lexa-ai/releases/latest liefert HTTP 404 (auch das Repo selbst: 404 — privat oder nicht vorhanden). Kein Fix vorgenommen, weil die korrekte oeffentliche Ziel-URL nicht aus dem Code ableitbar ist: es gibt im Projekt keine /download-Seite und keine alternative URL-Konfiguration. Eine ersatzweise URL waere reines Raten. Zudem ist derselbe Link in index.html (Z.128 und Z.377) vorhanden — die Korrektur ist eine projekt-/deploy-uebergreifende Entscheidung (stabile Release-URL festlegen).

### backend/action_parser.py:177
**Single-Quote-Reparatur in _try_parse kann valides JSON mit Apostrophen zerstoeren bzw. Mixed-Quote-JSON nie reparieren**
Nicht geaendert. Befund ist real: _try_parse ersetzt ' durch " nur, wenn KEIN " im Text vorhanden ist (Zeile 177), wodurch Mixed-Quote-Quasi-JSON nicht repariert wird und ein reiner Single-Quote-Block mit Apostroph (don't) durch naives Replace korrumpiert wuerde. Die im fix-Feld empfohlene robuste Loesung (json5/demjson-aehnlicher Tolerantparser) verstoesst gegen die Vorgabe 'keine neuen Abhaengigkeiten'. Eine selbstgebaute Regex-Quote-Normalisierung ist genau die riskante Heuristik, die der vorhandene '-Guard bewusst vermeidet (Gefahr, Apostrophe in Werten erneut zu zerstoeren) und damit Geschmackssache/risikobehaftet. Daher bewusst keine Aenderung, um keinen neuen Korruptionsbug einzufuehren.

### backend/action_parser.py:61
**validate_command_output nutzt naive Substring-Suche - False Positives blockieren harmlose Nutzerinhalte**
Nicht geaendert. Befund ist teils ueberzeichnet: DANGEROUS_COMMANDS (security.py:320-326) enthaelt ausschliesslich mehrtoken-Shell-Muster (z.B. 'rm -rf', 'format c:', 'shutdown -s -t 0', 'powershell -enc') - die im Befund genannten Einzelwoerter 'shutdown' bzw. 'format' als blosse Worte loesen also KEINEN Treffer aus. Der Restkern (eine Notiz, die exakt 'rm -rf' o.ae. als Text speichert, wird blockiert) ist real, aber gering. Die empfohlene Korrektur (Content-Felder text/body/message/description vom Scan ausnehmen) wuerde die Sicherheit schwaechen, da _scan_params_for_dangerous_output auch im Agent-Tool-Pfad genutzt wird (agent_loop.py:42/437) - ein LLM koennte gefaehrliche Muster ueber ein als 'text' benanntes Feld einschleusen. Diese sicherheitsrelevante, dateiuebergreifende Abwaegung (separater Fund security.py:331) sollte nicht raterisch in dieser Datei entschieden werden.

### backend/router_agent.py:112
**_is_hermes_system_status_request ruft _hermes_forced_first_tool doppelt auf (einmal hier, einmal in run_agent)**
Keine Aenderung. Der vorgeschlagene Fix (Ergebnis einmal berechnen und an run_agent durchreichen) erfordert eine Signaturaenderung von run_agent in backend/agent_loop.py (Zeile 1107ff. / Aufruf Zeile 1189-1193) — also einen dateiuebergreifenden Eingriff, der laut Auftrag (nur backend/router_agent.py editieren) hier nicht erlaubt ist. Eine rein lokale Loesung in dieser Datei ist nicht moeglich, ohne die Verzweigungsstruktur zu brechen. Fachlich ist der Mehraufwand zudem vernachlaessigbar: _hermes_forced_first_tool (agent_loop.py:934-993) ist deterministisch und fuehrt nur billige Substring-/Normalisierungs-Checks auf der kurzen Nutzernachricht aus; das in der Beschreibung erwaehnte Divergenz-Risiko besteht praktisch nicht, da die Funktion rein und ohne Seiteneffekte ist. Empfehlung zur Koordination: run_agent um einen optionalen Parameter forced_first_tool erweitern und den Wert aus dem Router durchreichen.

### backend/ai_engine.py:80
**Toter Provider-Code: Groq/OpenAI/Anthropic-Clients und -Routing**
Nicht entfernt. Per Grep ueber das Projekt verifiziert: Der vermeintlich tote Code (_get_groq_client, _get_anthropic_api_key, gesamte _anthropic_*-/_AnthropicStream*-Familie, set_ai_model('anthropic:...'), groq/openai/anthropic-Zweige) wird intensiv von tests/test_ai_engine.py genutzt (test_groq_client_*, test_anthropic_*, ~Dutzend Tests). Ein Loeschen von ~400 Zeilen wuerde die bestehende Testsuite brechen. Ob die Multi-Provider-Reserve geloescht oder als Legacy behalten wird, ist eine projektweite Architektur-/Test-Entscheidung. Stattdessen wurde der Status im Modul-Docstring klar als 'inaktiv (Gemini-only), Legacy/Reserve' markiert.

### backend/ai_engine.py:3452
**_detect_quality_mode laeuft bei jeder Nachricht durch ~25 Marker-Gruppen**
Nicht geaendert. Real, aber ein Early-Exit bei score>=2 ist nicht gefahrlos: Die einzelnen Boolean-Flags (security/accessibility/performance/...) werden NACH dem Scoring zum Aufbau des Hint-Strings wiederverwendet. Ein vorzeitiger Abbruch wuerde Hints verlieren und das Verhalten aendern. Die saubere Loesung (vorkompilierter Trie/Single-Pass) waere ein groesserer, geschmacks-/risikobehafteter Rewrite. Die vorhandene @functools.lru_cache(maxsize=4096) auf den normalisierten Markern (Z.3125) mildert die Kosten bereits deutlich.

### backend/ai_engine.py:4338
**Anthropic-Titelgenerierung im toten Zweig kann bei API-Fehler durchschlagen**
Nicht geaendert. Das Finding selbst stuft die Auswirkung als 'praktisch null' ein (toter Zweig durch Gemini-only) und verweist auf 'Erledigt mit Entfernen des toten Anthropic-Codes'. Da diese Entfernung wegen der Test-Anbindung als needs_human eingestuft ist (siehe Z.80-Finding), bleibt auch dieser Zweig unveraendert. Die Exception wird zudem bereits vom umschliessenden except (Z.4344) gefangen, sodass kein unbehandeltes Durchschlagen entsteht.

### backend/memory.py:624
**search_memory_semantic lädt alle eingebetteten Memories in Python (Full-Scan, kein ANN)**
Nicht geändert. Eine echte Behebung (FTS/Keyword-Vorfilter der Kandidaten, ANN-Index oder persistenter Vektor-Cache) ist ein Architektur-/Datenmodell-Eingriff mit Auswirkung auf Trefferqualität — zu riskant für einen minimalen lokalen Diff. Sollte bewusst designt werden.

### backend/memory.py:484
**add_memory: synchroner OpenAI-Embedding-Call im Schreibpfad (blockierend)**
Nicht geändert. Wirklich asynchrones/queue-basiertes Embedding (Markierung + Reindex-Worker) ist eine querschnittliche Änderung des Schreibpfads (auto_remember/_save_interaction/ai_engine-Stream) und braucht ein Worker-Konzept — nicht rein in memory.py sicher umsetzbar.

### backend/memory.py:1248
**conversation_update überschreibt messages komplett — Lost-Update bei parallelen Schreibern**
Nicht geändert. Optimistic Concurrency (version/updated_at im WHERE, Konflikt-Rückgabe) oder append-only-Nachrichtentabelle ist eine API-/Schema-Änderung mit Auswirkung auf alle Aufrufer (Frontend/Router) — bewusst zu koordinieren, nicht als stiller Minimal-Diff.

### backend/memory.py:1198
**conversation_list: Parsing der letzten Nachricht aus SUBSTR-Tail ist fragil**
Nicht geändert. Die saubere Lösung (last_role/last_message als eigene Spalten beim conversation_update mitschreiben) erfordert Schema-Erweiterung (memory_core/schema.py) und Anpassung des Schreibpfads — über diese Datei hinaus. Reines Innerhalb-memory.py-Fixing würde das Problem nicht robust lösen.

### backend/memory.py:444
**Dedup-Exact-Match per LOWER(TRIM(content)) ohne Index — Full-Table-Scan**
Nicht geändert. Die vorgeschlagene Behebung (normalisierte content_norm-Spalte mit Index oder content_hash mit UNIQUE-Index) ist eine Schema-Migration in memory_core/schema.py samt Backfill-/Trigger-Logik — über diese Datei hinaus und migrationsbedürftig.

### backend/memory.py:962
**auto_remember: add_memory committet innerhalb des laufenden Interaction-Inserts**
Nicht geändert. Eine saubere Lösung verlangt eine commit-freie add_memory-Variante bzw. eine umklammernde Transaktion über mehrere Schreibpfade. add_memory ist öffentlich und wird breit genutzt; eine Signatur-/Commit-Semantik-Änderung ist nicht ohne Koordination/Regressionsrisiko machbar. Bewusste Entscheidung nötig.

### backend/router_hermes.py:200
**_open_tasks_from_text dupliziert Logik der Plugin-Implementierung (Divergenzgefahr)**
Nicht geändert. Per Grep bestätigt: Die Parsing-/Auswahl-Logik existiert dupliziert in router_hermes.py (_open_tasks_from_text/_read_next_work_tasks) UND in backend/hermes_adapter.py (Plugin _plugin_tasks, registriert via 'lexa-tasks'). Eine saubere Behebung erfordert Extraktion in einen gemeinsamen Helper (z.B. hermes_adapter/util) und Edits in BEIDEN Dateien. Da der Auftrag ausschließlich Änderungen an router_hermes.py erlaubt, ist die Konsolidierung hier nicht durchführbar -> dateiübergreifende Koordination nötig.

### backend/embeddings.py:94
**_active_provider wird gecacht und ignoriert spätere API-Key-Hinterlegung**
Nicht geändert. Das Problem ist real: _detect_provider() cached _active_provider prozessweit (Zeile 96-129); nach späterer Key-Hinterlegung bleibt 'local' aktiv bis reset_provider(). Der vom Audit primär vorgeschlagene Fix (reset_provider() beim Key-Wechsel in den Einstellungen aufrufen) ist dateiübergreifend (Settings-/Router-/Key-Change-Pfad) und damit außerhalb des erlaubten Scopes (nur backend/embeddings.py). Die einzige rein lokale Alternative (TTL-Caching) behebt die Ursache nicht, sondern verkürzt nur das Fenster, erzeugt Nicht-Determinismus und kann mitten in der Laufzeit einen Provider-Wechsel (local->openai) auslösen — was die im Finding beschriebene Dimensions-Inkompatibilität (alte 256-dim local-Vektoren vs. neue 1536-dim openai-Queries) erst recht provoziert. Korrekter Fix ist event-getrieben im Key-Change-Handler; daher needs_human/Koordination.

### backend/embeddings.py:305
**Lokaler TF-IDF nutzt MD5 für Feature-Hashing — unnötig teuer**
Nicht geändert. Beobachtung (MD5 in _build_tfidf_vector, Zeile 305) ist korrekt, aber der vorgeschlagene Wechsel auf zlib.crc32 ist NICHT sicher anwendbar: Die lokalen TF-IDF-Vektoren werden persistent als SQLite-BLOB gespeichert (memory.py _embed_memory_row Zeile 752-771) und später gegen frisch berechnete Query-Vektoren via cosine_similarity verglichen. Ein anderer Hash ändert die Bucket-Zuordnung aller Tokens, sodass bereits gespeicherte Vektoren und neue Queries nicht mehr im selben Merkmalsraum liegen. Die Kompatibilitätsprüfung embedding_metadata_compatible() prüft nur provider/model/dimension — der Hash-Wechsel würde NICHT erkannt und die semantische Ähnlichkeit für alle Bestands-Memories still degradieren. Ein sicherer Wechsel erfordert ein koordiniertes Reindex aller lokal eingebetteten Memories; daher needs_human.

### backend/memory_core/ranking.py:83
**Recency-Score nutzt naive datetime.now() gegen localtime-Strings ohne TZ-Konsistenzgarantie**
Keine Änderung. Verifiziert: Die memories-Tabelle (backend/memory_core/schema.py:223) schreibt created_at konsequent als LOKALZEIT via datetime('now','localtime') — ebenso alle übrigen Tabellen (memory.py, productivity.py, reminders.py, access.py). Der Vergleich in _score_memory_recency mit dem naiven, lokalen datetime.now() ist damit per Design konsistent zur gespeicherten Zeit. Der vom Finding vorgeschlagene Fix (Speicherung auf UTC umstellen + datetime.utcnow() im Ranking) ist eine dateiübergreifende Schema-/Datenmigration; würde man NUR ranking.py auf datetime.utcnow() umstellen, würde man UTC-Jetzt gegen Lokalzeit-Strings vergleichen und damit einen echten Bug einführen (jedes Memory um den TZ-Offset verfälscht, recency_score systematisch falsch). Der bestehende max(0.0, ...)-Clamp deckelt den verbleibenden Randfall (DST/Backup-Restore -> Zeitstempel knapp in der Zukunft -> Alter 0 -> recency 1.0) bereits sinnvoll und begrenzt. Eine sichere, allein in dieser Datei umsetzbare Verbesserung existiert nicht; daher needs_human (koordinierte Migration über mehrere Dateien + bestehende Nutzerdaten erforderlich).

### backend/router_chat.py:1593
**Hermes-Stream: History wird mit '[Hermes]'-Praefix gespeichert und bricht kontextuelle Followups**
Nicht geaendert. Der empfohlene Fix (das '[Hermes]'-Marker als separates Metadatum statt als content-Teil speichern) erfordert eine Aenderung des History-Speicherformats ueber Dateigrenzen hinweg (update_history/shared State) und ist nicht rein in router_chat.py sauber loesbar. Eine reine In-File-Lockerung der Kuerzung waere spekulativ: Hermes-Summaries (Desktop-Aktionsberichte) enthalten praktisch keine Wetter-/Mathe-/Tagesplan-Marker, auf die die Followup-Regexe reagieren. Geschmacks-/Risiko-Abwaegung -> needs_human.

### backend/intent_engine.py:1433
**'lauter'/'leiser' setzen feste Lautstaerke 70/30 statt relativer Aenderung**
Nicht geaendert. Die korrekte Loesung (relative Anpassung) erfordert ein neues Companion-Command 'volume_adjust' bzw. das Auslesen des aktuellen Pegels (get_volume) plus Whitelist- und tool_registry-Eintraege. Verifiziert: companion/engine.py kennt nur set_volume/mute_volume, kein volume_adjust/get_volume. Eine relative Aenderung ist im Intent-Engine allein nicht moeglich (kein Zugriff auf den aktuellen Pegel), und das Anlegen eines neuen Commands ist dateiuebergreifend und sicherheitsrelevant (Whitelist braucht laut Projektregeln explizite Bestaetigung). Daher zur Koordination/Freigabe markiert statt zu raten.

### backend/error_response.py:77
**error_payload spiegelt rohes 'detail' ungefiltert in die Antwort**
Keine Aenderung. Verifikation gegen den echten Code: error_payload wird projektweit nur in backend/main.py aufgerufen. Alle Aufrufe uebergeben entweder handgeschriebene Strings (Zeilen 208/236/248/623), HTTPException.detail (Z.762, app-kontrolliert), jsonable_encoder(exc.errors()) fuer Validierungsfehler (Z.779, bewusst strukturiert beibehalten) oder den statischen Text 'Internal server error' im Catch-all fuer unbehandelte Exceptions (Z.796). Der gefaehrliche Fall (rohes Exception-/Stacktrace-Objekt) gelangt also nie nach detail — der 500-Handler nutzt bereits einen festen String. Der vorgeschlagene Fix (detail auf error_message(...) beschraenken bzw. nur im Debug-Modus einbetten) wuerde den bestehenden Test tests/test_error_response.py::test_error_payload_extracts_structured_detail_message brechen, der explizit payload['detail']['debug'] == 'hidden internals' (verbatim erhaltenes strukturiertes detail) zusichert, sowie die dokumentierte Zusage des validation_exception_handler ('while keeping detail'). Das ist eine bewusste Vertrags-/Verhaltensentscheidung (Debug-Flag, Rueckwaertskompatibilitaet) und kein sicherer mechanischer Fix — daher needs_human statt zu raten. Das Finding selbst stuft das Risiko bei der lokalen 127.0.0.1-App als gering ein.

### backend/security.py:384
**validate_url führt keine DNS-Auflösung durch — SSRF über DNS-Rebinding/Hostnamen auf private IPs**
Nicht geändert. Der vorhandene Schutz gegen IP-Literale (is_dangerous_network_ip) und benannte Metadaten-Hosts ist real und korrekt. Die geforderte vollständige Lösung (socket.getaddrinfo + Re-Check JEDER aufgelösten IP, idealerweise Connect-to-IP-Pinning gegen Rebinding) lässt sich NICHT sicher allein in dieser Datei umsetzen: validate_url ist synchron und wird synchron im Request-Validierungspfad (validate_params) sowie in workflows.py/plugin_manager.py aufgerufen — blockierendes DNS-I/O hier würde Latenz/Event-Loop-Blocking einführen und die Offline-/Test-Semantik ändern. Echtes Rebinding-Hardening erfordert IP-Pinning an den HTTP-Aufrufstellen (httpx/requests), also dateiübergreifende Koordination. Daher needs_human.

### backend/integrations.py:561
**analyze_clipboard ruft PowerShell synchron mit 3s-Timeout bei jeder Analyse auf — blockierend wenn aus async-Kontext genutzt**
Keine Änderung. Der primäre Fix-Teil (Aufrufer sollen asyncio.to_thread nutzen) betrifft andere Dateien und ist dort bereits korrekt umgesetzt: router_context.py:70 ruft analyze_clipboard via await asyncio.to_thread auf; context_tools.py:_exec_clipboard_content ist selbst synchron (und execute_context_tool wird projektweit nirgends aufgerufen). Die synchrone Methode in dieser Datei ist damit als Design korrekt. Der mittelfristige Vorschlag (PowerShell-Spawn durch Windows-API/ctypes OpenClipboard ersetzen) ist eine nicht-triviale, riskante Umschreibung (CF_UNICODETEXT/Format-Handling, Unicode, Clipboard-Lock) und im Finding explizit als 'mittelfristig' markiert — Geschmacks-/Risikoabwägung, daher needs_human statt zu raten.

### backend/router_os_agents.py:53
**GET /os/tasks/{id} gibt vollstaendiges Task-JSON inkl. evidence/result ungefiltert zurueck**
Bestaetigt am Code: os_task gibt get_os_agent_task(task_id) (== _load_task) 1:1 zurueck; das Task-Dict enthaelt evidence[] mit pro Eintrag eingebettetem result (Hermes-stdout/stderr, in os_agent_runtime _append_evidence) plus task['result'] — also Mehrfach-Duplikation grosser Outputs. NICHT umgesetzt: Der Fix verlangt eine neue, kompakte Antwortform (welche Felder behalten, evidence-data auf Previews kappen, separater Debug/Export-Pfad). Das ist eine API-Vertrags-Designentscheidung, die den Cockpit-Client betreffen kann und sich inhaltlich mit dem dateiuebergreifenden Befund os_agent_runtime.py:475/468 (unredigierte Secrets in result/evidence) ueberschneidet. Eigenmaechtiges Trimmen birgt das Risiko, vom Frontend benoetigte Felder zu entfernen, und sollte mit der Redaction-Aenderung in os_agent_runtime.py koordiniert werden — daher needs_human statt raten.

### backend/personal_os_actions.py:125
**Verbesserung: _resolve_draft_path ist N+1-anfaellig, listet bis 200 Drafts pro Aufruf**
Nicht umgesetzt. Der Vorschlag erfordert entweder einen zustandsbehafteten kurzlebigen In-Memory-Cache (TTL/Invalidierung des os_list_drafts-Ergebnisses pro (approval, hideSmoke)-Schluessel) oder die Rueckgabe der aufgeloesten draftPath im Tool-Resultat (Aenderung der Antwortform). Beides ist riskant bzw. Geschmackssache: Caching kann veraltete Draft-Listen liefern (Korrektheit > marginale Latenz im read-only Chat-Pfad), und eine Aenderung der Response-Shape betrifft Aufrufer ausserhalb dieser Datei. Daher bewusst nicht 'geraten'.

### backend/router_productivity.py:120
**Massenlöschung erledigter Todos ist N+1 statt einer Query**
Bestätigt real: delete_completed_todos (Z.120ff) lädt erst alle done-Todos via prod.todo_list und ruft dann pro Todo einzeln prod.todo_delete via asyncio.to_thread auf (N+1 Thread-Übergaben + N einzelne DELETE+commit). Nicht behoben, da der saubere Fix laut Vorschlag eine neue Funktion prod.todo_delete_completed() (ein einziges DELETE FROM todos WHERE status='done' mit rowcount) in backend/productivity.py erfordert. Per Grep verifiziert: eine solche Bulk-Delete-Funktion existiert dort nicht. Da ich ausschließlich backend/router_productivity.py ändern darf und direkter DB-Zugriff im Router die bestehende Schichtentrennung (alle DB-Logik liegt in productivity.py) verletzen würde, ist der Fix nicht rein in dieser Datei sinnvoll umsetzbar. Erfordert eine kleine Ergänzung in productivity.py durch einen Menschen/separate Koordination.

### companion/hermes_desktop.py:1862
**Nicht-mutierende Aktionen (find/observe/screen_text) ignorieren inline-Abbruch-Formulierungen**
Nicht geaendert. Der vorgeschlagene Fix 'bei erkanntem Gesamt-Abbruch (inline_cancel) den ganzen Plan stoppen' wuerde den im Finding selbst als legitim bezeichneten read-only-Fall 'finde den Senden-Button aber mach nichts' faelschlich blockieren. Das eigentliche Restrisiko (eine mutierende Absicht wird durch classify_desktop_instruction faelschlich als find klassifiziert) laesst sich hier nicht zuverlaessig vom legitimen Fall unterscheiden, ohne valide read-only-Anfragen zu unterdruecken. Da rein read-only (max. OCR/Screenshot) und Verhaltensaenderung mit Regressionsrisiko -> menschliche Abwaegung noetig.

### companion/desktop_control.py:156
**_screen_size nutzt GetSystemMetrics(0/1) statt der DPI-bewussten virtuellen Bildschirmgroesse**
Nicht geaendert. Der Befund ist plausibel, der vorgeschlagene Fix aber riskant und Geschmackssache: (a) SetProcessDpiAwareness beim Import ist ein prozessweiter Seiteneffekt, der den gesamten Companion/Backend-Prozess (inkl. UI-Rendering) betrifft und nicht lokal auf diese Datei begrenzt ist. (b) Die virtuellen Bounds als primaeres screen_width/height in desktop_position zu melden aendert die oeffentliche Rueckgabe-Semantik, die LLM/OCR und ggf. anderer Code konsumieren. Beides sind Verhaltensaenderungen ohne sicheren minimalen Diff und sollten bewusst entschieden werden.

### companion/browser.py:671
**_get_readability_js laedt JS von externem CDN und injiziert es in jede gescrapte Seite**
Nicht geaendert. Befund ist real (kein SRI/Hash/Pinning beim CDN-Abruf von cdn.jsdelivr.net, Code wird via page.evaluate in jede Fremdseite injiziert). Sichere Behebung erfordert entweder das Mitliefern von Readability.js als lokales Projekt-Asset (neue Datei — laut Auftrag nicht erlaubt, nur browser.py editierbar) oder eine SHA-256-Pruefung gegen einen autoritativen Hash, den ich offline nicht verifizieren kann; ein hartkodierter, ungepruefter Hash wuerde entweder das Feature brechen oder falsche Sicherheit vortaeuschen. Daher Koordination/menschliche Entscheidung noetig (Asset bundlen + vetten).

### companion/tool_health.py:99
**Playwright-Health-Check startet bei jedem Build/Refresh einen echten Chromium-Headless-Browser**
Keine Code-Aenderung. Der vorgeschlagene Fix (statt echtem Chromium-Start nur die Existenz der Browser-Binaerdateien im ms-playwright-Cache pruefen) aendert die Verifikations-Semantik und senkt die Zuverlaessigkeit: eine vorhandene Binaerdatei garantiert keinen funktionierenden Start (fehlende System-Libs, korrupte/unvollstaendige Installation). Der echte launch(headless=True) ist genau der Zweck dieses Checks. Der Cache-Pfad ist zudem OS/Version-abhaengig. Das ist ein bewusster Reliability-vs-Performance-Tradeoff und Geschmackssache -> menschliche Entscheidung noetig, nicht raten.

### frontend/src/chat_search.js:177
**Such-Treffer für Notizen/Memories öffnen nicht das konkrete Element, nur die Memory-View**
Keine Änderung. Der Befund ist real (switchView("memory") verwirft n.id/m.id), aber der vorgeschlagene Fix (gezieltes Navigieren/Highlighten via focusId) ist nicht innerhalb von chat_search.js umsetzbar: switchView(view) in app.js akzeptiert nur ein einzelnes view-Argument, und das Hervorheben/Scrollen eines konkreten Notiz-/Memory-Elements müsste in memory.js erfolgen. Zusätzlich ist refreshMemoryView() in memory.js inzwischen auf eine Graph-Ansicht umgestellt (ruft refreshMemoryGraphView() auf und kehrt sofort zurück) — die alte Listendarstellung mit Element-IDs ist toter Code, es existiert also kein Listen-Element zum Fokussieren. Eine korrekte Umsetzung erfordert dateiübergreifende Änderungen (app.js switchView-Signatur + memory.js Graph-Fokus) und ist daher zu koordinieren statt zu raten.

### frontend/src/i18n/i18n.js:104
**changeLanguage/translatePage uebersetzt dynamisch erzeugte Views nicht neu**
Keine Aenderung in i18n.js. Der Fund ist real: setLanguage -> init -> dispatcht zwar das CustomEvent 'lexa-lang-changed' (Zeilen 109-111), aber per projektweitem Grep hoert NIEMAND auf dieses Event; translatePage() (in init nicht einmal aufgerufen) erfasst nur statische [data-i18n]-Elemente. Dynamisch via t() befuellte Views (commands/system/chat) bleiben nach Sprachwechsel stale. Der korrekte Fix ist jedoch dateiuebergreifend: er erfordert einen 'lexa-lang-changed'-Listener bzw. ein switchView(LexaState.get('currentView')) in app.js (dort liegen switchView und LexaState). Ein Aufruf von switchView aus i18n.js heraus wuerde das bewusst entkoppelte Modul (Event-Dispatch-Muster) an app-spezifische View-Logik koppeln und beim Start-init() — bevor Views existieren — riskante Re-Renders ausloesen. Daher rein in DIESER Datei nicht sicher loesbar; Verdrahtung gehoert in die View-Schicht (app.js).

### frontend/src/personal_os_renderers.js:382
**History-Events werden in UI und Chat-Prompt unterschiedlich sortiert/ausgewählt**
Nicht geändert. Der Fund ist real: createPersonalOsReviewHistory (personal_os_renderers.js, Z.382) rendert ALLE Events mit events.slice().reverse() (neueste zuerst, ohne Cut), während personalOsReviewPrompt (personal_os_prompt_helpers.js, Z.232) dieselben Events mit review.history.events.slice(-5) OHNE reverse (letzte 5, chronologisch) in den Chat-Prompt schreibt. Die im Fix geforderte Angleichung über einen gemeinsamen Helper bzw. identische Reihenfolge+Auswahl ist zwingend dateiübergreifend: Die zweite, abweichende Stelle liegt in personal_os_prompt_helpers.js, das laut Auftrag (Punkt 9) NICHT verändert werden darf. Ein einseitiger Fix nur im Renderer ist nicht sinnvoll: (a) den Renderer auf slice(-5).reverse() umzustellen würde die sichtbare Audit-History stillschweigend auf 5 Einträge kürzen — eine Regression, da die UI bewusst die vollständige History anzeigt; (b) eine reine Umsortierung im Renderer löst die Divergenz nicht, weil der Prompt-Pfad in der anderen Datei unverändert slice(-5) ohne reverse nutzt. Kein vorhandener gemeinsamer History-Helper existiert (projektweit per Grep verifiziert). Daher status needs_human: korrekte Lösung = gemeinsamer Selektions-/Sortier-Helper, koordiniert über beide Dateien, mit bewusster Entscheidung, ob die UI weiterhin die volle History oder ebenfalls nur die letzten N zeigen soll.

### frontend/preload.js:2266
**Mehrere POST-Bridge-Methoden ohne try/catch propagieren Netzwerkfehler als unbehandelte Rejection**
Nicht geändert. Der vorgeschlagene Fix (Netzwerkfehler im Bridge schlucken und {ok:false, error} zurückgeben) ist innerhalb von preload.js allein unsicher und würde Regressionen erzeugen: Aufrufer verlassen sich auf die geworfene Rejection. Beispiele: setAiModel (settings.js:272) zeigt im catch einen Fehler-Toast und im Erfolgspfad showToast(...,'success') — ein geschluckter Fehler würde einen FALSE-SUCCESS-Toast auslösen. snippetCreate (memory.js:1359) hat kein lokales try/catch und würde fälschlich 'gespeichert' melden. hermesGatewayAutostartSet (settings.js:602) setzt im catch den Toggle zurück (toggle.checked=previous) — das entfiele. Eine sichere Umsetzung erfordert, dass jeder Aufrufer auf result.ok===false umgestellt wird (cross-file). Daher needs_human statt riskantem Rate-Fix.

### personal_os/11_Integrations/MCP/os-mcp-server/src/index.ts:530
**Keine Lese-Zugriffsbeschraenkung: os_read_file/os_query_index liefern beliebige .md-Dateien unter OS-Root**
Nicht geaendert. Befund ist real (isProtectedPath in paths.ts schuetzt nur Schreibzugriffe, siehe write.ts Z.60/96; os_read_file und os_query_index/queryByTag pruefen keine Read-Allowlist). Eine Read-Denylist ist jedoch eine Sicherheits-/Policy-Entscheidung, die das Verhalten fuer das gesamte Agenten-Oekosystem aendert: Die geschuetzten Bereiche (01_User/, 05_Memory/Core/, 05_Memory/MEMORY.md, 10_Product/, 00_System/Security/) werden vom LLM-Agenten im Normalbetrieb plausibel gelesen. Ein hartes Block bzw. ein neues Berechtigungs-Flag/Tier muss dateiuebergreifend abgestimmt werden (welche Tools, welcher Default, welche Eskalation), statt es hier zu raten.

## PARTIAL — teilweise gefixt, Rest offen (27)

### backend/agent_loop.py:351
**Doppelte Schema-Validierung Executor- vs. Agent-Pfad mit unterschiedlichem Verhalten**
Den sicherheitsrelevanten Teil umgesetzt: _scan_params_for_dangerous_output(safe_params) wird jetzt auch im Agent-Tool-Pfad (in _execute_tool, nach _sanitize_params) angewendet, sodass gefaehrliche Shell-Muster in LLM-Argumenten konsistent zum Chat-Pfad blockiert werden (ValueError -> {success:false} + audit_log). Die vollstaendige Zentralisierung der Validierung in eine von action_executor UND agent_loop genutzte gemeinsame Funktion ist ein dateiuebergreifender Refactor und wurde bewusst nicht riskant erzwungen.

### backend/hermes_adapter.py:1328
**_safe_lexa_memory_snapshot: COUNT(*) ueber 6 Tabellen, f-String-SQL, 0.25s-Timeout**
SQL-Sicherheitsaspekt der backend.md-Regel adressiert: defensive Guard 'if not table.isidentifier(): continue' plus Kommentar, dass Tabellennamen ausschliesslich aus der festen Whitelist _LEXA_MEMORY_TABLES stammen. Den vorgeschlagenen Performance-Teil (COUNT-Schaetzung via LIMIT-Subquery oder TTL-Cache) NICHT umgesetzt, da er die im UI angezeigten Zahlen veraendert bzw. Cache-Invalidierung einfuehrt — siehe needs_human-Hinweis.

### backend/hermes_adapter.py:1810
**get_hermes_capabilities loest verschachtelte, redundante Statusberechnungen aus**
get_hermes_media_status() um optionalen Parameter provider_status erweitert; get_hermes_capabilities reicht den bereits berechneten provider_status durch, wodurch der doppelte get_hermes_provider_status-Aufruf (inkl. erneutem config/env-Read) entfaellt. Den umfassenderen Vorschlag (config/env einmal pro Request laden und an ALLE Sub-Funktionen durchreichen) bewusst nicht umgesetzt, da er die oeffentlichen Signaturen mehrerer von Router-Endpoints genutzter Status-Funktionen aendert (riskanter, dateiuebergreifende Aufrufer).

### companion/file_tools.py:1100
**file_write: schmale Pfad-Blockliste lässt Persistenz-Pfade (Autostart) zu**
Der Autostart-Ordner ('start menu\\programs\\startup') wurde zu _FILE_WRITE_BLOCKED_PATH_PARTS hinzugefügt, sodass file_write nicht mehr in den Windows-Startup-Ordner schreiben kann. Der zweite Teil des Vorschlags (vollständig aufgelösten Zielpfad in der Bestätigungs-UI anzeigen) ist dateiübergreifend (Confirmation-Dialog liegt außerhalb dieser Datei) und wurde hier nicht umgesetzt.

### frontend/src/chat.js:433
**Fire-and-forget fetch auf /chat/confirm-clear ohne Fehlerbehandlung/Bridge-Nutzung**
In denyAction wurde der bisher unbehandelte Promise-Reject des fire-and-forget fetch durch ein `.catch(...)` mit console.warn abgesichert (vorher fing das sync try/catch eine Netzwerk-Rejection NICHT). Der rohe fetch bleibt erhalten: es existiert KEINE preload-Bridge-Methode fuer /chat/confirm-clear (Anlegen erfordert preload.js = datuebergreifend) und der Test electron_confirmation_click_smoke.js zaehlt fetch-Aufrufe auf /chat/confirm-clear (clearCalls===1) — ein Bridge-Wechsel wuerde den Test brechen. confirmAction (Z.2255/2260) nutzt bereits await im try/catch und ist daher schon abgesichert.

### frontend/src/memory.js:1270
**trackClipboard liest System-Zwischenablage ohne Nutzer-Trigger und kann sensible Daten persistieren**
Defensive Maskierung ergänzt: Neue Hilfsfunktion isLikelySensitiveClipboard() erkennt typische Schlüssel/Token/Passwort-Muster (sk_/pk_/rk_-Präfixe, ghp/xox/AKIA/ya29/JWT eyJ..., Bearer-Token, api_key/secret/token/password-Zuweisungen, lange leerzeichenfreie Hex/Base64-Strings). trackClipboard speichert solche Inhalte nicht mehr (frühzeitiger return mit console.info). Damit werden bei einer etwaigen Reaktivierung der Funktion offensichtliche Geheimnisse nicht mehr in die lokale DB geschrieben. Bewusst NICHT umgesetzt: das geforderte explizite Opt-in/Kopplung an den Privacy-Prompt, da die nötige Verdrahtung/Einstellung außerhalb dieser Datei liegt (Settings/IPC) und die Funktion derzeit ohnehin nirgends aufgerufen wird.

### backend/memory.py:1829
**clipboard_add: Duplikat-Erkennung whitespace-sensitiv**
Eingabe wird vor Vergleich/Speichern mit strip() normalisiert und der DELETE läuft über TRIM(text)=?, sodass Einträge, die sich nur in führenden/abschließenden Leerzeichen oder Newlines unterscheiden, nicht mehr als Quasi-Duplikate die 50er-History fluten. Case-Insensitivität wurde bewusst NICHT umgesetzt, da Lowercasing den gespeicherten Klartext verfälschen würde (Clipboard-Inhalt muss originalgetreu bleiben).

### backend/context_tools.py:198
**KI-gesteuerte Context-Tools fuehren ungedrosselte System-/Subprozess-Operationen ohne Audit aus**
Audit-Logging in execute_context_tool ergaenzt: ueber 'from backend.security import audit_log' wird nun jeder Tool-Aufruf protokolliert (command='context_tool:<name>') mit Status success/failed/rejected/error inkl. Fehlertext bei Exceptions. Damit ist die fehlende Audit-Schicht — analog zum Companion-Pfad — geschlossen, die der Fund als Kernluecke nennt. Die if/elif-Kette wurde minimal umgebaut (Ergebnis in 'result' sammeln, dann loggen, dann zurueckgeben); Signatur und Rueckgabeformat unveraendert. Nicht umgesetzt: Rate-Limiting (check_rate_limit gehoert in die Endpoint-/Request-Schicht und hat hier keinen Request-Kontext) und Bestaetigungs-Gating sensibler Tools (browser_tabs/recent_files) — beides ist dateiuebergreifend (Agent-Loop/Settings/Security-Tier) und nicht sauber allein in dieser Datei loesbar. Hinweis: execute_context_tool wird projektweit aktuell von keinem Aufrufer genutzt (verwaistes Feature); die Audit-Haertung ist dennoch sicher und konsistent zur Security-Konvention.

### backend/intent_engine.py:1043
**Synchroner heavy Import/Aufruf von companion.app_discovery im Schnellpfad**
Im _RE_APP_OPEN-Zweig den blockierenden find_app()-Aufruf entfernt. Dieser diente dort nur dem Anzeigenamen in der Nachricht; die tatsaechliche Aufloesung macht app_open -> launch_app ohnehin nachgelagert in der Companion-Schicht (verifiziert in companion/engine.py:404-407). Action/params bleiben identisch (Rohname). Der find_app-Aufruf im _RE_APP_CLOSE-Zweig (Zeile ~1069) bleibt bestehen: dort ist die Aufloesung funktional (liefert den proc_name fuer process_kill), und der saubere Fix (Verlagerung in den action_executor) ist dateiuebergreifend und daher hier nicht moeglich.

### backend/mcp_client.py:118
**MCP-Subprozess wird ohne Working-Directory und ohne command-Allowlist gestartet**
cwd-Teil umgesetzt: create_subprocess_exec erhält nun cwd=str(LEXA_DATA_DIR) (Import aus backend.config ergänzt), ein definiertes, beim Config-Import bereits angelegtes, schreibbares Verzeichnis — statt das (im Build OneDrive-/PyInstaller-) cwd des Backends zu erben. Damit verhalten sich MCP-Server mit relativen Pfaden deterministisch. Der command-Allowlist-Teil wurde NICHT umgesetzt: command stammt aus mcp_registry.load_config()/mcp_servers.json; eine Allowlist/Pfadprüfung gehört in die Registry-/Config-Schicht (mcp_registry.py) und ist dateiübergreifend — laut Vorgaben separat zu koordinieren (needs_coordination für diesen Teilaspekt).

### backend/plugin_loader.py:116
**Legacy-Plugin-Loader ist standardmäßig deaktiviert, bleibt aber komplett im Code**
Fund bestätigt: discover_plugins()/list_plugins() kehren ohne LEXA_ENABLE_LEGACY_PLUGIN_LOADER=1 sofort zurück, der restliche Pfad ist im Normalbetrieb tot. Der Loader ist aber KEIN echter toter Code, sondern ein bewusst gewollter Opt-in-Kompatibilitätspfad: companion/engine.py (Zeilen 27, 340, 354) importiert und ruft discover_plugins()/list_plugins() weiterhin auf, und es existieren dedizierte Tests (tests/test_plugin_permissions.py::test_legacy_plugin_loader_default_disabled, tests/test_plugin_manager.py::test_legacy_plugin_loader_blocks_network_and_introspection_patterns) sowie ein statischer Source-Read-Test (tests/test_backend_data_dir_static.py). Die vom Fund vorgeschlagene Entfernung/Auslagerung des Loaders ist daher dateiübergreifend (engine.py + Tests + Doku) und nicht rein in dieser Datei umsetzbar. Lokal sicher umgesetzt wurde die zweite, gefahrlose Hälfte des Fixes ('in der Doku eindeutig auf plugin_manager als kanonisches System verweisen'): Im Modul-Docstring wurde der Titel auf 'Plugin Loader (LEGACY / DEPRECATED)' geändert und ein DEPRECATED-Block ergänzt, der erklärt, dass dieser Loader standardmäßig deaktiviert ist, nur per Env-Var aktivierbar bleibt und plugin_manager.py das kanonische System mit AST-Validierung/Permission-Policy ist. Reine Kommentar-/Docstring-Änderung — keine Signaturen, kein Verhalten, keine Tests berührt; Kommentarsprache (Deutsch) beibehalten.

### backend/main.py:804
**uvicorn-Start: zwei divergierende Startpfade und zwei Quellen für Host/Port**
In DIESER Datei umsetzbarer Teil behoben: __main__-Block von uvicorn.run(app, ...) auf den Import-String uvicorn.run('backend.main:app', ...) umgestellt — identisch zum Produktions-Entry (backend/pyinstaller_entry.py), damit reload/workers verfügbar bleiben und Dev/Prod gleich starten. Host/Port bleiben aus backend.config (BACKEND_HOST/BACKEND_PORT, abgeleitet aus LEXA_HOST/LEXA_PORT) — bestätigt als Single Source of Truth in config.py:93-94. Hinweis: Die zweite Host/Port-Quelle liegt in pyinstaller_entry.py (liest os.environ direkt) und kann hier nicht angefasst werden; dafür dateiübergreifende Angleichung nötig.

### backend/security.py:292
**sanitize_input kürzt Chat-Nachrichten still auf 2000 Zeichen — unter MAX_CHAT_MESSAGE_LENGTH (4000)**
sanitize_input erhielt einen optionalen Parameter 'max_chars: int = 2000'. Default bleibt 2000 (rückwärtskompatibel zu allen bestehenden Aufrufern und zum Test test_input_truncated_at_2000), aber Aufrufer im Chat-Pfad können nun sanitize_input(req.message, max_chars=MAX_CHAT_MESSAGE_LENGTH) übergeben, um stilles Abschneiden zu vermeiden. Die eigentliche Kopplung an MAX_CHAT_MESSAGE_LENGTH bzw. die Nutzer-Rückmeldung muss in router_chat.py/router_agent.py/router_os_agents.py erfolgen — das liegt außerhalb dieser Datei. In security.py ist damit nur die Voraussetzung geschaffen.

### backend/security.py:331
**validate_command_output erkennt gefährliche Befehle nur per naivem Substring-Vergleich**
Vor dem Matching werden nun sowohl die Ausgabe als auch jedes Muster über re.sub(r'\\s+',' ') whitespace-normalisiert. Damit sind die im Finding genannten trivialen Whitespace-Bypässe (z.B. 'rm  -rf' mit Doppel-Space, 'rm\\t-rf', Zeilenumbruch zwischen Tokens) jetzt abgedeckt. Docstring klargestellt, dass dies eine Defense-in-Depth-Blockliste ist, nicht das primäre Gate (Autorisierung via is_command_allowed/Whitelist). Die im Finding vorgeschlagene vollständige Token-Parser-Lösung wurde NICHT umgesetzt: is_command_allowed arbeitet auf Action-Namen, nicht auf Freitext-Parameterwerten, und kann diesen Scanner daher nicht ersetzen; ein echter Shell-Token-Parser wäre eine größere Umschreibung mit Falsch-Negativ-Risiko. Wortgrenzen-Matching gegen Falsch-Positive (z.B. 'bcdedit' als Teilstring) wurde bewusst nicht ergänzt, da mehrere Muster Leerzeichen enthalten und \b dann inkonsistent griffe.

### backend/router_backup.py:110
**Backup-Datei-Erstellung: Fallback schreibt vollständiges Backup-JSON inkl. evtl. sensibler Daten erneut, doppelte Serialisierung**
In create_backup_file() wird der von memory.backup_database(str(path)) zurückgegebene komplette data-Dict (alle Notizen/Memories/Conversations) nun sofort nach dem Schreiben freigegeben (data = None), sobald die Datei existiert, damit das potenziell große Payload garbage-collected werden kann, bevor die Response gebaut wird. Der json.dumps-Fallback läuft weiterhin nur, wenn die Datei NICHT existiert (nachgewiesener Schreibfehler), nicht generisch. Im Happy-Path bleibt es bei genau einer Serialisierung (durch memory.backup_database selbst) — es gibt also keine doppelte Serialisierung mehr außer im echten Fehlerfall. Erläuternder Kommentar (EN, dateikonsistent) ergänzt.

### backend/reminders.py:401
**Verpasste wiederkehrende Erinnerungen feuern nur einmal trotz mehrerer übersprungener Intervalle**
Bestätigt: reminder_check legt pro fälligem wiederkehrendem Reminder genau EINE nächste Occurrence an; _calculate_next springt in die Zukunft, übersprungene Intervalle entfallen kommentarlos. Die vorgeschlagene funktionale Variante (Anzahl verpasster Intervalle melden / in die Nachricht aufnehmen) würde Form des fired-Dicts bzw. die Anzeige ändern und damit Frontend-Anpassungen außerhalb dieser Datei erfordern. Umgesetzt wurde daher der sichere, dateilokale Teil des Fixes ('mindestens dokumentieren'): erklärender Kommentar an der Stelle der Occurrence-Erstellung, dass verpasste Intervalle bewusst zusammengefasst werden (kein Catch-up/Backfill). Verhaltensänderung am Code bewusst unterlassen.

### backend/router_calendar.py:43
**calendar_connect startet OAuth-Browserflow ohne Timeout und kann den Endpoint blockieren**
In router_calendar.py einen Modul-Level threading.Lock (_connect_lock) eingeführt und in calendar_connect mit acquire(blocking=False) genutzt: Überlappende Connect-Aufrufe werden jetzt sofort mit HTTP 409 und klarer Meldung abgewiesen, statt mehrere blockierte Worker-Threads zu stapeln (verhindert Executor-Pool-Erschöpfung). Lock wird im finally wieder freigegeben. import threading ergänzt. Der zweite Teil des Fixes (Timeout für den lokalen Redirect-Server / OAuth-Wartezeit) ist NICHT umsetzbar, da flow.run_local_server(port=0) in companion/calendar_integration.py:63 ohne Timeout-Parameter läuft und diese Datei laut Auftrag nicht verändert werden darf — daher Status partial.

### backend/router_voice.py:65
**Hartkodierter Default-Sensitivity-Wert 0.015 mehrfach dupliziert**
Da nur diese Datei editiert werden darf (Vorschlag war eine Konstante in voice/config.py), wurde eine modullokale Single-Source-of-Truth-Konstante _DEFAULT_WAKE_SENSITIVITY = 0.015 vor den Request-Models definiert und an allen drei Stellen referenziert: SensitivityRequest.sensitivity, _wakeword_default_status() und wakeword_get_sensitivity()-Fallback. voice/config.py existiert, hat aber keine passende Konstante (WAKE_PORCUPINE_SENSITIVITY=0.55 ist andere Semantik). Eine projektweite Konstante in config.py bleibt fuer spaeter offen.

### companion/engine.py:396
**execute() ruft synchrone Blocking-Companion-Methoden direkt im Event-Loop-Kontext auf**
Der eigentliche Fix liegt im Aufrufer: backend/agent_loop.py:474 nutzt korrekt asyncio.to_thread, aber backend/action_executor.py:131 ruft companion.execute() synchron ohne to_thread auf — das ist dateiübergreifend und außerhalb dieser Datei. In engine.py habe ich den in-file-Teil umgesetzt: ausführliche Warn-Docstring an execute(), die erzwingt/dokumentiert, dass die Methode nur via asyncio.to_thread aus async-Kontext aufgerufen werden darf (sonst friert der Event-Loop ein). Die nötige Korrektur in action_executor.py muss separat koordiniert werden.

### companion/desktop_control.py:452
**desktop_scroll ignoriert das Zielfenster vollstaendig und scrollt am Cursor**
Docstring praezisiert: statt der irrefuehrenden Angabe 'Scroll the active window' beschreibt sie jetzt korrekt, dass am Cursor gescrollt wird (Windows liefert Wheel-Events an das Fenster unter dem Cursor) und dass Aufrufer das Zielfenster vorher mit dem Cursor zentrieren muessen (wie es hermes_desktop._center_cursor_on_window bereits vor jedem Aufruf tut). Der alternative Vorschlag (window-Parameter + Zentrier-Logik) wurde NICHT umgesetzt: die Zentrier-Logik liegt in hermes_desktop.py; sie hierher zu duplizieren waere riskant/Code-Doppelung und nicht rein lokal sauber, zumal Hermes die Zentrierung bereits korrekt vornimmt.

### companion/browser.py:405
**open_url/play_youtube: page.new_page() ohne page.close() bei Erfolg — Page-Leak**
Echte Datenextraktions-Leaks behoben: search_youtube (Playwright-Pfad) nutzt jetzt try/finally mit page.close(), sodass die Page auch bei wait_for_selector/evaluate-Fehlern geschlossen wird (zuvor nur auf dem Erfolgspfad). open_url und der play_youtube-Wiedergabepfad lassen die sichtbare Page BEWUSST offen: dort ist die geoeffnete Seite/das Video das vom Nutzer gewollte Ergebnis im sichtbaren Browser — sie zu schliessen wuerde das Feature kaputtmachen. Daher kein page.close() im Erfolgsfall dieser beiden Funktionen.

### frontend/src/chat_message_formatting.js:140
**formatMessage() ist toter Code und liefert innerHTML — Re-Injection-Risiko bei spaeterer Nutzung**
Kein Entfernen/Umbau moeglich ohne Schaden: formatMessage() ist KEIN toter Code, sondern ein Test-/Serialisierungs-Helfer. Projektweiter Grep zeigt: tests/test_chat_rendering.js ruft formatMessage() in 15+ String-Gleichheits-Assertions auf (z.B. === "hello world", === "line one<br>line two"), und tests/test_frontend_script_order_static.js:163 verlangt statisch das Vorhandensein von 'function formatMessage('. Entfernen wuerde beide Tests brechen; eine Rueckgabe als DocumentFragment/Element wuerde die String-Assertions brechen (verbotener Bruch des erwarteten Verhaltens). Der Live-Runtime-Pfad nutzt ausschliesslich renderFormattedMessage()->appendFormattedMessage() (reines DOM, kein innerHTML) — das tatsaechliche Injection-Risiko ist rein hypothetisch. Die im fix vorgeschlagene Doku-Korrektur betrifft frontend.md (ausserhalb dieser Datei, nicht erlaubt). Umgesetzt: minimaler, sicherer In-Datei-Fix — ein expliziter SECURITY-Warnkommentar direkt ueber formatMessage(), der vor 'element.innerHTML = formatMessage(text)' warnt und auf renderFormattedMessage()/appendFormattedMessage() als sicheren Pfad verweist. Keine Signatur geaendert, keine Tests gebrochen.

### frontend/src/chat_voice.js:362
**AudioContext und Audio-Graph-Knoten der Stille-Erkennung werden nie freigegeben (Memory/Resource-Leak)**
Der Teil 'Source-/Analyser-Nodes werden nie disconnected' war bereits behoben: voiceStopSilenceDetect (Z.362-367) ruft src.disconnect()/analyser.disconnect() auf, und voiceStop ruft voiceStopSilenceDetect (Z.344). Der zweite, im Finding/Fix genannte Aspekt — ein eigener, paralleler Voice.audioCtx neben dem Shared-Context aus chat.js — bestand noch und wurde von mir behoben: voiceStartSilenceDetect verwendet jetzt _getAudioCtx() aus chat.js (mit typeof-Guard und Fallback auf new AudioContext() bei state==='closed'). Dadurch wird nur noch ein gemeinsamer AudioContext gehalten (Browser-Limit ~6 wird nicht durch einen zweiten Kontext belastet) und das vorhandene Resume-bei-suspended-Verhalten mitgenutzt. _getAudioCtx ist ein globaler Funktions-Declaration in chat.js (plain script-tags, gemeinsamer Renderer-Scope) und zur Laufzeit von voiceStartSilenceDetect verfügbar, obwohl chat_voice.js vor chat.js geladen wird.

### frontend/src/chat_agent_runs.js:819
**startAgentCompletionContinue: doppelter focus()-Aufruf und stilles Überschreiben eines bestehenden Composer-Entwurfs**
Teil 1 (doppelter focus()): FALSE POSITIVE — im echten Code (Zeilen 812-826) gibt es nur EINEN chatInput.focus()-Aufruf (Zeile 819), keinen zweiten focus() in einem setTimeout(...,0). Dieser Teil war bereits bereinigt, daher keine Änderung. Teil 2 (stilles Überschreiben eines ungespeicherten Composer-Entwurfs ohne Rückfrage): real, aber NICHT umgesetzt — der Fix wäre eine UX-Entscheidung (Bestätigungsdialog/Undo vs. Anhängen), und exakt dasselbe Muster existiert dateiübergreifend in startContinueFromMessage (chat_message_actions_controller.js Zeile 199, außerhalb des erlaubten Änderungsbereichs). Würde man nur startAgentCompletionContinue absichern, entstünde eine Inkonsistenz zwischen zwei parallelen Continue-Funktionen. Dies sollte konsistent und abgestimmt entschieden werden, daher als needs_human/needs_coordination zu behandeln statt zu raten.

### frontend/src/chat_message_actions_controller.js:252
**saveMessageAsMemory erlaubt Mehrfachspeicherung derselben Antwort (Duplikat-Memories)**
Die im Finding behauptete Duplikat-Lücke existiert im aktuellen Code so NICHT: nach Erfolg wird btn.disabled (Zeile 259 gesetzt) bewusst nicht zurückgesetzt, nur aria-busy entfernt — der Button bleibt disabled, und der Guard `if (btn?.disabled) return;` (Zeile 253) verhindert ein erneutes Speichern bereits. Das Finding ist hier ein Fehlschluss. Da der Schutz aber nur implizit am Disabled-Nebeneffekt hängt (fragil: ein künftiges finally, das wie die anderen Handler dieser Datei wieder enabled, würde den Bug einführen), wurde der vom Finding empfohlene explizite Idempotenz-Schutz umgesetzt: am Funktionsanfang zusätzlich `btn?.dataset.saved === "true"` prüfen (Zeile 253) und im Erfolgszweig `btn.dataset.saved = "true"` setzen (Zeile 265). Verhalten im Normalpfad unverändert, Schutz nun explizit und refactoring-sicher. Kein riskanter Eingriff, öffentliche Signatur unverändert.

### frontend/src/productivity.js:545
**Sidebar-Todo-Badge: Zahl statt String, duplizierte Logik**
Neue gemeinsame Hilfsfunktion setTodoSidebarBadge(count) eingefuehrt (String-Cast via String(n), Clamp >=0, einheitliches >99 -> '99+', Sichtbarkeits-Toggle). createTodo nutzt jetzt diese Funktion statt der inline Zahl-Zuweisung an textContent (impliziter Cast behoben). Den zusaetzlichen window.lexa.todos('open')-Roundtrip habe ich BEWUSST belassen: Der vom Audit vorgeschlagene Ersatz durch refreshProdStats' open_todos ist NICHT aequivalent — Backend zaehlt open_todos als status IN ('open','in_progress') (productivity.py Z.1050), waehrend das Badge gezielt nur status='open' meint (todo_list filtert status = ? exakt, productivity.py Z.247-253). Ein Wechsel wuerde die Badge-Semantik aendern (in_progress mitgezaehlt). Die Auslagerung in einen projektweiten gemeinsamen Helper (auch dashboard.js Z.308-316 hat dieselbe Zahl-Cast-Stelle) ist dateiuebergreifend und wurde nicht angefasst.

### i18n.js:442
**setLanguage überschreibt Elemente nur bei vorhandenem Key — fehlende Keys bleiben unentdeckt; Text ohne data-i18n bleibt einsprachig**
In setLanguage() wird die Übersetzungs-Schleife verbessert: Statt der Truthiness-Prüfung `if (I18N_DICT[lang][key])` (die auch legitime leere Strings übersprungen hätte) wird jetzt per `Object.prototype.hasOwnProperty.call(dict, key)` echte Existenz geprüft. Existiert ein data-i18n-Key NICHT im Dictionary, wird ein `console.warn('[i18n] Fehlender Übersetzungs-Key ...')` ausgegeben, sodass Lücken bei der Entwicklung sofort auffallen. Das Dictionary wird einmal in `const dict` gecacht. Der zweite Teil des Vorschlags (data-i18n an dashboard.html Z.173 'Alle Tools + Dev-Suite' vergeben) wurde per Grep als real bestätigt (dashboard.html:173 hat tatsächlich kein data-i18n), liegt aber dateiübergreifend in dashboard.html und wurde gemäß Auftrag NICHT angefasst — nur i18n.js darf geändert werden.


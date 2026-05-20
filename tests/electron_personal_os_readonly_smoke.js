/**
 * Electron read-only Personal OS cockpit smoke.
 * Uses the real renderer with mocked display payloads and never clicks write/apply controls.
 * Run with: node tests\electron_personal_os_readonly_smoke.js
 */

const path = require("path");

if (!process.versions.electron) {
  const { spawnSync } = require("child_process");
  const electronBinary = process.platform === "win32" ? "electron.exe" : "electron";
  const electronPath = path.join(__dirname, "..", "frontend", "node_modules", "electron", "dist", electronBinary);
  const env = { ...process.env, LEXA_ELECTRON_SMOKE_TEST: "1", LEXA_ELECTRON_SMOKE_MOCK: "1" };
  delete env.ELECTRON_RUN_AS_NODE;
  const result = spawnSync(electronPath, [__filename], {
    cwd: path.join(__dirname, ".."),
    env,
    stdio: "inherit",
  });
  process.exit(result.status ?? (result.signal ? 1 : 0));
}

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const os = require("os");

process.env.LEXA_ELECTRON_SMOKE_TEST = "1";
process.env.LEXA_ELECTRON_SMOKE_MOCK = "1";

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-personal-os-readonly-"));
app.setPath("userData", smokeUserData);
app.on("window-all-closed", () => {});

let passed = 0;
let failed = 0;
const bridgeAudits = [];
const presenceRequests = [];

function assert(desc, ok, detail = "") {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`);
    failed += 1;
  }
}

function runRenderer(win, script) {
  return win.webContents.executeJavaScript(script, true);
}

ipcMain.handle("i18n-load", (_event, lang) => {
  const safeLang = lang === "en" ? "en" : "de";
  const filePath = path.join(__dirname, "..", "frontend", "src", "i18n", `${safeLang}.json`);
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
});
ipcMain.handle("local-auth-token", () => "personal-os-readonly-smoke-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  bridgeAudits.push(payload);
  return { ok: true };
});
ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
  presenceRequests.push(payload);
  return { ok: false, reason: "personal_os_readonly_smoke_denied" };
});
ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
ipcMain.on("get-autostart", (event) => { event.returnValue = false; });
ipcMain.on("set-autostart", () => {});

async function main() {
  await app.whenReady();

  const rendererErrors = [];
  const win = new BrowserWindow({
    width: 1160,
    height: 820,
    show: false,
    backgroundColor: "#071018",
    webPreferences: {
      preload: path.join(__dirname, "..", "frontend", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    const text = String(message || "");
    if (/frame-ancestors.+meta/i.test(text)) return;
    if (level >= 3 || /\b(LEXA ERROR|Unhandled|TypeError|ReferenceError|SyntaxError|RangeError)\b/i.test(text)) {
      rendererErrors.push({ level, message: text.slice(0, 500), line, sourceId });
    }
  });
  win.webContents.on("render-process-gone", (_event, details) => {
    rendererErrors.push({ level: 3, message: `render-process-gone: ${details?.reason || "unknown"}` });
  });
  win.webContents.on("did-fail-load", (_event, code, description, url) => {
    rendererErrors.push({ level: 3, message: `did-fail-load ${code}: ${description || ""} ${url || ""}`.trim() });
  });

  await win.loadFile(path.join(__dirname, "..", "frontend", "src", "index.html"));
  await new Promise((resolve) => setTimeout(resolve, 1400));

  const result = await runRenderer(win, `
    (async () => {
      const waitFor = (predicate, timeoutMs = 5000) => new Promise((resolve) => {
        const started = Date.now();
        const tick = () => {
          let value = false;
          try { value = predicate(); } catch (_) { value = false; }
          if (value) { resolve({ ok: true }); return; }
          if (Date.now() - started > timeoutMs) { resolve({ ok: false, timeoutMs }); return; }
          setTimeout(tick, 40);
        };
        tick();
      });

      await waitFor(() =>
        window.lexa
        && typeof switchView === "function"
        && typeof renderPersonalOsStatus === "function"
        && typeof renderPersonalOsDraftList === "function"
        && typeof renderPersonalOsDetail === "function"
        && typeof renderPersonalOsQueryPayload === "function"
        && typeof renderPersonalOsContextPack === "function"
        && typeof renderPersonalOsGraphPayload === "function"
        && typeof posErrorMessage === "function"
        && document.getElementById("personal-os-view")
      );

      const fetchCalls = [];
      const originalFetch = window.fetch;
      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), method: options?.method || "GET" });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.set("currentView", "chat");
        LexaState.clearInterval("personal-os");
      }

      switchView("personal-os");
      await new Promise((resolve) => setTimeout(resolve, 250));
      if (typeof LexaState !== "undefined") LexaState.clearInterval("personal-os");

      const unsafe = "<img src=x onerror=alert(1)>";
      const diagnostics = {
        ok: true,
        state: "attention",
        summary: "Personal OS connected " + unsafe,
        nextAction: "Review " + unsafe,
        counts: { total: 2, pending: 1, approved: 1, rejected: 0, conflict: 0, missing: 0, invalid: 0 },
        status: {
          status: "connected",
          server: "personal_os " + unsafe,
          tools_count: 9,
          draft_review: true,
          capabilities: {
            draftQueue: true,
            reviewPacket: true,
            auditHistory: true,
            contextBrowser: true,
            graph: true,
            explicitApply: true,
          },
        },
        checks: [
          { id: "mcp", label: "MCP " + unsafe, state: "ok", detail: "connected " + unsafe },
          { id: "pending-drafts", label: "Pending " + unsafe, state: "warn", detail: "1 draft " + unsafe },
        ],
      };
      const queue = {
        ok: true,
        counts: diagnostics.counts,
        drafts: [
          {
            title: "Read-only draft " + unsafe,
            path: "06_Inbox/Drafts/readonly-smoke.md",
            approval: "pending",
            memory_level: "working",
            source: "smoke",
            tags: ["readonly", "smoke"],
          },
        ],
      };

      if (typeof PersonalOSState !== "undefined") {
        PersonalOSState.lastRefreshAt = Date.now();
        PersonalOSState.draftSearch = "";
      }
      renderPersonalOsStatus(diagnostics.status, queue, diagnostics);
      renderPersonalOsDraftList(queue);
      const draftListSnapshot = {
        text: document.getElementById("pos-draft-list")?.textContent || "",
        html: document.getElementById("pos-draft-list")?.innerHTML || "",
        rows: document.querySelectorAll("#pos-draft-list .pos-draft-row").length,
      };

      renderPersonalOsDetail({
        ok: true,
        path: "06_Inbox/Drafts/readonly-smoke.md",
        approval: "pending",
        frontmatter: {
          title: "Draft title " + unsafe,
          tags: ["readonly", unsafe],
          related: ["05_Memory/Rollups/related.md", unsafe],
        },
        body: "Draft body " + unsafe,
      }, {
        assist: {
          status: "attention",
          summary: "Review assist summary " + unsafe,
          checks: [{ state: "warn", label: "Check " + unsafe, detail: "Detail " + unsafe }],
        },
        checklist: { hasApproved: true, hasRejected: true, approvedChecked: false, rejectedChecked: false },
        applyHint: { enabled: false, target: "05_Memory/Rollups/target.md", reason: "Approved state required " + unsafe },
        history: { events: [{ type: "DraftCreated " + unsafe, timestamp: "2026-05-20T10:00:00Z", agent: "Smoke", reason: "Display only " + unsafe }] },
        related: [{ title: "Related " + unsafe, path: "05_Memory/Rollups/related.md", type: "memory-summary", error: "Read-only unavailable " + unsafe }],
        target: { error: "Target unavailable " + unsafe },
      });
      const detailSnapshot = {
        title: document.getElementById("pos-detail-title")?.textContent || "",
        text: document.getElementById("pos-draft-detail")?.textContent || "",
        html: document.getElementById("pos-draft-detail")?.innerHTML || "",
        approveDisabled: document.getElementById("pos-approve-btn")?.disabled === true,
        rejectDisabled: document.getElementById("pos-reject-btn")?.disabled === true,
        applyDisabled: document.getElementById("pos-apply-btn")?.disabled === true,
      };

      renderPersonalOsQueryPayload({
        ok: true,
        matches: [
          { title: "Index route " + unsafe, path: "00_System/INDEX.md", memory_level: "system " + unsafe },
          { title: "Memory item " + unsafe, path: "05_Memory/Rollups/one.md", type: "memory " + unsafe },
        ],
      });
      const queryListSnapshot = {
        text: document.getElementById("pos-query-results")?.textContent || "",
        html: document.getElementById("pos-query-results")?.innerHTML || "",
        rows: document.querySelectorAll("#pos-query-results .pos-query-row").length,
      };

      renderPersonalOsContextPack({
        ok: true,
        query: { areaPath: "00_System " + unsafe, tag: "lexa " + unsafe, candidateCount: 2, includedCount: 1 },
        files: [{
          title: "Context file " + unsafe,
          path: "00_System/INDEX.md",
          memory_level: "core " + unsafe,
          tags: ["lexa", unsafe],
          bodyPreview: "Context preview " + unsafe,
        }],
        errors: [{ error: "Skipped unreadable fixture " + unsafe }],
        graph: { ok: false, counts: { edges: 1 } },
      });
      const contextPackSnapshot = {
        text: document.getElementById("pos-query-results")?.textContent || "",
        html: document.getElementById("pos-query-results")?.innerHTML || "",
        relatedRows: document.querySelectorAll("#pos-query-results [data-related-path]").length,
      };

      renderPersonalOsGraphPayload({
        ok: true,
        areaPath: "00_System " + unsafe,
        counts: { files: 1, edges: 1 },
        nodes: [
          { id: "file-1", kind: "file", label: "Graph file " + unsafe, path: "00_System/INDEX.md", degree: 1, memory_level: "system" },
          { id: "tag-lexa", kind: "tag", label: "#lexa " + unsafe, degree: 1 },
        ],
        edges: [{ source: "file-1", target: "tag-lexa", type: "tag" }],
      });
      const graphSnapshot = {
        text: (document.getElementById("pos-graph-summary")?.textContent || "") + " " + (document.getElementById("pos-graph-stage")?.textContent || ""),
        html: (document.getElementById("pos-graph-summary")?.innerHTML || "") + " " + (document.getElementById("pos-graph-stage")?.innerHTML || ""),
        nodes: document.querySelectorAll("#pos-graph-stage .pos-graph-node").length,
      };

      renderPersonalOsQueryPayload({ ok: false, detail: { message: "Query unavailable " + unsafe }, requestId: "readonly-smoke" });
      const errorSnapshot = {
        text: document.getElementById("pos-query-results")?.textContent || "",
        html: document.getElementById("pos-query-results")?.innerHTML || "",
      };

      renderPersonalOsDraftList({ ok: true, counts: {}, drafts: [] });
      const emptySnapshot = {
        text: document.getElementById("pos-draft-list")?.textContent || "",
        detailText: document.getElementById("pos-draft-detail")?.textContent || "",
      };

      const view = document.getElementById("personal-os-view");
      const allHtml = view?.innerHTML || "";
      const allText = view?.textContent || "";
      const writeControls = {
        approve: Boolean(document.getElementById("pos-approve-btn")),
        reject: Boolean(document.getElementById("pos-reject-btn")),
        apply: Boolean(document.getElementById("pos-apply-btn")),
        rawButtons: document.querySelectorAll('[data-action="submitPersonalOsRawInbox"], [data-pos-home-action="raw"]').length,
      };
      const unsafeNodes = view?.querySelectorAll("script,img[onerror],iframe,object,embed").length || 0;
      const active = view?.classList.contains("active") === true;
      const internalChipVisible = Boolean(view?.querySelector('[data-readiness="internal"]'));
      window.fetch = originalFetch;

      return {
        active,
        internalChipVisible,
        statusText: document.getElementById("pos-status-grid")?.textContent || "",
        statusHtml: document.getElementById("pos-status-grid")?.innerHTML || "",
        draftListSnapshot,
        detailSnapshot,
        queryListSnapshot,
        contextPackSnapshot,
        graphSnapshot,
        errorSnapshot,
        emptySnapshot,
        allText,
        allHtml,
        unsafeNodes,
        writeControls,
        fetchCalls,
      };
    })();
  `);

  await new Promise((resolve) => setTimeout(resolve, 120));

  console.log("\nPersonal OS read-only cockpit smoke:");
  assert("Personal OS view loads and remains marked Internal", result.active === true && result.internalChipVisible === true, JSON.stringify({ active: result.active, internalChipVisible: result.internalChipVisible }));
  assert("mocked OS status summary renders safely", /(OS|Entwurf|Review|Prüfen|connected|verbunden)/i.test(result.statusText || "") && /&lt;img src=x onerror=alert\(1\)&gt;/.test(result.statusHtml || ""), JSON.stringify({ text: result.statusText, html: result.statusHtml }));

  const draftList = result.draftListSnapshot || {};
  assert("draft-like item renders in the queue as display text", Number(draftList.rows || 0) === 1 && draftList.text.includes("Read-only draft") && /&lt;img src=x onerror=alert\(1\)&gt;/.test(draftList.html || ""), JSON.stringify(draftList));

  const detail = result.detailSnapshot || {};
  assert("draft detail renders unsafe title/body/history as inert text", detail.title.includes("Draft title") && detail.text.includes("Draft body") && detail.text.includes("Review assist summary") && /&lt;img src=x onerror=alert\(1\)&gt;/.test(detail.html || "") && !/<img src=x/i.test(detail.html || ""), JSON.stringify(detail));
  assert("read-only smoke does not enable apply for mocked pending draft", detail.applyDisabled === true, JSON.stringify(detail));

  const query = result.queryListSnapshot || {};
  assert("mocked route/index items render safely", Number(query.rows || 0) === 2 && query.text.includes("Index route") && query.text.includes("Memory item") && !/<img src=x/i.test(query.html || ""), JSON.stringify(query));

  const contextPack = result.contextPackSnapshot || {};
  assert("mocked context pack renders read-only result cards safely", Number(contextPack.relatedRows || 0) === 1 && contextPack.text.includes("Context file") && contextPack.text.includes("Context preview") && !/<img src=x/i.test(contextPack.html || ""), JSON.stringify(contextPack));

  const graph = result.graphSnapshot || {};
  assert("mocked context map renders read-only nodes safely", Number(graph.nodes || 0) >= 2 && graph.text.includes("Graph file") && /&lt;img src=x onerror=alert\(1\)&gt;/.test(graph.html || ""), JSON.stringify(graph));

  const error = result.errorSnapshot || {};
  assert("Personal OS error state renders safely", error.text.includes("Query unavailable") && error.text.includes("Request ID: readonly-smoke") && !/<img src=x/i.test(error.html || ""), JSON.stringify(error));

  const empty = result.emptySnapshot || {};
  assert("empty draft queue recovers to stable empty state", /No .*draft|Kein|Keine/i.test(empty.text || "") && /No .*draft|Kein|Keine/i.test(empty.detailText || ""), JSON.stringify(empty));
  assert("unsafe OS-like content does not create executable nodes", Number(result.unsafeNodes || 0) === 0, JSON.stringify(result.unsafeNodes));

  const controls = result.writeControls || {};
  assert("write-capable controls remain visible but untouched by the read-only smoke", controls.approve === true && controls.reject === true && controls.apply === true && Number(controls.rawButtons || 0) >= 1, JSON.stringify(controls));
  assert("read-only Personal OS smoke did not perform renderer fetch calls", Array.isArray(result.fetchCalls) && result.fetchCalls.length === 0, JSON.stringify(result.fetchCalls || []));

  const forbiddenBridgeMethods = new Set([
    "personalOsDraftDecision",
    "personalOsDraftApply",
    "personalOsRawSubmit",
    "execute",
    "executeWithConfirmation",
    "prepareCompanionExecute",
    "chatFile",
    "setAiModel",
    "elevenlabsSetKey",
    "deepgramSetKey",
    "cartesiaSetKey",
  ]);
  assert("read-only Personal OS smoke did not call write/tool/provider/secret bridge methods", bridgeAudits.every((entry) => !forbiddenBridgeMethods.has(entry?.method)) && presenceRequests.length === 0, JSON.stringify({ bridgeAudits, presenceRequests }));
  assert("renderer stayed free of fatal errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  await win.close();
  app.exit(failed > 0 ? 1 : 0);
}

main().catch(async (error) => {
  console.error(error);
  app.exit(1);
});

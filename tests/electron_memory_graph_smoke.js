/**
 * Electron smoke for the Obsidian-style Memory/Gedaechtnis graph view.
 * Uses the real renderer with smoke-mocked bridge data and performs no writes.
 * Run with: node tests\electron_memory_graph_smoke.js
 */

const path = require("path");
require("./electron_smoke_safe_io");

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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-memory-graph-smoke-"));
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
ipcMain.handle("local-auth-token", () => "memory-graph-smoke-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  bridgeAudits.push(payload);
  return { ok: true };
});
ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
  presenceRequests.push(payload);
  return { ok: false, reason: "memory_graph_smoke_denied" };
});
ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
ipcMain.on("get-autostart", (event) => { event.returnValue = false; });
ipcMain.on("set-autostart", () => {});

async function main() {
  await app.whenReady();

  const rendererErrors = [];
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    show: false,
    backgroundColor: "#06070d",
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
      const waitFor = (predicate, timeoutMs = 6000) => new Promise((resolve) => {
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
        && typeof refreshMemoryView === "function"
        && typeof renderMemoryGraph === "function"
        && document.getElementById("memory-view")
      );

      const originalFetch = window.fetch;
      const fetchCalls = [];
      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), method: options?.method || "GET" });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.clearInterval("memory");
      }

      switchView("memory");
      const rendered = await waitFor(() => document.querySelectorAll("#memory-graph-svg .memory-graph-node").length >= 3);
      if (typeof LexaState !== "undefined") LexaState.clearInterval("memory");

      const svg = document.getElementById("memory-graph-svg");
      const shell = document.querySelector("#memory-view .memory-graph-shell");
      const nodes = Array.from(document.querySelectorAll("#memory-graph-svg .memory-graph-node"));
      const links = Array.from(document.querySelectorAll("#memory-graph-svg .memory-graph-link"));
      const brainBackdrop = document.querySelector("#memory-graph-svg .memory-graph-brain-backdrop");
      const brainFolds = document.querySelectorAll("#memory-graph-svg .memory-graph-brain-fold").length;
      const curvedLinks = links.filter((link) => link.tagName.toLowerCase() === "path" && /^M\\s/.test(link.getAttribute("d") || "")).length;
      const labels = Array.from(document.querySelectorAll("#memory-graph-svg .memory-graph-label")).map((el) => ({
        text: el.textContent || "",
        html: el.innerHTML || "",
      }));
      const oldIds = ["memory-stats-grid", "notes-list", "snippets-list", "ai-status-panel", "routines-list", "clipboard-history-list", "memory-cleanup-info"];
      const oldVisibleSections = oldIds.filter((id) => document.getElementById(id));

      const unsafeNode = nodes.find((node) => (node.getAttribute("aria-label") || "").includes("<img src=x onerror=alert(1)>"));
      unsafeNode?.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true }));
      unsafeNode?.focus();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const inspector = document.getElementById("memory-graph-inspector");
      const inspectorState = {
        text: inspector?.textContent || "",
        html: inspector?.innerHTML || "",
      };

      const filter = document.getElementById("memory-graph-filter");
      if (filter) {
        filter.value = "unsafe";
        filter.dispatchEvent(new Event("input", { bubbles: true }));
      }
      const dimAfterFilter = document.querySelectorAll("#memory-graph-svg .memory-graph-node.is-dim").length;
      document.getElementById("memory-graph-fit-btn")?.click();
      await new Promise((resolve) => setTimeout(resolve, 80));

      if (filter) {
        filter.value = "";
        filter.dispatchEvent(new Event("input", { bubbles: true }));
      }
      const fallbackData = buildMemoryGraphFallbackData({
        stats: { memories: 2 },
        conversations: {
          conversations: [
            { id: 701, title: "Fallback Chat <img src=x onerror=alert(3)>", message_count: 4, last_message: "Shared graph fallback topic" },
          ],
        },
        notes: {
          notes: [
            { id: 702, title: "Fallback Note", content: "Shared graph fallback note" },
          ],
        },
        snippets: { snippets: [] },
        routines: { routines: [] },
      });
      renderMemoryGraph(fallbackData);
      await waitFor(() => document.querySelectorAll("#memory-graph-svg .memory-graph-node").length >= 4);
      const fallbackLabels = Array.from(document.querySelectorAll("#memory-graph-svg .memory-graph-label")).map((el) => ({
        text: el.textContent || "",
        html: el.innerHTML || "",
      }));

      const unsafeExecutableNodes = document.querySelectorAll("#memory-view script, #memory-view img[onerror]").length;
      const viewBox = svg?.getAttribute("viewBox") || "";
      const active = document.getElementById("memory-view")?.classList.contains("active") || false;

      window.fetch = originalFetch;
      return {
        rendered,
        active,
        shell: Boolean(shell),
        viewBox,
        nodeCount: nodes.length,
        linkCount: links.length,
        brainBackdrop: Boolean(brainBackdrop),
        brainFolds,
        curvedLinks,
        labels,
        oldVisibleSections,
        inspectorState,
        dimAfterFilter,
        fallback: {
          source: fallbackData.source,
          nodes: fallbackData.nodes.length,
          links: fallbackData.links.length,
          labels: fallbackLabels,
        },
        unsafeExecutableNodes,
        fetchCalls,
      };
    })();
  `);

  await new Promise((resolve) => setTimeout(resolve, 120));

  console.log("\nMemory graph smoke:");
  assert("Memory view switches to graph-only shell", result.active === true && result.shell === true, JSON.stringify(result));
  assert("Smoke graph renders SVG nodes and links", result.rendered?.ok === true && result.nodeCount >= 3 && result.linkCount >= 2 && /^\d+ \d+ \d+ \d+$/.test(result.viewBox || ""), JSON.stringify(result));
  assert("Memory graph renders neural brain backdrop and curved pathways", result.brainBackdrop === true && result.brainFolds >= 5 && result.curvedLinks >= Math.min(2, result.linkCount), JSON.stringify(result));
  assert("Old Memory dashboard sections are absent from the visible view", Array.isArray(result.oldVisibleSections) && result.oldVisibleSections.length === 0, JSON.stringify(result.oldVisibleSections));
  assert("Unsafe graph labels render as inert text", result.labels.some((label) => label.text.includes("<img src=x onerror=alert(1)>") && /&lt;img src=x onerror=alert\(1\)&gt;/.test(label.html || "")), JSON.stringify(result.labels));
  assert("Inspector displays unsafe preview without executable nodes", result.inspectorState?.text?.includes("<script>alert(1)</script>") && !/<script/i.test(result.inspectorState?.html || ""), JSON.stringify(result.inspectorState));
  assert("Graph filter dims unrelated nodes", Number(result.dimAfterFilter || 0) >= 1, JSON.stringify(result.dimAfterFilter));
  assert("Legacy read-endpoint fallback builds a non-empty graph", result.fallback?.source === "frontend_fallback_readonly" && result.fallback.nodes >= 4 && result.fallback.links >= 3, JSON.stringify(result.fallback));
  assert("Fallback graph labels remain inert text", result.fallback?.labels?.some((label) => label.text.includes("<img src=x onerror=alert(3)>") && /&lt;img src=x onerror=alert\(3\)&gt;/.test(label.html || "")), JSON.stringify(result.fallback?.labels || []));
  assert("Graph view does not create executable unsafe elements", Number(result.unsafeExecutableNodes || 0) === 0, JSON.stringify(result.unsafeExecutableNodes));
  assert("Memory graph smoke did not perform renderer fetch calls", Array.isArray(result.fetchCalls) && result.fetchCalls.length === 0, JSON.stringify(result.fetchCalls || []));
  assert("Memory graph bridge stayed read-only and did not request presence", presenceRequests.length === 0 && bridgeAudits.every((entry) => entry?.method !== "execute" && entry?.method !== "personalOsDraftApply"), JSON.stringify({ bridgeAudits, presenceRequests }));
  assert("renderer stayed free of fatal errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  await win.close();
  app.exit(failed > 0 ? 1 : 0);
}

main().catch(async (error) => {
  console.error(error);
  app.exit(1);
});

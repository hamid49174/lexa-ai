/**
 * Electron provider/model settings smoke.
 * Uses the real renderer with smoke bridge mocks and never touches real keys/keyring/providers.
 * Run with: node tests\electron_provider_settings_smoke.js
 */

const path = require("path");
const { normalizeElectronConsoleMessage } = require("./electron_smoke_safe_io");

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
  if (result.error) {
    console.error(`[Electron smoke] Failed to launch Electron at ${electronPath}: ${result.error.message || result.error}`);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const os = require("os");

process.env.LEXA_ELECTRON_SMOKE_TEST = "1";
process.env.LEXA_ELECTRON_SMOKE_MOCK = "1";

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-provider-settings-"));
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
ipcMain.handle("local-auth-token", () => "provider-settings-smoke-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  bridgeAudits.push(payload);
  return { ok: true };
});
ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
  presenceRequests.push(payload);
  return { ok: false, reason: "provider_settings_smoke_denied" };
});
ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
ipcMain.on("get-autostart", (event) => { event.returnValue = false; });
ipcMain.on("set-autostart", () => {});

async function main() {
  await app.whenReady();

  const rendererErrors = [];
  const win = new BrowserWindow({
    width: 1120,
    height: 780,
    show: false,
    backgroundColor: "#071018",
    webPreferences: {
      preload: path.join(__dirname, "..", "frontend", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.webContents.on("console-message", (event, ...legacyConsoleArgs) => {
    const { level, message, line, sourceId } = normalizeElectronConsoleMessage(event, ...legacyConsoleArgs);
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
        && typeof refreshSettingsView === "function"
        && typeof loadModelSelection === "function"
        && typeof changeAiModel === "function"
        && typeof settingsRenderAiModelSelection === "function"
        && document.getElementById("settings-view")
        && document.getElementById("model-select")
      );

      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.set("notificationsEnabled", true);
      }

      const fetchCalls = [];
      const originalFetch = window.fetch;
      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), method: options?.method || "GET" });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      await refreshSettingsView();
      await waitFor(() => (document.getElementById("model-desc")?.textContent || "").includes("Smoke Model"), 4000);

      const providerStatuses = {
        groq: document.getElementById("groq-status")?.textContent || "",
        openai: document.getElementById("openai-status")?.textContent || "",
        gemini: document.getElementById("gemini-status")?.textContent || "",
        anthropic: document.getElementById("anthropic-status")?.textContent || "",
      };
      const modelSelect = document.getElementById("model-select");
      const modelBefore = {
        desc: document.getElementById("model-desc")?.textContent || "",
        optionCount: modelSelect?.options?.length || 0,
        selectedValue: modelSelect?.value || "",
      };

      await changeAiModel("openai:gpt-4o-mini");
      await new Promise((resolve) => setTimeout(resolve, 120));
      const modelAfter = {
        desc: document.getElementById("model-desc")?.textContent || "",
        selectedValue: modelSelect?.value || "",
      };

      const unsafeSelect = document.createElement("select");
      const unsafeDesc = document.createElement("div");
      settingsRenderAiModelSelection({
        current: "unsafe:model",
        current_name: "<script>alert(1)</script>",
        available: { "unsafe:model": "<img src=x onerror=alert(1)>" },
        grouped: {
          unsafe: {
            label: "Unsafe <script>Group</script>",
            models: { "unsafe:model": "<img src=x onerror=alert(1)>" },
          },
        },
      }, unsafeSelect, unsafeDesc);

      const settingsView = document.getElementById("settings-view");
      const keyInputs = Array.from(settingsView.querySelectorAll("input")).map((input) => ({
        id: input.id || "",
        type: input.type || "",
        value: input.value || "",
      }));
      const secretPattern = /(?:sk-(?:live|test|proj|car)?[_-]?[A-Za-z0-9]{12,}|AIza[0-9A-Za-z_-]{20,}|LEXA-[A-Z0-9-]{16,})/i;
      const visibleText = settingsView.textContent || "";
      const unsafeNodes = settingsView.querySelectorAll("script,img[onerror]").length + unsafeSelect.querySelectorAll("script,img[onerror]").length;
      window.fetch = originalFetch;

      return {
        providerStatuses,
        modelBefore,
        modelAfter,
        unsafeRendered: {
          label: unsafeSelect.querySelector("optgroup")?.label || "",
          text: unsafeSelect.textContent || "",
          html: unsafeSelect.innerHTML || "",
          desc: unsafeDesc.textContent || "",
        },
        keyInputs,
        secretLikeVisible: secretPattern.test(visibleText) || keyInputs.some((input) => secretPattern.test(input.value || "")),
        unsafeNodes,
        fetchCalls,
      };
    })();
  `);

  await new Promise((resolve) => setTimeout(resolve, 120));

  console.log("\nProvider/model settings smoke:");
  const providerStatuses = result.providerStatuses || {};
  assert("provider status rows render mocked availability", ["groq", "openai", "gemini", "anthropic"].every((name) => /Verbunden|Connected/i.test(providerStatuses[name] || "")), JSON.stringify(providerStatuses));

  const modelBefore = result.modelBefore || {};
  assert("model selector hydrates mocked current model", modelBefore.desc === "Aktiv: Smoke Model", JSON.stringify(modelBefore));
  assert("empty mocked model list remains stable", Number(modelBefore.optionCount || 0) === 0, JSON.stringify(modelBefore));

  const modelAfter = result.modelAfter || {};
  assert("safe mocked model change leaves the settings UI usable", modelAfter.desc === "Aktiv: Smoke Model", JSON.stringify(modelAfter));

  const unsafeRendered = result.unsafeRendered || {};
  assert("unsafe provider/model labels are rendered as inert text", unsafeRendered.label.includes("<script>Group</script>") && unsafeRendered.text.includes("<img src=x onerror=alert(1)>") && unsafeRendered.desc === "Aktiv: <script>alert(1)</script>" && /&lt;img src=x onerror=alert\(1\)&gt;/.test(unsafeRendered.html || ""), JSON.stringify(unsafeRendered));
  assert("settings provider path did not expose secret-like values", result.secretLikeVisible === false, JSON.stringify(result.keyInputs || []));
  assert("settings provider path did not create executable unsafe nodes", Number(result.unsafeNodes || 0) === 0, JSON.stringify(result.unsafeNodes));
  assert("settings provider path did not perform renderer fetch calls", Array.isArray(result.fetchCalls) && result.fetchCalls.length === 0, JSON.stringify(result.fetchCalls || []));

  const auditText = JSON.stringify(bridgeAudits);
  const secretMethods = ["elevenlabsSetKey", "elevenlabsDeleteKey", "deepgramSetKey", "deepgramDeleteKey", "cartesiaSetKey", "cartesiaDeleteKey"];
  assert("model change used only the mocked setAiModel bridge", bridgeAudits.some((entry) => entry?.method === "setAiModel" && entry?.allowed === true), auditText);
  assert("provider smoke did not call keyring/API-key bridge methods", secretMethods.every((method) => !auditText.includes(method)) && presenceRequests.length === 0, JSON.stringify({ bridgeAudits, presenceRequests }));
  assert("bridge audit metadata redacts the safe model value", !auditText.includes("openai:gpt-4o-mini"), auditText);
  assert("renderer stayed free of fatal errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  await win.close();
  app.exit(failed > 0 ? 1 : 0);
}

main().catch(async (error) => {
  console.error(error);
  app.exit(1);
});

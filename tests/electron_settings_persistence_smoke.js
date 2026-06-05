/**
 * Electron settings persistence smoke.
 * Uses the real renderer scripts with isolated userData and only local preference writes.
 * Run with: node tests\electron_settings_persistence_smoke.js
 */

const path = require("path");
const { loadElectronSmokeFile, normalizeElectronConsoleMessage } = require("./electron_smoke_safe_io");

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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-settings-persistence-"));
app.setPath("userData", smokeUserData);
app.on("window-all-closed", () => {});

let passed = 0;
let failed = 0;

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
ipcMain.handle("local-auth-token", () => "settings-persistence-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "settings_persistence_smoke_denied" }));
ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
ipcMain.on("get-autostart", (event) => { event.returnValue = false; });
ipcMain.on("set-autostart", () => {});

async function main() {
  await app.whenReady();

  const rendererErrors = [];
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
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

  await loadElectronSmokeFile(win, path.join(__dirname, "..", "frontend", "src", "index.html"));
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
        && typeof loadThemePreferences === "function"
        && typeof loadLanguagePreference === "function"
        && typeof toggleTheme === "function"
        && typeof setAccentColor === "function"
        && typeof setFontSize === "function"
        && typeof settingsSafeTheme === "function"
        && document.getElementById("settings-view")
      );

      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", false);
        LexaState.set("notificationsEnabled", true);
      }

      const fetchCalls = [];
      const originalFetch = window.fetch;
      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), method: options?.method || "GET" });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      const keys = ["lexa-theme", "lexa-accent", "lexa-fontsize", "lexa-lang", "lexa-unknown-setting"];
      keys.forEach((key) => localStorage.removeItem(key));
      localStorage.setItem("lexa-unknown-setting", "preserve-me");

      const settingsView = document.getElementById("settings-view");
      const betaBefore = settingsView.querySelectorAll('[data-readiness="beta"]').length;
      const internalBefore = settingsView.querySelectorAll('[data-readiness="internal"]').length;

      toggleTheme(false);
      setAccentColor("green");
      setFontSize("16");
      await loadLanguagePreference();

      const persisted = {
        viewLoaded: Boolean(settingsView),
        themeStored: localStorage.getItem("lexa-theme") || "",
        themeAttr: document.documentElement.getAttribute("data-theme") || "",
        accentStored: localStorage.getItem("lexa-accent") || "",
        accentAttr: document.documentElement.getAttribute("data-accent") || "",
        greenPressed: document.querySelector('.accent-dot[data-accent="green"]')?.getAttribute("aria-pressed") || "",
        purplePressed: document.querySelector('.accent-dot[data-accent="purple"]')?.getAttribute("aria-pressed") || "",
        fontStored: localStorage.getItem("lexa-fontsize") || "",
        fontAttr: document.documentElement.getAttribute("data-font-size") || "",
        languageStored: localStorage.getItem("lexa-lang") || "",
        languageSelect: document.getElementById("language-select")?.value || "",
        unknownStored: localStorage.getItem("lexa-unknown-setting") || "",
      };

      document.documentElement.setAttribute("data-theme", "dark");
      document.documentElement.setAttribute("data-accent", "amber");
      document.documentElement.setAttribute("data-font-size", "13");
      loadThemePreferences();
      const hydrated = {
        themeAttr: document.documentElement.getAttribute("data-theme") || "",
        accentAttr: document.documentElement.getAttribute("data-accent") || "",
        greenPressed: document.querySelector('.accent-dot[data-accent="green"]')?.getAttribute("aria-pressed") || "",
        fontAttr: document.documentElement.getAttribute("data-font-size") || "",
        fontSelect: document.getElementById("fontsize-select")?.value || "",
      };

      localStorage.setItem("lexa-theme", "solarized<script>");
      localStorage.setItem("lexa-accent", "<img src=x onerror=alert(1)>");
      localStorage.setItem("lexa-fontsize", "99");
      localStorage.setItem("lexa-lang", "fr");
      document.documentElement.setAttribute("data-theme", "light");
      document.documentElement.setAttribute("data-accent", "blue");
      document.documentElement.setAttribute("data-font-size", "16");
      loadThemePreferences();
      await loadLanguagePreference();
      const recovered = {
        themeAttr: document.documentElement.getAttribute("data-theme") || "",
        accentAttr: document.documentElement.getAttribute("data-accent") || "",
        purplePressed: document.querySelector('.accent-dot[data-accent="purple"]')?.getAttribute("aria-pressed") || "",
        fontAttr: document.documentElement.getAttribute("data-font-size") || "",
        fontSelect: document.getElementById("fontsize-select")?.value || "",
        languageStored: localStorage.getItem("lexa-lang") || "",
        languageSelect: document.getElementById("language-select")?.value || "",
        unsafeAccentNodes: settingsView.querySelectorAll("img[onerror],script").length,
      };

      setAccentColor("<img src=x onerror=alert(1)>");
      setFontSize("<script>alert(1)</script>");
      const invalidDirect = {
        accentStored: localStorage.getItem("lexa-accent") || "",
        accentAttr: document.documentElement.getAttribute("data-accent") || "",
        fontStored: localStorage.getItem("lexa-fontsize") || "",
        fontAttr: document.documentElement.getAttribute("data-font-size") || "",
      };

      const betaAfter = settingsView.querySelectorAll('[data-readiness="beta"]').length;
      const internalAfter = settingsView.querySelectorAll('[data-readiness="internal"]').length;
      const labels = {
        betaBefore,
        betaAfter,
        internalBefore,
        internalAfter,
        ttsBeta: /Beta/.test(document.querySelector("#settings-view")?.textContent || "") && Boolean(document.querySelector("#settings-view [data-readiness='beta']")),
        licenseInternal: Boolean(document.querySelector("#license-key-display")?.closest(".settings-group")?.querySelector('[data-readiness="internal"]')),
        hermesInternal: Boolean(document.getElementById("hermes-gateway-autostart-status")?.closest(".settings-group")?.querySelector('[data-readiness="internal"]')),
      };

      window.fetch = originalFetch;
      return { persisted, hydrated, recovered, invalidDirect, labels, fetchCalls };
    })();
  `);

  console.log("\nSettings persistence smoke:");
  const persisted = result.persisted || {};
  assert("settings view loads", persisted.viewLoaded === true, JSON.stringify(persisted));
  assert("theme toggle persists safe local value", persisted.themeStored === "light" && persisted.themeAttr === "light", JSON.stringify(persisted));
  assert("accent selection persists and updates pressed state", persisted.accentStored === "green" && persisted.accentAttr === "green" && persisted.greenPressed === "true" && persisted.purplePressed === "false", JSON.stringify(persisted));
  assert("font size persists safe local value", persisted.fontStored === "16" && persisted.fontAttr === "16", JSON.stringify(persisted));
  assert("language preference hydrates to safe default", persisted.languageStored === "de" && persisted.languageSelect === "de", JSON.stringify(persisted));
  assert("unknown settings keys are preserved", persisted.unknownStored === "preserve-me", JSON.stringify(persisted));

  const hydrated = result.hydrated || {};
  assert("saved local preferences hydrate into the UI", hydrated.themeAttr === "light" && hydrated.accentAttr === "green" && hydrated.greenPressed === "true" && hydrated.fontAttr === "16" && hydrated.fontSelect === "16", JSON.stringify(hydrated));

  const recovered = result.recovered || {};
  assert("corrupt theme/accent/font settings recover safely", recovered.themeAttr === "dark" && recovered.accentAttr === "" && recovered.purplePressed === "true" && recovered.fontAttr === "14" && recovered.fontSelect === "14", JSON.stringify(recovered));
  assert("corrupt language setting recovers safely", recovered.languageStored === "de" && recovered.languageSelect === "de", JSON.stringify(recovered));
  assert("unsafe persisted settings do not create executable nodes", Number(recovered.unsafeAccentNodes || 0) === 0, JSON.stringify(recovered));

  const invalidDirect = result.invalidDirect || {};
  assert("invalid direct setting calls fall back safely", invalidDirect.accentStored === "purple" && invalidDirect.accentAttr === "" && invalidDirect.fontStored === "14" && invalidDirect.fontAttr === "14", JSON.stringify(invalidDirect));

  const labels = result.labels || {};
  assert("Beta/Internal settings labels remain visible", labels.betaBefore >= 1 && labels.internalBefore >= 1 && labels.betaAfter === labels.betaBefore && labels.internalAfter === labels.internalBefore && labels.ttsBeta === true && labels.licenseInternal === true && labels.hermesInternal === true, JSON.stringify(labels));
  assert("local settings persistence did not trigger external fetch calls", Array.isArray(result.fetchCalls) && result.fetchCalls.length === 0, JSON.stringify(result.fetchCalls || []));
  assert("renderer stayed free of fatal errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  await win.close();
  app.exit(failed > 0 ? 1 : 0);
}

main().catch(async (error) => {
  console.error(error);
  app.exit(1);
});

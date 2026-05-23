/**
 * Electron visual smoke for the main Lexa UI.
 * Run with: node tests\electron_ui_visual_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-ui-smoke-"));
app.setPath("userData", smokeUserData);
app.on("window-all-closed", () => {});

delete process.env.LEXA_ELECTRON_SMOKE_MOCK;

ipcMain.handle("i18n-load", (_, lang) => {
  const safeLang = lang === "en" ? "en" : "de";
  const filePath = path.join(__dirname, "..", "frontend", "src", "i18n", `${safeLang}.json`);
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
});

const smokeBridgeAuditPath = () => path.join(app.getPath("userData"), "bridge-audit.log");
let smokeAutostartWrites = 0;

function writeSmokeBridgeAudit(payload = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    method: String(payload.method || "").slice(0, 120),
    risk: String(payload.risk || payload.effective_risk || "").slice(0, 40),
    allowed: Boolean(payload.allowed),
    reason: String(payload.reason || "").slice(0, 120),
    args_hash: String(payload.args_hash || "").slice(0, 16),
    arg_keys: Array.isArray(payload.arg_keys) ? payload.arg_keys.slice(0, 20) : [],
  };
  fs.appendFileSync(smokeBridgeAuditPath(), `${JSON.stringify(entry)}\n`, "utf8");
}

ipcMain.handle("local-auth-token", () => "smoke-local-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  writeSmokeBridgeAudit(payload);
  return { ok: true };
});
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "user_denied" }));
ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
ipcMain.on("get-autostart", (event) => {
  event.returnValue = false;
});
ipcMain.on("set-autostart", (_event, enabled) => {
  if (enabled) smokeAutostartWrites += 1;
});

async function runRenderer(win, script) {
  return win.webContents.executeJavaScript(script, true);
}

async function waitForBridge(win) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const ready = await runRenderer(win, "Boolean(window.lexa && window.lexa.getAutostart && window.lexa.setAutostart)");
    if (ready) return true;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return false;
}

async function runBridgeSecurityProbe() {
  const probeHtml = path.join(smokeUserData, "bridge-security-probe.html");
  fs.writeFileSync(probeHtml, "<!doctype html><html><body>bridge probe</body></html>", "utf8");
  const win = new BrowserWindow({
    width: 480,
    height: 320,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "frontend", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  await win.loadFile(probeHtml);
  const preloadReady = await waitForBridge(win);
  const readResult = preloadReady ? await runRenderer(win, "window.lexa.getAutostart()") : null;
  const beforeWrites = smokeAutostartWrites;
  const highRiskResult = preloadReady ? await runRenderer(win, `
    (async () => {
      try {
        await window.lexa.setAutostart(true);
        return { ok: true };
      } catch (error) {
        return { ok: false, code: error && error.code, message: String(error && error.message || "") };
      }
    })();
  `) : { ok: true, code: "", message: "preload unavailable" };
  await new Promise((resolve) => setTimeout(resolve, 80));
  const auditPath = smokeBridgeAuditPath();
  const auditText = fs.existsSync(auditPath) ? fs.readFileSync(auditPath, "utf8") : "";
  const repoAuditPath = path.join(__dirname, "..", "bridge-audit.log");
  win.destroy();
  return {
    preloadReady,
    readOnlyWorks: readResult === false,
    highRiskBlocked: highRiskResult?.ok === false && /explicit user presence|presence|Sicherheitsfreigabe|safety gate|local action was not started/i.test(String(highRiskResult?.code || highRiskResult?.message || "")),
    highRiskDidNotExecute: smokeAutostartWrites === beforeWrites,
    auditUnderUserData: auditPath.startsWith(app.getPath("userData")) && fs.existsSync(auditPath),
    noRepoBridgeAudit: !fs.existsSync(repoAuditPath),
    auditRedacted: !/smoke-local-token|SECRET|TOKEN|api[_-]?key/i.test(auditText),
    highRiskResult,
  };
}

async function main() {
  const securityProbe = await runBridgeSecurityProbe();
  process.env.LEXA_ELECTRON_SMOKE_MOCK = "1";
  const rendererErrors = [];
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
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
    const looksFatal = /\b(LEXA ERROR|Unhandled|TypeError|ReferenceError|SyntaxError|RangeError)\b/i.test(text);
    if (level >= 3 || looksFatal) {
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
  await new Promise((resolve) => setTimeout(resolve, 1800));

  const result = await win.webContents.executeJavaScript(`
    (async () => {
      const canvas = document.getElementById("lexa-ambient-canvas");
      const ctx = canvas?.getContext("2d");
      const w = canvas?.width || 0;
      const h = canvas?.height || 0;
      const sample = ctx && w && h
        ? Array.from(ctx.getImageData(Math.floor(w / 2), Math.floor(h / 2), 1, 1).data)
        : [0, 0, 0, 0];

      const input = document.getElementById("chat-input");
      const button = document.getElementById("composer-command-btn");
      const palette = document.getElementById("composer-command-palette");
      if (typeof setupComposerCommandPalette === "function") setupComposerCommandPalette();
      if (input) {
        input.value = "/";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const slashOpen = palette && !palette.classList.contains("hidden");
      const itemCount = palette ? palette.querySelectorAll(".composer-command-item").length : 0;
      const activeId = input?.getAttribute("aria-activedescendant") || "";
      const activeOption = activeId ? document.getElementById(activeId) : null;
      const composerAliasRows = {};
      for (const id of ["research", "workspace", "context", "review", "skill", "think", "ship"]) {
        const row = palette?.querySelector(\`.composer-command-item[data-command-id="\${id}"]\`);
        composerAliasRows[id] = {
          prefix: row?.querySelector(".composer-command-prefix")?.textContent?.trim() || "",
          aria: row?.getAttribute("aria-label") || "",
          title: row?.getAttribute("title") || "",
        };
      }
      const composerSlashState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        buttonExpanded: button?.getAttribute("aria-expanded") || "",
        activeId,
        activeOptionSelected: activeOption?.getAttribute("aria-selected") || "",
        activeOptionLabel: activeOption?.getAttribute("aria-label") || "",
      };
      if (input) {
        input.value = "/c";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const contextAliasActiveId = input?.getAttribute("aria-activedescendant") || "";
      const contextAliasActiveOption = contextAliasActiveId ? document.getElementById(contextAliasActiveId) : null;
      const composerContextAliasSearchState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        activeId: contextAliasActiveId,
        commandId: contextAliasActiveOption?.dataset?.commandId || "",
        selected: contextAliasActiveOption?.getAttribute("aria-selected") || "",
        prefix: contextAliasActiveOption?.querySelector(".composer-command-prefix")?.textContent?.trim() || "",
        aria: contextAliasActiveOption?.getAttribute("aria-label") || "",
      };
      if (input) {
        input.value = "/rv";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const reviewAliasActiveId = input?.getAttribute("aria-activedescendant") || "";
      const reviewAliasActiveOption = reviewAliasActiveId ? document.getElementById(reviewAliasActiveId) : null;
      const composerReviewAliasSearchState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        activeId: reviewAliasActiveId,
        commandId: reviewAliasActiveOption?.dataset?.commandId || "",
        selected: reviewAliasActiveOption?.getAttribute("aria-selected") || "",
        prefix: reviewAliasActiveOption?.querySelector(".composer-command-prefix")?.textContent?.trim() || "",
        aria: reviewAliasActiveOption?.getAttribute("aria-label") || "",
      };
      if (input) {
        input.value = "/sk";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const skillAliasActiveId = input?.getAttribute("aria-activedescendant") || "";
      const skillAliasActiveOption = skillAliasActiveId ? document.getElementById(skillAliasActiveId) : null;
      const composerSkillAliasSearchState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        activeId: skillAliasActiveId,
        commandId: skillAliasActiveOption?.dataset?.commandId || "",
        selected: skillAliasActiveOption?.getAttribute("aria-selected") || "",
        prefix: skillAliasActiveOption?.querySelector(".composer-command-prefix")?.textContent?.trim() || "",
        aria: skillAliasActiveOption?.getAttribute("aria-label") || "",
      };
      if (input) {
        input.value = "/dt";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const thinkAliasActiveId = input?.getAttribute("aria-activedescendant") || "";
      const thinkAliasActiveOption = thinkAliasActiveId ? document.getElementById(thinkAliasActiveId) : null;
      const composerThinkAliasSearchState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        activeId: thinkAliasActiveId,
        commandId: thinkAliasActiveOption?.dataset?.commandId || "",
        selected: thinkAliasActiveOption?.getAttribute("aria-selected") || "",
        prefix: thinkAliasActiveOption?.querySelector(".composer-command-prefix")?.textContent?.trim() || "",
        aria: thinkAliasActiveOption?.getAttribute("aria-label") || "",
      };
      if (input) {
        input.value = "/rl";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const shipAliasActiveId = input?.getAttribute("aria-activedescendant") || "";
      const shipAliasActiveOption = shipAliasActiveId ? document.getElementById(shipAliasActiveId) : null;
      const composerShipAliasSearchState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        activeId: shipAliasActiveId,
        commandId: shipAliasActiveOption?.dataset?.commandId || "",
        selected: shipAliasActiveOption?.getAttribute("aria-selected") || "",
        prefix: shipAliasActiveOption?.querySelector(".composer-command-prefix")?.textContent?.trim() || "",
        aria: shipAliasActiveOption?.getAttribute("aria-label") || "",
      };
      if (input) {
        input.value = "/w";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const aliasActiveId = input?.getAttribute("aria-activedescendant") || "";
      const aliasActiveOption = aliasActiveId ? document.getElementById(aliasActiveId) : null;
      const composerAliasSearchState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        activeId: aliasActiveId,
        commandId: aliasActiveOption?.dataset?.commandId || "",
        selected: aliasActiveOption?.getAttribute("aria-selected") || "",
        prefix: aliasActiveOption?.querySelector(".composer-command-prefix")?.textContent?.trim() || "",
        aria: aliasActiveOption?.getAttribute("aria-label") || "",
      };
      if (button) button.click();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const closedAfterButton = palette ? palette.classList.contains("hidden") : false;
      if (button) {
        button.focus();
        button.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
      }
      await new Promise((resolve) => setTimeout(resolve, 160));
      const composerButtonKeyState = {
        open: palette ? !palette.classList.contains("hidden") : false,
        activeElementId: document.activeElement?.id || "",
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
      };
      if (typeof closeComposerCommandPalette === "function") closeComposerCommandPalette();

      const notifButton = document.getElementById("notif-bell-btn");
      const notifPanel = document.getElementById("notif-center");
      notifButton?.focus();
      notifButton?.click();
      await new Promise((resolve) => setTimeout(resolve, 160));
      const notifPanelRect = notifPanel?.getBoundingClientRect();
      const notifButtonRect = notifButton?.getBoundingClientRect();
      const notifSampleX = notifPanelRect
        ? Math.min(Math.max(notifPanelRect.left + 16, 0), window.innerWidth - 1)
        : 0;
      const notifSampleY = notifPanelRect
        ? Math.min(Math.max(notifPanelRect.top + 16, 0), window.innerHeight - 1)
        : 0;
      const notifTopElement = notifPanel ? document.elementFromPoint(notifSampleX, notifSampleY) : null;
      const notifPanelStyle = notifPanel ? getComputedStyle(notifPanel) : null;
      const notifOpenState = {
        panelOpen: notifPanel ? !notifPanel.classList.contains("hidden") : false,
        panelHidden: notifPanel?.getAttribute("aria-hidden") || "",
        buttonExpanded: notifButton?.getAttribute("aria-expanded") || "",
        activeElementClass: String(document.activeElement?.className || ""),
        panelPosition: notifPanelStyle?.position || "",
        panelZIndex: Number.parseInt(notifPanelStyle?.zIndex || "0", 10) || 0,
        panelBelowButton: notifPanelRect && notifButtonRect
          ? notifPanelRect.top >= notifButtonRect.bottom + 6
          : false,
        panelInViewport: notifPanelRect
          ? notifPanelRect.left >= 0 &&
            notifPanelRect.top >= 0 &&
            notifPanelRect.right <= window.innerWidth &&
            notifPanelRect.bottom <= window.innerHeight
          : false,
        panelTopMost: Boolean(notifTopElement && notifPanel?.contains(notifTopElement)),
        panelRect: notifPanelRect ? {
          left: Math.round(notifPanelRect.left),
          top: Math.round(notifPanelRect.top),
          right: Math.round(notifPanelRect.right),
          bottom: Math.round(notifPanelRect.bottom),
        } : null,
        buttonRect: notifButtonRect ? {
          left: Math.round(notifButtonRect.left),
          top: Math.round(notifButtonRect.top),
          right: Math.round(notifButtonRect.right),
          bottom: Math.round(notifButtonRect.bottom),
        } : null,
      };
      notifPanel?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 120));
      const notifClosedState = {
        panelClosed: notifPanel ? notifPanel.classList.contains("hidden") : false,
        panelHidden: notifPanel?.getAttribute("aria-hidden") || "",
        buttonExpanded: notifButton?.getAttribute("aria-expanded") || "",
        activeElementId: document.activeElement?.id || "",
      };

      const voiceStatusBar = document.getElementById("voice-status-bar");
      let voiceStatus = { bar: Boolean(voiceStatusBar), available: typeof VoiceStatusBar !== "undefined" };
      let orbListeningSurface = { available: typeof voiceStatusBarUpdate === "function" };
      if (voiceStatusBar && typeof VoiceStatusBar !== "undefined") {
        VoiceStatusBar.show();
        VoiceStatusBar.setState("listening");
        VoiceStatusBar.setProvider("Verarbeitung");
        VoiceStatusBar.setTranscript("Ich nutze den stabilen Sprachweg.");
        await new Promise((resolve) => setTimeout(resolve, 80));
        const rect = voiceStatusBar.getBoundingClientRect();
        const style = getComputedStyle(voiceStatusBar);
        const mainRect = document.querySelector(".main-layout")?.getBoundingClientRect();
        voiceStatus = {
          ...voiceStatus,
          visible: !voiceStatusBar.classList.contains("hidden"),
          position: style.position,
          zIndex: Number.parseInt(style.zIndex || "0", 10) || 0,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          top: Math.round(rect.top),
          left: Math.round(rect.left),
          inViewport: rect.left >= 0 && rect.top >= 0 && rect.right <= window.innerWidth && rect.bottom <= window.innerHeight,
          mainTop: Math.round(mainRect?.top || 0),
        };
        VoiceStatusBar.hide();
      }
      if (voiceStatusBar && typeof voiceStatusBarUpdate === "function") {
        const orbCanvas = document.getElementById("voice-orb-canvas");
        const orbContainer = document.getElementById("voice-orb-container");
        window.__lexaOrbVoiceActive = true;
        voiceStatusBarUpdate({ state: "listening", transcript: "", provider: "Recording" });
        await new Promise((resolve) => setTimeout(resolve, 120));
        const orbStyle = orbCanvas ? getComputedStyle(orbCanvas) : null;
        orbListeningSurface = {
          ...orbListeningSurface,
          statusHidden: voiceStatusBar.classList.contains("hidden"),
          orbCanvas: Boolean(orbCanvas),
          canvasListening: Boolean(orbCanvas?.classList.contains("conv-listening")),
          containerListening: orbContainer?.dataset?.convState === "listening",
          transform: orbStyle?.transform || "",
          filter: orbStyle?.filter || "",
          animationName: orbStyle?.animationName || "",
        };
        if (typeof voiceStatusBarReset === "function") voiceStatusBarReset({ hide: true });
        else {
          window.__lexaOrbVoiceActive = false;
          if (typeof window.setOrbConversationState === "function") window.setOrbConversationState(null);
          VoiceStatusBar.hide();
        }
      }

      const measureActiveView = (view) => {
        const active = view === "chat"
          ? document.querySelector(".chat-container")
          : document.querySelector(".tool-view.active");
        const rect = active?.getBoundingClientRect();
        return {
          view,
          activeId: active?.id || "",
          missing: !active,
          width: Math.round(rect?.width || 0),
          documentOverflow: Math.max(0, Math.round(document.documentElement.scrollWidth - window.innerWidth)),
          viewOverflow: active ? Math.max(0, Math.round(active.scrollWidth - active.clientWidth)) : 0,
        };
      };
      const layout = [];
      const views = ["chat", "dashboard", "system", "commands", "productivity", "memory", "personal-os", "settings"];
      for (const view of views) {
        if (typeof switchView === "function") switchView(view);
        await new Promise((resolve) => setTimeout(resolve, 80));
        layout.push(measureActiveView(view));
      }
      const nativeActionTags = new Set(["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "OPTION", "LABEL"]);
      const actionElements = Array.from(document.querySelectorAll("[data-action]"));
      const nonNativeActions = actionElements.filter((el) => !nativeActionTags.has(el.tagName));
      const inaccessibleActions = nonNativeActions
        .filter((el) => el.getAttribute("role") !== "button" || el.tabIndex < 0)
        .map((el) => ({
          tag: el.tagName,
          action: el.dataset.action || "",
          className: String(el.className || "").slice(0, 80),
        }));
      const agentStepLabels = typeof agentStepDisplayLabel === "function" && typeof agentStepTechnicalLabel === "function"
        ? {
            web: agentStepDisplayLabel({ action: "web_open", params: { url: "https://example.com/report" } }),
            personalOs: agentStepDisplayLabel({ action: "personal_os_query", params: { query: "Lexa release" } }),
            technical: agentStepTechnicalLabel({ action: "personal_os_query", params: { query: "Lexa release", area: "08_Lexa" } }),
            foundOutcome: typeof agentStepOutcomeLabel === "function" && typeof agentStepOutcomeKind === "function"
              ? agentStepOutcomeLabel(agentStepOutcomeKind({ action: "web_open", status: "success" }))
              : "",
            changedOutcome: typeof agentStepOutcomeLabel === "function" && typeof agentStepOutcomeKind === "function"
              ? agentStepOutcomeLabel(agentStepOutcomeKind({ action: "memory_add", status: "success" }))
              : "",
            blockedOutcome: typeof agentStepOutcomeLabel === "function" && typeof agentStepOutcomeKind === "function"
              ? agentStepOutcomeLabel(agentStepOutcomeKind({ action: "system_shutdown", status: "needs_confirmation" }))
              : "",
            failedOutcome: typeof agentStepOutcomeLabel === "function" && typeof agentStepOutcomeKind === "function"
              ? agentStepOutcomeLabel(agentStepOutcomeKind({ action: "web_open", status: "failed" }))
              : "",
            runSummary: (() => {
              if (typeof agentRunOutcomeCounts !== "function" || typeof renderAgentOutcomeSummary !== "function") return {};
              const summary = document.createElement("div");
              const counts = agentRunOutcomeCounts([
                { action: "web_open", status: "success" },
                { action: "memory_add", status: "success" },
                { action: "system_shutdown", status: "needs_confirmation" },
                { action: "web_open", status: "failed" },
              ]);
              renderAgentOutcomeSummary(summary, counts);
              return {
                text: summary.textContent,
                aria: summary.getAttribute("aria-label") || "",
                hidden: summary.hidden,
                chipCount: summary.querySelectorAll(".agent-outcome-chip").length,
              };
            })(),
            completion: (() => {
              if (typeof renderAgentCompletionPanel !== "function" || typeof agentRunOutcomeCounts !== "function") return {};
              const panel = document.createElement("div");
              const steps = [
                { action: "web_open", status: "success" },
                { action: "memory_add", status: "success" },
                { action: "system_shutdown", status: "needs_confirmation" },
                { action: "web_open", status: "failed" },
              ];
              const counts = agentRunOutcomeCounts(steps);
              const continuePrompt = typeof agentCompletionContinuePrompt === "function"
                ? agentCompletionContinuePrompt({ steps, summary: "Prior summary" }, counts, "Prior summary")
                : { text: "", cursorStart: 0 };
              renderAgentCompletionPanel(panel, counts, { continuePrompt });
              const button = panel.querySelector(".agent-completion-continue-btn");
              const input = document.getElementById("chat-input");
              const oldInput = input?.value || "";
              const oldDraft = localStorage.getItem("lexa-chat-draft");
              button?.click();
              const clickedDraft = input?.value || "";
              const storedDraft = localStorage.getItem("lexa-chat-draft") || "";
              const focused = document.activeElement === input;
              const feedbackIcon = button?.dataset?.icon || "";
              const feedbackLabel = button?.getAttribute("aria-label") || "";
              const textPreserved = /continue|weiterarbeiten/i.test(button?.textContent || "");
              if (input) input.value = oldInput;
              if (oldDraft === null || oldDraft === undefined) localStorage.removeItem("lexa-chat-draft");
              else localStorage.setItem("lexa-chat-draft", oldDraft);
              return {
                text: panel.textContent,
                aria: panel.getAttribute("aria-label") || "",
                hidden: panel.hidden,
                state: panel.querySelector(".agent-completion-state")?.textContent || "",
                itemCount: panel.querySelectorAll(".agent-completion-item").length,
                buttonText: button?.textContent || "",
                promptText: continuePrompt.text,
                promptCursor: continuePrompt.cursorStart,
                clickedDraft,
                storedDraft,
                focused,
                feedbackIcon,
                feedbackLabel,
                textPreserved,
                resolve: (() => {
                  if (typeof startAgentCompletionResolve !== "function" || typeof setMessagePersistText !== "function" || typeof setMessageAgentRunMeta !== "function" || typeof agentRunAttentionResolvedCacheKey !== "function") return {};
                  const oldConv = LexaState.get("currentConversationId");
                  const convId = 987656;
                  const summary = "Completion attention summary";
                  localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
                  LexaState.set("currentConversationId", convId);
                  const msg = document.createElement("div");
                  msg.className = "message system-message";
                  setMessagePersistText(msg, summary);
                  setMessageAgentRunMeta(msg, { summary, steps, counts });
                  const body = document.createElement("div");
                  const resolvePanel = document.createElement("div");
                  body.appendChild(resolvePanel);
                  msg.appendChild(body);
                  document.body.appendChild(msg);
                  renderAgentCompletionPanel(resolvePanel, counts, { continuePrompt });
                  const resolveBtn = resolvePanel.querySelector(".agent-completion-resolve-btn");
                  const beforeText = resolveBtn?.textContent || "";
                  const resolveResult = startAgentCompletionResolve(resolveBtn);
                  const raw = localStorage.getItem(agentRunAttentionResolvedCacheKey(convId)) || "";
                  const afterText = resolveBtn?.textContent || "";
                  const disabled = Boolean(resolveBtn?.disabled);
                  const resolvedState = resolveBtn?.dataset?.resolved || "";
                  const undoResult = startAgentCompletionResolve(resolveBtn);
                  const rawAfterUndo = localStorage.getItem(agentRunAttentionResolvedCacheKey(convId)) || "";
                  const undoText = resolveBtn?.textContent || "";
                  const undoState = resolveBtn?.dataset?.resolved || "";
                  msg.remove();
                  localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
                  LexaState.set("currentConversationId", oldConv);
                  return { beforeText, resolveResult, raw, afterText, disabled, resolvedState, undoResult, rawAfterUndo, undoText, undoState };
                })(),
              };
            })(),
            persistedMeta: (() => {
              if (typeof renderPersistedAgentRunMeta !== "function" || typeof setMessageAgentRunMeta !== "function" || typeof getMessageAgentRunMeta !== "function" || typeof agentRunOutcomeCounts !== "function") return {};
              const steps = [
                { action: "web_open", status: "success" },
                { action: "memory_add", status: "success" },
                { action: "web_open", status: "failed" },
              ];
              const meta = { summary: "Persisted summary", steps, counts: agentRunOutcomeCounts(steps), total_duration_ms: 123 };
              const msg = document.createElement("div");
              msg.className = "message system-message";
              setMessageAgentRunMeta(msg, meta);
              const body = document.createElement("div");
              renderPersistedAgentRunMeta(body, getMessageAgentRunMeta(msg), "Persisted summary");
              return {
                type: getMessageAgentRunMeta(msg)?.type || "",
                text: body.textContent,
                completionCount: body.querySelectorAll(".agent-completion-panel").length,
                outcomeCount: body.querySelectorAll(".agent-outcome-chip").length,
                hasAgentClass: msg.classList.contains("agent-message"),
              };
            })(),
            attention: (() => {
              if (typeof renderAgentAttentionPanel !== "function" || typeof agentRunAttentionForConversation !== "function" || typeof agentRunMetaCacheKey !== "function" || typeof agentRunOutcomeCounts !== "function" || typeof renderConversationList !== "function" || typeof toggleAgentAttentionFilter !== "function" || typeof resolveAgentAttentionForConversation !== "function" || typeof agentRunAttentionResolvedCacheKey !== "function" || typeof agentRunAttentionResolvedHistoryCacheKey !== "function" || typeof agentRunAttentionResolvedHistory !== "function" || typeof agentRunAttentionResolvedHistoryMaxAgeMs !== "function" || typeof restoreAgentAttentionHistoryItem !== "function" || typeof updateAgentAttentionHeaderSummary !== "function") return {};
              const steps = [
                { action: "web_open", status: "failed" },
                { action: "system_shutdown", status: "needs_confirmation" },
              ];
              const meta = { summary: "Attention summary", steps, counts: agentRunOutcomeCounts(steps) };
              const oldList = LexaState.get("conversationsList") || [];
              const oldFilter = LexaState.get("conversationAttentionOnly");
              localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
              LexaState.set("conversationsList", [
                { id: 987652, title: "Clean Agent Run", message_count: 1, last_message: "Done" },
              ]);
              LexaState.set("conversationAttentionOnly", false);
              renderConversationList();
              const zeroSummary = document.getElementById("agent-attention-summary");
              const zeroHeaderText = zeroSummary?.textContent || "";
              const zeroHeaderLabel = zeroSummary?.getAttribute("aria-label") || "";
              const zeroHeaderHidden = Boolean(zeroSummary?.hidden);
              const zeroFilterHidden = Boolean(document.getElementById("agent-attention-filter-btn")?.hidden);
              const zeroPanelCount = document.querySelectorAll("#conversation-list .agent-attention-panel, #conversation-list .agent-resolved-panel").length;
              const staleKey = "assistant:stale";
              localStorage.setItem(agentRunMetaCacheKey(987653), JSON.stringify([{ key: staleKey, meta }]));
              localStorage.setItem(agentRunAttentionResolvedCacheKey(987653), JSON.stringify([staleKey]));
              localStorage.setItem(agentRunAttentionResolvedHistoryCacheKey(), JSON.stringify([{
                convId: 987653,
                title: "Old Agent Run",
                failed: 1,
                blocked: 0,
                keys: [staleKey],
                resolved_at: Date.now() - agentRunAttentionResolvedHistoryMaxAgeMs() - 1000,
              }]));
              const stalePrunedCount = agentRunAttentionResolvedHistory().length;
              const staleHistoryRaw = localStorage.getItem(agentRunAttentionResolvedHistoryCacheKey()) || "";
              localStorage.removeItem(agentRunMetaCacheKey(987653));
              localStorage.removeItem(agentRunAttentionResolvedCacheKey(987653));
              localStorage.removeItem(agentRunAttentionResolvedCacheKey(987654));
              localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
              localStorage.setItem(agentRunMetaCacheKey(987656), JSON.stringify([{ key: "assistant:orphan", meta }]));
              localStorage.setItem(agentRunAttentionResolvedCacheKey(987656), JSON.stringify(["assistant:orphan"]));
              localStorage.setItem(agentRunAttentionResolvedHistoryCacheKey(), JSON.stringify([{
                convId: 987656,
                title: "Orphan Agent Run",
                failed: 1,
                blocked: 0,
                keys: ["assistant:orphan"],
                resolved_at: Date.now(),
              }]));
              localStorage.setItem(agentRunMetaCacheKey(987654), JSON.stringify([{ key: "assistant:test", meta }]));
              const container = document.createElement("div");
              const rendered = renderAgentAttentionPanel(container, [{ id: 987654, title: "Blocked Agent Run" }]);
              const attention = agentRunAttentionForConversation({ id: 987654, title: "Blocked Agent Run" });
              LexaState.set("conversationsList", [
                { id: 987654, title: "Blocked Agent Run", message_count: 2, last_message: "Needs confirmation" },
                { id: 987655, title: "Clean Agent Run", message_count: 1, last_message: "Done" },
              ]);
              LexaState.set("conversationAttentionOnly", false);
              renderConversationList();
              const orphanHistoryRaw = localStorage.getItem(agentRunAttentionResolvedHistoryCacheKey()) || "";
              const headerText = document.getElementById("agent-attention-summary")?.textContent || "";
              const headerLabel = document.getElementById("agent-attention-summary")?.getAttribute("aria-label") || "";
              const filterButton = document.getElementById("agent-attention-filter-btn");
              const beforeFilterCount = document.querySelectorAll("#conversation-list .conv-item").length;
              const beforePressed = filterButton?.getAttribute("aria-pressed") || "";
              toggleAgentAttentionFilter();
              const afterFilterCount = document.querySelectorAll("#conversation-list .conv-item").length;
              const afterPressed = filterButton?.getAttribute("aria-pressed") || "";
              const filterText = document.getElementById("conversation-list")?.textContent || "";
              const badgeText = document.querySelector("#conversation-list .conv-agent-attention-badge")?.textContent || "";
              const resolveButtonCount = document.querySelectorAll(".agent-attention-resolve-btn, .conv-agent-resolve-btn").length;
              const resolveResult = resolveAgentAttentionForConversation(987654, "Blocked Agent Run");
              const afterResolveAttention = agentRunAttentionForConversation({ id: 987654, title: "Blocked Agent Run" });
              const afterResolveCount = document.querySelectorAll("#conversation-list .conv-item.needs-agent-attention").length;
              const resolvedRaw = localStorage.getItem(agentRunAttentionResolvedCacheKey(987654)) || "";
              const headerAfterResolveText = document.getElementById("agent-attention-summary")?.textContent || "";
              const afterResolveFilterState = Boolean(LexaState.get("conversationAttentionOnly"));
              const afterResolveFilterHidden = Boolean(document.getElementById("agent-attention-filter-btn")?.hidden);
              const afterResolveFilterPressed = document.getElementById("agent-attention-filter-btn")?.getAttribute("aria-pressed") || "";
              const afterResolveVisibleCount = document.querySelectorAll("#conversation-list .conv-item").length;
              const historyText = document.querySelector("#conversation-list .agent-resolved-panel")?.textContent || "";
              const historyCount = document.querySelectorAll("#conversation-list .agent-resolved-row").length;
              const historyItem = agentRunAttentionResolvedHistory()[0];
              const restoreResult = restoreAgentAttentionHistoryItem(historyItem);
              const afterRestoreAttention = agentRunAttentionForConversation({ id: 987654, title: "Blocked Agent Run" });
              const rawAfterRestore = localStorage.getItem(agentRunAttentionResolvedCacheKey(987654)) || "";
              const headerAfterRestoreText = document.getElementById("agent-attention-summary")?.textContent || "";
              const historyAfterRestoreCount = document.querySelectorAll("#conversation-list .agent-resolved-row").length;
              localStorage.removeItem(agentRunMetaCacheKey(987654));
              localStorage.removeItem(agentRunMetaCacheKey(987656));
              localStorage.removeItem(agentRunAttentionResolvedCacheKey(987654));
              localStorage.removeItem(agentRunAttentionResolvedCacheKey(987656));
              localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
              LexaState.set("conversationAttentionOnly", oldFilter);
              LexaState.set("conversationsList", oldList);
              renderConversationList();
              return {
                rendered,
                text: container.textContent,
                itemCount: container.querySelectorAll(".agent-attention-item").length,
                attention,
                zeroHeaderText,
                zeroHeaderLabel,
                zeroHeaderHidden,
                zeroFilterHidden,
                zeroPanelCount,
                stalePrunedCount,
                staleHistoryRaw,
                orphanHistoryRaw,
                filterButtonHidden: Boolean(filterButton?.hidden),
                beforeFilterCount,
                afterFilterCount,
                beforePressed,
                afterPressed,
                filterText,
                headerText,
                headerLabel,
                badgeText,
                resolveButtonCount,
                resolveResult,
                afterResolveAttention,
                afterResolveCount,
                resolvedRaw,
                headerAfterResolveText,
                afterResolveFilterState,
                afterResolveFilterHidden,
                afterResolveFilterPressed,
                afterResolveVisibleCount,
                historyText,
                historyCount,
                restoreResult,
                afterRestoreAttention,
                rawAfterRestore,
                headerAfterRestoreText,
                historyAfterRestoreCount,
              };
            })(),
          }
        : {};

      return {
        ambient: {
          exists: Boolean(canvas),
          width: w,
          height: h,
          frame: window.__lexaAmbientDebug?.frame || 0,
          sample,
          nonBlank: sample[3] > 0 && (sample[0] + sample[1] + sample[2]) > 0,
        },
        composer: {
          button: Boolean(button),
          palette: Boolean(palette),
          slashOpen: Boolean(slashOpen),
          itemCount,
          slashState: composerSlashState,
          aliasRows: composerAliasRows,
          contextAliasSearchState: composerContextAliasSearchState,
          reviewAliasSearchState: composerReviewAliasSearchState,
          skillAliasSearchState: composerSkillAliasSearchState,
          thinkAliasSearchState: composerThinkAliasSearchState,
          shipAliasSearchState: composerShipAliasSearchState,
          aliasSearchState: composerAliasSearchState,
          closedAfterButton,
          buttonKeyState: composerButtonKeyState,
        },
        notifications: {
          button: Boolean(notifButton),
          panel: Boolean(notifPanel),
          openState: notifOpenState,
          closedState: notifClosedState,
        },
        voiceStatus,
        orbListeningSurface,
        layout,
        accessibility: {
          actions: actionElements.length,
          nonNativeActions: nonNativeActions.length,
          inaccessibleActions,
        },
        agentStepLabels,
        graphFocusWired: typeof setupPersonalOsGraphFocus === "function",
      };
    })();
  `);

  win.setSize(390, 760);
  try {
    win.webContents.debugger.attach("1.3");
  } catch (_error) {
    // The debugger may already be attached in some Electron harnesses.
  }
  try {
    await win.webContents.debugger.sendCommand("Emulation.setTouchEmulationEnabled", {
      enabled: true,
      maxTouchPoints: 1,
    });
  } catch (error) {
    rendererErrors.push({ level: 3, message: `touch emulation failed: ${error?.message || error}` });
  }
  await new Promise((resolve) => setTimeout(resolve, 300));
  result.mobile = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof switchView === "function") switchView("settings");
      await new Promise((resolve) => setTimeout(resolve, 100));
      const active = document.querySelector(".tool-view.active");
      return {
        width: window.innerWidth,
        activeId: active?.id || "",
        documentOverflow: Math.max(0, Math.round(document.documentElement.scrollWidth - window.innerWidth)),
        viewOverflow: active ? Math.max(0, Math.round(active.scrollWidth - active.clientWidth)) : 0,
        settingGrid: getComputedStyle(document.querySelector(".setting-item") || document.body).gridTemplateColumns,
      };
    })();
  `);
  result.mobileSidebar = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof renderConversationList !== "function" || typeof agentRunMetaCacheKey !== "function" || typeof agentRunAttentionResolvedCacheKey !== "function" || typeof agentRunAttentionResolvedHistoryCacheKey !== "function" || typeof agentRunOutcomeCounts !== "function") return {};
      const oldList = LexaState.get("conversationsList") || [];
      const oldFilter = LexaState.get("conversationAttentionOnly");
      const openId = 777001;
      const resolvedId = 777002;
      const openKey = "assistant:mobile-open";
      const resolvedKey = "assistant:mobile-resolved";
      const steps = [
        { action: "web_open", status: "failed" },
        { action: "system_shutdown", status: "needs_confirmation" },
      ];
      const meta = { summary: "Mobile attention summary", steps, counts: agentRunOutcomeCounts(steps) };
      localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
      localStorage.setItem(agentRunMetaCacheKey(openId), JSON.stringify([{ key: openKey, meta }]));
      localStorage.setItem(agentRunMetaCacheKey(resolvedId), JSON.stringify([{ key: resolvedKey, meta }]));
      localStorage.setItem(agentRunAttentionResolvedCacheKey(resolvedId), JSON.stringify([resolvedKey]));
      localStorage.setItem(agentRunAttentionResolvedHistoryCacheKey(), JSON.stringify([{
        convId: resolvedId,
        title: "Mobile Done Agent Run With Long Localized Label",
        failed: 1,
        blocked: 1,
        keys: [resolvedKey],
        resolved_at: Date.now(),
      }]));
      LexaState.set("conversationsList", [
        { id: openId, title: "Mobile Blocked Agent Run With Long Localized Label", message_count: 3, last_message: "Needs confirmation from the user" },
        { id: resolvedId, title: "Mobile Done Agent Run With Long Localized Label", message_count: 2, last_message: "Resolved locally" },
      ]);
      LexaState.set("conversationAttentionOnly", false);
      renderConversationList();
      const sidebar = document.querySelector(".sidebar");
      const overlay = document.getElementById("nav-overlay");
      sidebar?.classList.add("open");
      overlay?.classList.add("visible");
      await new Promise((resolve) => setTimeout(resolve, 100));
      const summary = document.getElementById("agent-attention-summary");
      const label = document.querySelector(".conversations-section .sidebar-label");
      const list = document.getElementById("conversation-list");
      const panels = Array.from(document.querySelectorAll(".agent-attention-panel, .agent-resolved-panel"));
      const rows = Array.from(document.querySelectorAll(".agent-attention-row, .agent-resolved-row"));
      const chips = Array.from(document.querySelectorAll(".agent-attention-summary-chip"));
      const sidebarRect = sidebar?.getBoundingClientRect();
      const labelRect = label?.getBoundingClientRect();
      const summaryRect = summary?.getBoundingClientRect();
      const allMeasured = [label, summary, list, ...panels, ...rows, ...chips].filter(Boolean);
      const maxRightOverflow = sidebarRect
        ? Math.max(0, ...allMeasured.map((el) => Math.round(el.getBoundingClientRect().right - sidebarRect.right)))
        : 999;
      const minRowActionWidth = Math.min(...Array.from(document.querySelectorAll(".agent-attention-resolve-btn, .agent-resolved-restore-btn")).map((btn) => Math.round(btn.getBoundingClientRect().width)));
      const metrics = {
        width: window.innerWidth,
        sidebarWidth: Math.round(sidebarRect?.width || 0),
        documentOverflow: Math.max(0, Math.round(document.documentElement.scrollWidth - window.innerWidth)),
        sidebarOverflow: sidebar ? Math.max(0, Math.round(sidebar.scrollWidth - sidebar.clientWidth)) : 999,
        listOverflow: list ? Math.max(0, Math.round(list.scrollWidth - list.clientWidth)) : 999,
        maxRightOverflow,
        chipCount: chips.length,
        panelCount: panels.length,
        rowCount: rows.length,
        summaryWrapped: Boolean(summaryRect && labelRect && summaryRect.top > labelRect.top + 8),
        summaryDisplay: summary ? getComputedStyle(summary).display : "",
        summaryText: summary?.textContent || "",
        minRowActionWidth: Number.isFinite(minRowActionWidth) ? minRowActionWidth : 0,
      };
      localStorage.removeItem(agentRunMetaCacheKey(openId));
      localStorage.removeItem(agentRunMetaCacheKey(resolvedId));
      localStorage.removeItem(agentRunAttentionResolvedCacheKey(openId));
      localStorage.removeItem(agentRunAttentionResolvedCacheKey(resolvedId));
      localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
      LexaState.set("conversationAttentionOnly", oldFilter);
      LexaState.set("conversationsList", oldList);
      renderConversationList();
      sidebar?.classList.remove("open");
      overlay?.classList.remove("visible");
      return metrics;
    })();
  `);
  result.mobileChatActions = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof switchView === "function") switchView("chat");
      await new Promise((resolve) => setTimeout(resolve, 100));
      const messages = document.getElementById("chat-messages");
      if (messages) {
        messages.classList.remove("hidden");
        messages.querySelectorAll(".message").forEach((msg) => msg.remove());
      }
      window._chatViewOpen = true;
      if (typeof addMessage === "function") {
        addMessage("Touch action smoke answer with enough text to render a complete assistant action row.", "system", null, false, false);
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
      const message = Array.from(document.querySelectorAll(".message.system-message")).pop();
      const nameEl = message?.querySelector(".msg-name");
      const timeEl = message?.querySelector(".msg-time");
      if (nameEl) {
        nameEl.textContent = "Lexa Assistant Research Workspace Verification Export Mode";
        nameEl.title = nameEl.textContent;
      }
      await new Promise((resolve) => setTimeout(resolve, 60));
      const header = message?.querySelector(".msg-header");
      const headerRect = header?.getBoundingClientRect();
      const nameRect = nameEl?.getBoundingClientRect();
      const timeRect = timeEl?.getBoundingClientRect();
      const buttons = Array.from(message?.querySelectorAll(".msg-copy-btn, .msg-thumbs-btn, .msg-action-btn") || []);
      const buttonMetrics = buttons.map((button) => {
        const rect = button.getBoundingClientRect();
        const style = getComputedStyle(button);
        return {
          className: String(button.className || ""),
          left: Math.round(rect.left),
          top: Math.round(rect.top),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          opacity: Number.parseFloat(style.opacity || "0"),
          disabled: Boolean(button.disabled),
        };
      });
      const renderedButtonMetrics = buttonMetrics.filter((button) => button.width > 0 && button.height > 0);
      const visualButtons = [...renderedButtonMetrics].sort((a, b) => (a.top - b.top) || (a.left - b.left));
      const visualOrder = visualButtons.map((button) => button.className);
      const visualIndex = (className) => visualOrder.findIndex((value) => value.includes(className));
      const verifyButton = buttons.find((button) => String(button.className || "").includes("msg-verify-btn"));
      verifyButton?.focus();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const tooltipStyle = verifyButton ? getComputedStyle(verifyButton, "::after") : null;
      const tooltipContent = String(tooltipStyle?.content || "").replace(/^["']|["']$/g, "");
      const moreButton = buttons.find((button) => String(button.className || "").includes("msg-more-btn"));
      moreButton?.click();
      await new Promise((resolve) => setTimeout(resolve, 100));
      const moreWrap = message?.querySelector(".msg-more-actions");
      const moreMenu = message?.querySelector(".msg-more-menu");
      const moreMenuRect = moreMenu?.getBoundingClientRect();
      const moreMenuButtons = Array.from(moreMenu?.querySelectorAll("button") || []);
      const moreMenuButtonMetrics = moreMenuButtons.map((button) => {
        const rect = button.getBoundingClientRect();
        return {
          className: String(button.className || ""),
          label: button.getAttribute("aria-label") || "",
          role: button.getAttribute("role") || "",
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        };
      });
      const moreMenuInitialExpanded = moreButton?.getAttribute("aria-expanded") || "";
      const moreMenuInitialOpen = Boolean(moreWrap?.classList.contains("open") && moreMenuRect?.width > 0 && moreMenuRect?.height > 0);
      const oldBackendOnline = typeof LexaState?.get === "function" ? LexaState.get("backendOnline") : true;
      const workspaceButton = moreMenuButtons.find((button) => String(button.className || "").includes("msg-workspace-btn"));
      if (typeof LexaState?.set === "function") LexaState.set("backendOnline", false);
      const offlineWorkspaceExpandedBefore = moreButton?.getAttribute("aria-expanded") || "";
      const offlineWorkspaceOpenBefore = Boolean(moreWrap?.classList.contains("open"));
      workspaceButton?.click();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const offlineWorkspace = {
        available: Boolean(workspaceButton),
        openBefore: offlineWorkspaceOpenBefore,
        expandedBefore: offlineWorkspaceExpandedBefore,
        closedAfter: !moreWrap?.classList.contains("open"),
        expandedAfter: moreButton?.getAttribute("aria-expanded") || "",
        focusReturned: document.activeElement === moreButton,
        disabled: Boolean(workspaceButton?.disabled),
        busy: workspaceButton?.getAttribute("aria-busy") || "",
      };
      verifyButton?.click();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const offlineVerify = {
        available: Boolean(verifyButton),
        disabled: Boolean(verifyButton?.disabled),
        busy: verifyButton?.getAttribute("aria-busy") || "",
      };
      if (typeof LexaState?.set === "function") LexaState.set("backendOnline", oldBackendOnline);
      const customAction = document.createElement("button");
      customAction.type = "button";
      customAction.className = "msg-action-btn";
      customAction.setAttribute("aria-label", "Custom action");
      customAction.textContent = "Custom";
      customAction.addEventListener("click", () => {
        customAction.dataset.clicked = "true";
        customAction.disabled = true;
        customAction.setAttribute("aria-busy", "true");
      });
      const customWrap = typeof createMessageActionOverflowMenu === "function"
        ? createMessageActionOverflowMenu([customAction])
        : null;
      header?.appendChild(customWrap);
      const customTrigger = customWrap?.querySelector(".msg-more-btn");
      customTrigger?.click();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const customOpen = Boolean(customWrap?.classList.contains("open"));
      const customExpandedBefore = customTrigger?.getAttribute("aria-expanded") || "";
      customAction.click();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const customClosed = !customWrap?.classList.contains("open");
      const customExpandedAfter = customTrigger?.getAttribute("aria-expanded") || "";
      const customFocusReturned = document.activeElement === customTrigger;
      const customClicked = customAction.dataset.clicked === "true";
      customWrap?.remove();
      const offlineMemoryMsg = document.createElement("div");
      offlineMemoryMsg.className = "message system-message";
      offlineMemoryMsg.dataset.persistText = "Offline memory save source";
      const offlineMemoryButton = document.createElement("button");
      offlineMemoryButton.type = "button";
      if (typeof saveMessageAsMemory === "function" && typeof LexaState?.set === "function") {
        LexaState.set("backendOnline", false);
        await saveMessageAsMemory(offlineMemoryButton, offlineMemoryMsg);
        await new Promise((resolve) => setTimeout(resolve, 80));
        LexaState.set("backendOnline", oldBackendOnline);
      }
      const offlineMemory = {
        available: typeof saveMessageAsMemory === "function",
        disabled: Boolean(offlineMemoryButton.disabled),
        busy: offlineMemoryButton.getAttribute("aria-busy") || "",
      };
      return {
        touchMedia: matchMedia("(hover: none)").matches || matchMedia("(pointer: coarse)").matches,
        buttonCount: buttons.length,
        visibleButtons: renderedButtonMetrics.filter((button) => button.opacity >= 0.7).length,
        minWidth: Math.min(...renderedButtonMetrics.map((button) => button.width)),
        minHeight: Math.min(...renderedButtonMetrics.map((button) => button.height)),
        maxDisabledOpacity: Math.max(0, ...buttonMetrics.filter((button) => button.disabled).map((button) => button.opacity)),
        documentOverflow: Math.max(0, Math.round(document.documentElement.scrollWidth - window.innerWidth)),
        longName: {
          clipped: nameEl ? nameEl.scrollWidth > nameEl.clientWidth : false,
          width: Math.round(nameRect?.width || 0),
          maxWidth: Math.round(Number.parseFloat(getComputedStyle(nameEl || document.body).maxWidth) || 0),
          sameLineWithTime: Boolean(nameRect && timeRect && Math.abs(nameRect.top - timeRect.top) <= 2),
          metadataBeforeActions: Boolean(nameRect && timeRect && visualButtons[0] && nameRect.top <= visualButtons[0].top + 2 && timeRect.top <= visualButtons[0].top + 2),
          headerOverflow: header ? Math.max(0, Math.round(header.scrollWidth - header.clientWidth)) : 999,
          headerWidth: Math.round(headerRect?.width || 0),
        },
        tooltip: {
          content: tooltipContent,
          opacity: Number.parseFloat(tooltipStyle?.opacity || "0"),
          pointerEvents: tooltipStyle?.pointerEvents || "",
        },
        moreMenu: {
          triggerVisible: Boolean(moreButton && moreButton.getBoundingClientRect().width >= 32),
          expanded: moreMenuInitialExpanded,
          open: moreMenuInitialOpen,
          role: moreMenu?.getAttribute("role") || "",
          buttonCount: moreMenuButtons.length,
          minButtonWidth: Math.min(...moreMenuButtonMetrics.map((button) => button.width)),
          minButtonHeight: Math.min(...moreMenuButtonMetrics.map((button) => button.height)),
          labels: moreMenuButtonMetrics.map((button) => button.label),
          roles: moreMenuButtonMetrics.map((button) => button.role),
          afterAction: {
            customOpen,
            customExpandedBefore,
            customClosed,
            customExpandedAfter,
            customFocusReturned,
            customClicked,
          },
        },
        offlineWorkspace,
        offlineVerify,
        offlineMemory,
        visualOrder,
        priorityOrderOk:
          visualIndex("msg-copy-btn") === 0 &&
          visualIndex("msg-continue-btn") > visualIndex("msg-copy-btn") &&
          visualIndex("msg-verify-btn") > visualIndex("msg-continue-btn") &&
          visualIndex("msg-export-btn") > visualIndex("msg-verify-btn") &&
          visualIndex("msg-more-btn") > visualIndex("msg-export-btn"),
        buttonMetrics,
      };
    })();
  `);
  result.persistedConversationActions = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof switchView === "function") switchView("chat");
      await new Promise((resolve) => setTimeout(resolve, 80));
      const messages = document.getElementById("chat-messages");
      const input = document.getElementById("chat-input");
      const oldInput = input?.value || "";
      const oldDraft = localStorage.getItem("lexa-chat-draft");
      if (messages) {
        messages.classList.remove("hidden");
        messages.querySelectorAll(".message").forEach((msg) => msg.remove());
      }
      window._chatViewOpen = true;
      const source = "## Persisted Answer\\n\\n- Fact: Reloaded from a saved conversation.\\n- Evidence: Answer actions should still work.\\n\\n~~~js\\nconst persisted = true;\\n~~~";
      const helperAvailable = typeof renderPersistedConversationMessages === "function";
      if (helperAvailable) {
        renderPersistedConversationMessages([
          { role: "user", content: "What survived after reload?" },
          { role: "assistant", content: source },
        ], "smoke-persisted-conv");
      }
      await new Promise((resolve) => setTimeout(resolve, 120));
      const assistant = Array.from(document.querySelectorAll(".message.system-message")).pop();
      const persistText = typeof getMessagePersistText === "function" ? getMessagePersistText(assistant) : "";
      const copyBtn = assistant?.querySelector(".msg-copy-btn");
      const continueBtn = assistant?.querySelector(".msg-continue-btn");
      const verifyBtn = assistant?.querySelector(".msg-verify-btn");
      const exportBtn = assistant?.querySelector(".msg-export-btn");
      const moreBtn = assistant?.querySelector(".msg-more-btn");
      const memoryBtn = assistant?.querySelector(".msg-more-menu .msg-thumbs-btn");
      const workspaceBtn = assistant?.querySelector(".msg-more-menu .msg-workspace-btn");
      continueBtn?.click();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const draft = input?.value || localStorage.getItem("lexa-chat-draft") || "";
      if (input) input.value = oldInput;
      if (oldDraft === null || oldDraft === undefined) localStorage.removeItem("lexa-chat-draft");
      else localStorage.setItem("lexa-chat-draft", oldDraft);
      return {
        helperAvailable,
        assistantCount: document.querySelectorAll(".message.system-message").length,
        rawMatches: persistText === source,
        rawHasFence: persistText.includes("~~~js") && persistText.includes("const persisted = true;"),
        renderedHasHeading: Boolean(assistant?.querySelector(".msg-text")?.textContent?.includes("Persisted Answer")),
        copyAvailable: Boolean(copyBtn && !copyBtn.disabled),
        continueAvailable: Boolean(continueBtn && !continueBtn.disabled),
        verifyAvailable: Boolean(verifyBtn && !verifyBtn.disabled),
        exportAvailable: Boolean(exportBtn && !exportBtn.disabled),
        moreAvailable: Boolean(moreBtn && !moreBtn.disabled),
        memoryAvailable: Boolean(memoryBtn && !memoryBtn.disabled),
        workspaceAvailable: Boolean(workspaceBtn && !workspaceBtn.disabled),
        continueDraftHasSource: draft.includes("Persisted Answer") && draft.includes("Fact: Reloaded from a saved conversation"),
      };
    })();
  `);
  result.emptyConversationReload = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof loadChatHistory !== "function" || typeof addMessage !== "function") return {};
      const oldConv = LexaState.get("currentConversationId");
      const oldBackendOnline = LexaState.get("backendOnline");
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldHistory = localStorage.getItem("lexa-chat-history");
      const messagesEl = document.getElementById("chat-messages");
      if (messagesEl) {
        messagesEl.classList.remove("hidden");
        messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
      }
      addMessage("Stale visible row that an empty reload must remove.", "system", null, false, true);
      const before = document.querySelectorAll("#chat-messages .message").length;
      LexaState.set("currentConversationId", "empty-local-smoke");
      LexaState.set("backendOnline", false);
      localStorage.setItem("lexa-active-conversation", "empty-local-smoke");
      localStorage.setItem("lexa-chat-history", "[]");
      await loadChatHistory();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const after = document.querySelectorAll("#chat-messages .message").length;
      if (messagesEl) messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("backendOnline", oldBackendOnline);
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      if (oldHistory === null || oldHistory === undefined) localStorage.removeItem("lexa-chat-history");
      else localStorage.setItem("lexa-chat-history", oldHistory);
      return { before, after };
    })();
  `);
  result.clearAgentLocalState = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof clearChat !== "function" || typeof addMessage !== "function" || typeof renderConversationList !== "function" || typeof agentRunMetaCacheKey !== "function" || typeof agentRunAttentionResolvedCacheKey !== "function" || typeof agentRunAttentionResolvedHistoryCacheKey !== "function" || typeof agentRunOutcomeCounts !== "function" || typeof agentRunAttentionForConversation !== "function") return {};
      const convId = 889902;
      const key = "assistant:clear-state";
      const title = "Clear Agent State";
      const steps = [
        { action: "web_open", status: "failed" },
        { action: "personal_os_review_draft", status: "needs_confirmation" },
      ];
      const meta = { summary: "Clear state summary", steps, counts: agentRunOutcomeCounts(steps) };
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldFilter = LexaState.get("conversationAttentionOnly");
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldHistory = localStorage.getItem("lexa-chat-history");
      const oldMeta = localStorage.getItem(agentRunMetaCacheKey(convId));
      const oldResolved = localStorage.getItem(agentRunAttentionResolvedCacheKey(convId));
      const oldResolvedHistory = localStorage.getItem(agentRunAttentionResolvedHistoryCacheKey());
      const oldConversationUpdate = window.lexa?.conversationUpdate;
      const messagesEl = document.getElementById("chat-messages");
      if (messagesEl) {
        messagesEl.classList.remove("hidden");
        messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
      }
      LexaState.set("currentConversationId", convId);
      LexaState.set("conversationAttentionOnly", false);
      LexaState.set("conversationsList", [{ id: convId, title, message_count: 1, last_message: "Needs attention" }]);
      localStorage.setItem("lexa-active-conversation", String(convId));
      localStorage.setItem(agentRunMetaCacheKey(convId), JSON.stringify([{ key, meta }]));
      localStorage.setItem(agentRunAttentionResolvedCacheKey(convId), JSON.stringify([key]));
      localStorage.setItem(agentRunAttentionResolvedHistoryCacheKey(), JSON.stringify([{
        convId,
        title,
        failed: 1,
        blocked: 1,
        keys: [key],
        resolved_at: Date.now(),
      }]));
      addMessage("Visible row before clear.", "system", null, false, true);
      renderConversationList();
      const conversationSelector = "#conversation-list [data-conv-id='" + convId + "']";
      const beforePanels = document.querySelectorAll("#conversation-list .agent-attention-panel, #conversation-list .agent-resolved-panel").length;
      const beforePreview = document.querySelector(conversationSelector + " .conv-preview")?.textContent || "";
      const beforeAttention = agentRunAttentionForConversation({ id: convId, title });
      const beforeHistoryRaw = localStorage.getItem(agentRunAttentionResolvedHistoryCacheKey()) || "";
      if (window.lexa) window.lexa.conversationUpdate = () => Promise.reject(new Error("smoke clear sync failed"));
      clearChat();
      const afterPanelsImmediately = document.querySelectorAll("#conversation-list .agent-attention-panel, #conversation-list .agent-resolved-panel").length;
      const afterPreviewImmediately = document.querySelector(conversationSelector + " .conv-preview")?.textContent || "";
      const afterLocalConversation = (LexaState.get("conversationsList") || []).find((conv) => String(conv.id) === String(convId));
      await new Promise((resolve) => setTimeout(resolve, 160));
      const syncToastText = [...document.querySelectorAll("#toast-container .toast .toast-text")]
        .map((el) => el.textContent || "")
        .find((text) => text.includes("Sync failed") || text.includes("Sync fehlgeschlagen")) || "";
      const afterRows = document.querySelectorAll("#chat-messages .message").length;
      const afterPanels = document.querySelectorAll("#conversation-list .agent-attention-panel, #conversation-list .agent-resolved-panel").length;
      const result = {
        beforePanels,
        beforePreview,
        beforeMeta: Boolean(localStorage.getItem(agentRunMetaCacheKey(convId))),
        beforeResolvedKey: Boolean(localStorage.getItem(agentRunAttentionResolvedCacheKey(convId))),
        beforeHistory: beforeHistoryRaw.includes(title),
        beforeResolved: beforeAttention === null,
        afterRows,
        afterPanelsImmediately,
        afterPanels,
        afterPreviewImmediately,
        afterLocalCount: afterLocalConversation?.message_count,
        afterLocalLastMessage: afterLocalConversation?.last_message,
        syncToastText,
        metaGone: !localStorage.getItem(agentRunMetaCacheKey(convId)),
        resolvedGone: !localStorage.getItem(agentRunAttentionResolvedCacheKey(convId)),
        historyGone: !(localStorage.getItem(agentRunAttentionResolvedHistoryCacheKey()) || "").includes(title),
        attentionAfter: agentRunAttentionForConversation({ id: convId, title }),
      };
      if (oldMeta === null || oldMeta === undefined) localStorage.removeItem(agentRunMetaCacheKey(convId));
      else localStorage.setItem(agentRunMetaCacheKey(convId), oldMeta);
      if (oldResolved === null || oldResolved === undefined) localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
      else localStorage.setItem(agentRunAttentionResolvedCacheKey(convId), oldResolved);
      if (oldResolvedHistory === null || oldResolvedHistory === undefined) localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
      else localStorage.setItem(agentRunAttentionResolvedHistoryCacheKey(), oldResolvedHistory);
      if (window.lexa && oldConversationUpdate) window.lexa.conversationUpdate = oldConversationUpdate;
      if (oldHistory === null || oldHistory === undefined) localStorage.removeItem("lexa-chat-history");
      else localStorage.setItem("lexa-chat-history", oldHistory);
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("conversationsList", oldList);
      LexaState.set("conversationAttentionOnly", oldFilter);
      if (typeof renderConversationList === "function") renderConversationList();
      messagesEl?.querySelectorAll(".message").forEach((msg) => msg.remove());
      return result;
    })();
  `);
  result.deleteConversationBusyGuard = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof deleteConversation !== "function" || !window.lexa?.conversationDelete) return {};
      const oldDelete = window.lexa.conversationDelete;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "delete";
      document.body.appendChild(btn);
      let calls = 0;
      let rejectDelete = null;
      window.lexa.conversationDelete = () => {
        calls += 1;
        return new Promise((resolve, reject) => {
          rejectDelete = reject;
        });
      };
      const first = deleteConversation(990771, btn);
      const busyAfterFirst = btn.disabled && btn.getAttribute("aria-busy") === "true";
      const second = deleteConversation(990771, btn);
      const callsAfterSecond = calls;
      if (typeof rejectDelete === "function") rejectDelete(new Error("smoke delete failed"));
      await Promise.allSettled([first, second]);
      await new Promise((resolve) => setTimeout(resolve, 80));
      const restored = !btn.disabled && !btn.hasAttribute("aria-busy");
      const toastText = [...document.querySelectorAll("#toast-container .toast .toast-text")]
        .map((el) => el.textContent || "")
        .find((text) => text.includes("delete") || text.includes("Löschen")) || "";
      window.lexa.conversationDelete = oldDelete;
      btn.remove();
      return { calls, callsAfterSecond, busyAfterFirst, restored, toastText };
    })();
  `);
  result.deleteConversationRefreshFailure = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof deleteConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationDelete || !window.lexa?.conversations) return {};
      const deletedId = 990781;
      const keepId = 990782;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldDelete = window.lexa.conversationDelete;
      const oldConversations = window.lexa.conversations;
      document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
      LexaState.set("currentConversationId", keepId);
      LexaState.set("conversationsList", [
        { id: deletedId, title: "Delete Refresh Failure", message_count: 1, last_message: "Remove me" },
        { id: keepId, title: "Keep Chat", message_count: 2, last_message: "Keep me" },
      ]);
      localStorage.setItem("lexa-active-conversation", String(keepId));
      renderConversationList();
      window.lexa.conversationDelete = async () => ({ ok: true });
      window.lexa.conversations = async () => { throw new Error("smoke refresh failed"); };
      await deleteConversation(deletedId);
      await new Promise((resolve) => setTimeout(resolve, 120));
      const list = LexaState.get("conversationsList") || [];
      const removedLocally = !list.some((conv) => String(conv.id) === String(deletedId));
      const keptLocally = list.some((conv) => String(conv.id) === String(keepId));
      const deletedRowGone = !document.querySelector("#conversation-list [data-conv-id='" + deletedId + "']");
      const toastTexts = [...document.querySelectorAll("#toast-container .toast .toast-text")].map((el) => el.textContent || "");
      const refreshWarning = toastTexts.some((text) => text.includes("Sidebar refresh failed") || text.includes("Seitenleiste"));
      const deletedToast = toastTexts.some((text) => text.includes("Chat deleted") || text.includes("Chat gelöscht"));
      const noDeleteError = !toastTexts.some((text) => text.includes("Failed to delete") || text.includes("Fehler beim Löschen"));
      window.lexa.conversationDelete = oldDelete;
      window.lexa.conversations = oldConversations;
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("conversationsList", oldList);
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      renderConversationList();
      return { removedLocally, keptLocally, deletedRowGone, refreshWarning, deletedToast, noDeleteError };
    })();
  `);
  result.switchConversationFailureRestore = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof switchConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationGet) return {};
      const previousId = 990881;
      const missingId = 990882;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationGet = window.lexa.conversationGet;
      LexaState.set("currentConversationId", previousId);
      LexaState.set("conversationsList", [
        { id: previousId, title: "Previous Active Chat", message_count: 1, last_message: "Stay here" },
        { id: missingId, title: "Missing Chat", message_count: 1, last_message: "Do not activate" },
      ]);
      localStorage.setItem("lexa-active-conversation", String(previousId));
      renderConversationList();
      const beforeActive = document.querySelector("#conversation-list [data-conv-id='" + previousId + "']")?.classList.contains("active") === true;
      window.lexa.conversationGet = async () => ({ detail: "missing" });
      await switchConversation(missingId, true);
      await new Promise((resolve) => setTimeout(resolve, 80));
      const restoredState = String(LexaState.get("currentConversationId")) === String(previousId);
      const restoredStorage = localStorage.getItem("lexa-active-conversation") === String(previousId);
      const previousRowActive = document.querySelector("#conversation-list [data-conv-id='" + previousId + "']")?.classList.contains("active") === true;
      const missingRowInactive = document.querySelector("#conversation-list [data-conv-id='" + missingId + "']")?.classList.contains("active") === false;
      const toastText = [...document.querySelectorAll("#toast-container .toast .toast-text")]
        .map((el) => el.textContent || "")
        .find((text) => text.includes("not found") || text.includes("nicht gefunden")) || "";
      window.lexa.conversationGet = oldConversationGet;
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("conversationsList", oldList);
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      renderConversationList();
      return { beforeActive, restoredState, restoredStorage, previousRowActive, missingRowInactive, toastText };
    })();
  `);
  result.switchConversationSaveFailureWarning = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof switchConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationUpdate || !window.lexa?.conversationGet || !window.lexa?.conversationLoad) return {};
      const previousId = 990891;
      const targetId = 990892;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationUpdate = window.lexa.conversationUpdate;
      const oldConversationGet = window.lexa.conversationGet;
      const oldConversationLoad = window.lexa.conversationLoad;
      document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
      LexaState.set("currentConversationId", previousId);
      LexaState.set("conversationsList", [
        { id: previousId, title: "Unsaved Active Chat", message_count: 1, last_message: "Save should warn" },
        { id: targetId, title: "Target Chat", message_count: 1, last_message: "Load me" },
      ]);
      localStorage.setItem("lexa-active-conversation", String(previousId));
      renderConversationList();
      let updateCalls = 0;
      window.lexa.conversationUpdate = async () => {
        updateCalls += 1;
        throw new Error("smoke save failed");
      };
      window.lexa.conversationGet = async () => ({ id: targetId, title: "Target Chat", messages: [{ role: "assistant", content: "Loaded target after save warning." }] });
      window.lexa.conversationLoad = async () => ({ ok: true });
      await switchConversation(targetId, true);
      await new Promise((resolve) => setTimeout(resolve, 120));
      const targetActive = String(LexaState.get("currentConversationId")) === String(targetId);
      const targetStorage = localStorage.getItem("lexa-active-conversation") === String(targetId);
      const targetRowActive = document.querySelector("#conversation-list [data-conv-id='" + targetId + "']")?.classList.contains("active") === true;
      const warningToast = [...document.querySelectorAll("#toast-container .toast .toast-text")]
        .map((el) => el.textContent || "")
        .find((text) => text.includes("could not be saved") || text.includes("konnte vor dem Wechsel nicht gespeichert")) || "";
      window.lexa.conversationUpdate = oldConversationUpdate;
      window.lexa.conversationGet = oldConversationGet;
      window.lexa.conversationLoad = oldConversationLoad;
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("conversationsList", oldList);
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      renderConversationList();
      return { updateCalls, targetActive, targetStorage, targetRowActive, warningToast };
    })();
  `);
  result.saveConversationRefreshFailure = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof saveCurrentConversation !== "function" || typeof addMessage !== "function" || !window.lexa?.conversationUpdate || !window.lexa?.conversations) return {};
      const convId = 990896;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationUpdate = window.lexa.conversationUpdate;
      const oldConversations = window.lexa.conversations;
      const messagesEl = document.getElementById("chat-messages");
      const oldTranscript = messagesEl ? messagesEl.innerHTML : "";
      let updateCalls = 0;
      let updateId = null;
      try {
        document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
        if (messagesEl) messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
        LexaState.set("currentConversationId", convId);
        LexaState.set("conversationsList", [{ id: convId, title: "Save Refresh Warning", message_count: 1, last_message: "Old" }]);
        localStorage.setItem("lexa-active-conversation", String(convId));
        renderConversationList();
        addMessage("Save should survive sidebar refresh failure.", "user", null, false, true);
        window.lexa.conversationUpdate = async (id) => {
          updateCalls += 1;
          updateId = id;
          return { ok: true };
        };
        window.lexa.conversations = async () => { throw new Error("smoke sidebar refresh failed after save"); };
        const saved = await saveCurrentConversation({ notifyFailure: true });
        await new Promise((resolve) => setTimeout(resolve, 80));
        const toastTexts = [...document.querySelectorAll("#toast-container .toast .toast-text")].map((el) => el.textContent || "");
        const refreshWarning = toastTexts.find((text) => text.includes("Sidebar refresh failed") || text.includes("Seitenleiste konnte nicht aktualisiert")) || "";
        const noSaveWarning = !toastTexts.some((text) => text.includes("could not be saved") || text.includes("konnte vor dem Wechsel nicht gespeichert"));
        return { saved, updateCalls, updateId: String(updateId), refreshWarning, noSaveWarning };
      } finally {
        window.lexa.conversationUpdate = oldConversationUpdate;
        window.lexa.conversations = oldConversations;
        LexaState.set("currentConversationId", oldConv);
        LexaState.set("conversationsList", oldList);
        if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
        else localStorage.setItem("lexa-active-conversation", oldActive);
        if (messagesEl) messagesEl.innerHTML = oldTranscript;
        renderConversationList();
      }
    })();
  `);
  result.autoSaveDuringSwitchGuard = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof switchConversation !== "function" || typeof autoSaveConversation !== "function" || typeof addMessage !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationUpdate || !window.lexa?.conversations || !window.lexa?.conversationGet || !window.lexa?.conversationLoad) return {};
      const previousId = 990897;
      const targetId = 990898;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldBackendOnline = LexaState.get("backendOnline");
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationUpdate = window.lexa.conversationUpdate;
      const oldConversations = window.lexa.conversations;
      const oldConversationGet = window.lexa.conversationGet;
      const oldConversationLoad = window.lexa.conversationLoad;
      const messagesEl = document.getElementById("chat-messages");
      const oldTranscript = messagesEl ? messagesEl.innerHTML : "";
      const updates = [];
      let resolveGet = null;
      try {
        document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
        if (messagesEl) messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
        LexaState.set("backendOnline", true);
        LexaState.set("currentConversationId", previousId);
        LexaState.set("conversationsList", [
          { id: previousId, title: "Previous Autosave Chat", message_count: 1, last_message: "Old" },
          { id: targetId, title: "Target Autosave Chat", message_count: 1, last_message: "Target" },
        ]);
        localStorage.setItem("lexa-active-conversation", String(previousId));
        renderConversationList();
        addMessage("OLD_TRANSCRIPT_SHOULD_NOT_AUTOSAVE_TO_TARGET", "user", null, false, true);
        window.lexa.conversationUpdate = async (id, payload = {}) => {
          const text = Array.isArray(payload.messages) ? payload.messages.map((msg) => msg.content || msg.text || "").join(" ") : "";
          updates.push({ id: String(id), text });
          return { ok: true };
        };
        window.lexa.conversations = async () => ({ conversations: [
          { id: previousId, title: "Previous Autosave Chat", message_count: 1, last_message: "Old" },
          { id: targetId, title: "Target Autosave Chat", message_count: 1, last_message: "Target" },
        ] });
        window.lexa.conversationGet = async () => new Promise((resolve) => {
          resolveGet = () => resolve({ id: targetId, title: "Target Autosave Chat", messages: [{ role: "assistant", content: "TARGET_RENDERED_AFTER_SWITCH" }] });
        });
        window.lexa.conversationLoad = async () => ({ ok: true });
        const switchPromise = switchConversation(targetId, true);
        await new Promise((resolve) => setTimeout(resolve, 80));
        const activeTargetBeforeResolve = String(LexaState.get("currentConversationId")) === String(targetId);
        await autoSaveConversation();
        const updatesBeforeResolve = updates.slice();
        if (resolveGet) resolveGet();
        const switchValue = await switchPromise;
        await new Promise((resolve) => setTimeout(resolve, 120));
        const transcript = messagesEl?.textContent || "";
        const previousSave = updatesBeforeResolve.some((item) => item.id === String(previousId) && item.text.includes("OLD_TRANSCRIPT_SHOULD_NOT_AUTOSAVE_TO_TARGET"));
        const targetUpdateBeforeResolve = updatesBeforeResolve.some((item) => item.id === String(targetId));
        const targetHasOldTranscript = updates.some((item) => item.id === String(targetId) && item.text.includes("OLD_TRANSCRIPT_SHOULD_NOT_AUTOSAVE_TO_TARGET"));
        return {
          activeTargetBeforeResolve,
          updatesBeforeResolve: updatesBeforeResolve.length,
          previousSave,
          targetUpdateBeforeResolve,
          targetHasOldTranscript,
          switchValue,
          targetRendered: transcript.includes("TARGET_RENDERED_AFTER_SWITCH"),
        };
      } finally {
        window.lexa.conversationUpdate = oldConversationUpdate;
        window.lexa.conversations = oldConversations;
        window.lexa.conversationGet = oldConversationGet;
        window.lexa.conversationLoad = oldConversationLoad;
        LexaState.set("backendOnline", oldBackendOnline);
        LexaState.set("currentConversationId", oldConv);
        LexaState.set("conversationsList", oldList);
        if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
        else localStorage.setItem("lexa-active-conversation", oldActive);
        if (messagesEl) messagesEl.innerHTML = oldTranscript;
        renderConversationList();
      }
    })();
  `);
  result.autoTitleLocalIdNormalization = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof autoTitleConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationUpdate || !window.lexa?.generateTitle) return {};
      const convId = 990899;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationUpdate = window.lexa.conversationUpdate;
      const oldGenerateTitle = window.lexa.generateTitle;
      const updates = [];
      try {
        LexaState.set("currentConversationId", convId);
        LexaState.set("conversationsList", [{ id: String(convId), title: "Untitled", message_count: 1, last_message: "First" }]);
        localStorage.setItem("lexa-active-conversation", String(convId));
        renderConversationList();
        window.lexa.conversationUpdate = async (id, payload = {}) => {
          updates.push({ id: String(id), title: payload.title || "" });
          return { ok: true };
        };
        window.lexa.generateTitle = async () => ({ title: "  AI Title From Smoke  " });
        await autoTitleConversation("First user message for title");
        await new Promise((resolve) => setTimeout(resolve, 80));
        const list = LexaState.get("conversationsList") || [];
        const conv = list.find((item) => String(item.id) === String(convId));
        const rowText = document.querySelector("#conversation-list [data-conv-id='" + convId + "']")?.textContent || "";
        return {
          updateCalls: updates.length,
          updateIds: updates.map((item) => item.id).join(","),
          finalUpdateTitle: updates[updates.length - 1]?.title || "",
          localTitle: conv?.title || "",
          rowText,
        };
      } finally {
        window.lexa.conversationUpdate = oldConversationUpdate;
        window.lexa.generateTitle = oldGenerateTitle;
        LexaState.set("currentConversationId", oldConv);
        LexaState.set("conversationsList", oldList);
        if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
        else localStorage.setItem("lexa-active-conversation", oldActive);
        renderConversationList();
      }
    })();
  `);
  result.switchConversationStaleLoadGuard = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof switchConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationUpdate || !window.lexa?.conversationGet || !window.lexa?.conversationLoad) return {};
      const previousId = 990893;
      const slowId = 990894;
      const fastId = 990895;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationUpdate = window.lexa.conversationUpdate;
      const oldConversationGet = window.lexa.conversationGet;
      const oldConversationLoad = window.lexa.conversationLoad;
      const messagesEl = document.getElementById("chat-messages");
      const oldTranscript = messagesEl ? messagesEl.innerHTML : "";
      let slowResolve = null;
      try {
        document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
        if (messagesEl) messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
        LexaState.set("currentConversationId", previousId);
        LexaState.set("conversationsList", [
          { id: previousId, title: "Previous Chat", message_count: 1, last_message: "Previous" },
          { id: slowId, title: "Slow Chat", message_count: 1, last_message: "Slow" },
          { id: fastId, title: "Fast Chat", message_count: 1, last_message: "Fast" },
        ]);
        localStorage.setItem("lexa-active-conversation", String(previousId));
        renderConversationList();
        window.lexa.conversationUpdate = async () => ({ ok: true });
        window.lexa.conversationGet = async (id) => {
          if (String(id) === String(slowId)) {
            return new Promise((resolve) => {
              slowResolve = () => resolve({ id: slowId, title: "Slow Chat", messages: [{ role: "assistant", content: "SLOW_STALE_SHOULD_NOT_RENDER" }] });
            });
          }
          return { id: fastId, title: "Fast Chat", messages: [{ role: "assistant", content: "FAST_LATEST_RENDERED" }] };
        };
        window.lexa.conversationLoad = async () => ({ ok: true });
        const first = switchConversation(slowId, true);
        await new Promise((resolve) => setTimeout(resolve, 30));
        const second = switchConversation(fastId, true);
        await new Promise((resolve) => setTimeout(resolve, 60));
        const activeBeforeSlowResolve = String(LexaState.get("currentConversationId")) === String(fastId);
        if (slowResolve) slowResolve();
        const settled = await Promise.allSettled([first, second]);
        await new Promise((resolve) => setTimeout(resolve, 120));
        const transcript = messagesEl?.textContent || "";
        const activeFast = String(LexaState.get("currentConversationId")) === String(fastId);
        const storageFast = localStorage.getItem("lexa-active-conversation") === String(fastId);
        const fastRowActive = document.querySelector("#conversation-list [data-conv-id='" + fastId + "']")?.classList.contains("active") === true;
        const slowRowInactive = document.querySelector("#conversation-list [data-conv-id='" + slowId + "']")?.classList.contains("active") === false;
        const firstValue = settled[0]?.status === "fulfilled" ? settled[0].value : null;
        const secondValue = settled[1]?.status === "fulfilled" ? settled[1].value : null;
        return {
          activeBeforeSlowResolve,
          activeFast,
          storageFast,
          fastRowActive,
          slowRowInactive,
          fastText: transcript.includes("FAST_LATEST_RENDERED"),
          staleText: transcript.includes("SLOW_STALE_SHOULD_NOT_RENDER"),
          firstValue,
          secondValue,
        };
      } finally {
        window.lexa.conversationUpdate = oldConversationUpdate;
        window.lexa.conversationGet = oldConversationGet;
        window.lexa.conversationLoad = oldConversationLoad;
        LexaState.set("currentConversationId", oldConv);
        LexaState.set("conversationsList", oldList);
        if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
        else localStorage.setItem("lexa-active-conversation", oldActive);
        if (messagesEl) messagesEl.innerHTML = oldTranscript;
        renderConversationList();
      }
    })();
  `);
  result.newConversationSaveFailureWarning = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof newConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationUpdate || !window.lexa?.conversationCreate || !window.lexa?.historyClear || !window.lexa?.conversations) return {};
      const previousId = 990901;
      const newId = 990902;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationUpdate = window.lexa.conversationUpdate;
      const oldConversationCreate = window.lexa.conversationCreate;
      const oldHistoryClear = window.lexa.historyClear;
      const oldConversations = window.lexa.conversations;
      document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
      LexaState.set("currentConversationId", previousId);
      LexaState.set("conversationsList", [{ id: previousId, title: "Unsaved Before New Chat", message_count: 1, last_message: "Save should warn" }]);
      localStorage.setItem("lexa-active-conversation", String(previousId));
      renderConversationList();
      let updateCalls = 0;
      let createCalls = 0;
      window.lexa.conversationUpdate = async () => {
        updateCalls += 1;
        throw new Error("smoke save before new failed");
      };
      window.lexa.conversationCreate = async () => {
        createCalls += 1;
        return { id: newId };
      };
      window.lexa.historyClear = async () => ({ ok: true });
      window.lexa.conversations = async () => ({ conversations: [{ id: newId, title: "New Chat", message_count: 0, last_message: "" }] });
      await newConversation();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const newActive = String(LexaState.get("currentConversationId")) === String(newId);
      const newStorage = localStorage.getItem("lexa-active-conversation") === String(newId);
      const newRowActive = document.querySelector("#conversation-list [data-conv-id='" + newId + "']")?.classList.contains("active") === true;
      const toastTexts = [...document.querySelectorAll("#toast-container .toast .toast-text")].map((el) => el.textContent || "");
      const warningToast = toastTexts.find((text) => text.includes("could not be saved") || text.includes("konnte vor dem Wechsel nicht gespeichert")) || "";
      const newChatToast = toastTexts.find((text) => text.includes("New chat started") || text.includes("Neuer Chat gestartet")) || "";
      window.lexa.conversationUpdate = oldConversationUpdate;
      window.lexa.conversationCreate = oldConversationCreate;
      window.lexa.historyClear = oldHistoryClear;
      window.lexa.conversations = oldConversations;
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("conversationsList", oldList);
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      renderConversationList();
      return { updateCalls, createCalls, newActive, newStorage, newRowActive, warningToast, newChatToast };
    })();
  `);
  result.newConversationSetupRefreshFailure = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof newConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationCreate || !window.lexa?.historyClear || !window.lexa?.conversations) return {};
      const newId = 990912;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationCreate = window.lexa.conversationCreate;
      const oldHistoryClear = window.lexa.historyClear;
      const oldConversations = window.lexa.conversations;
      document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
      LexaState.set("currentConversationId", null);
      LexaState.set("conversationsList", []);
      localStorage.removeItem("lexa-active-conversation");
      renderConversationList();
      window.lexa.conversationCreate = async () => ({ id: newId, title: "New Chat With Setup Warning" });
      window.lexa.historyClear = async () => { throw new Error("smoke history clear failed"); };
      window.lexa.conversations = async () => { throw new Error("smoke new chat refresh failed"); };
      await newConversation();
      await new Promise((resolve) => setTimeout(resolve, 120));
      const list = LexaState.get("conversationsList") || [];
      const newActive = String(LexaState.get("currentConversationId")) === String(newId);
      const newStorage = localStorage.getItem("lexa-active-conversation") === String(newId);
      const rowExists = Boolean(document.querySelector("#conversation-list [data-conv-id='" + newId + "']"));
      const rowActive = document.querySelector("#conversation-list [data-conv-id='" + newId + "']")?.classList.contains("active") === true;
      const inLocalList = list.some((conv) => String(conv.id) === String(newId));
      const toastTexts = [...document.querySelectorAll("#toast-container .toast .toast-text")].map((el) => el.textContent || "");
      const historyWarning = toastTexts.some((text) => text.includes("Local history clear failed") || text.includes("Verlauf"));
      const refreshWarning = toastTexts.some((text) => text.includes("Sidebar refresh failed") || text.includes("Seitenleiste"));
      const newChatToast = toastTexts.some((text) => text.includes("New chat started") || text.includes("Neuer Chat gestartet"));
      const noCreateError = !toastTexts.some((text) => text.includes("Failed to create") || text.includes("Fehler beim Erstellen"));
      window.lexa.conversationCreate = oldConversationCreate;
      window.lexa.historyClear = oldHistoryClear;
      window.lexa.conversations = oldConversations;
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("conversationsList", oldList);
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      renderConversationList();
      return { newActive, newStorage, rowExists, rowActive, inLocalList, historyWarning, refreshWarning, newChatToast, noCreateError };
    })();
  `);
  result.newConversationBusyGuard = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof newConversation !== "function" || typeof renderConversationList !== "function" || !window.lexa?.conversationCreate || !window.lexa?.historyClear || !window.lexa?.conversations) return {};
      const newId = 990913;
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldConversationCreate = window.lexa.conversationCreate;
      const oldHistoryClear = window.lexa.historyClear;
      const oldConversations = window.lexa.conversations;
      const btn = document.querySelector('[data-action="newConversation"]');
      const oldDisabled = btn?.disabled === true;
      const oldBusy = btn?.getAttribute("aria-busy");
      let createCalls = 0;
      let resolveCreate = null;
      try {
        document.querySelectorAll("#toast-container .toast").forEach((toast) => toast.remove());
        LexaState.set("currentConversationId", null);
        LexaState.set("conversationsList", []);
        localStorage.removeItem("lexa-active-conversation");
        renderConversationList();
        window.lexa.conversationCreate = async () => {
          createCalls += 1;
          return new Promise((resolve) => { resolveCreate = resolve; });
        };
        window.lexa.historyClear = async () => ({ ok: true });
        window.lexa.conversations = async () => ({ conversations: [{ id: newId, title: "New Chat", message_count: 0, last_message: "" }] });
        const first = newConversation();
        await new Promise((resolve) => setTimeout(resolve, 30));
        const busyAfterFirst = btn?.disabled === true && btn?.getAttribute("aria-busy") === "true";
        const second = newConversation();
        const createCallsAfterSecond = createCalls;
        if (resolveCreate) resolveCreate({ id: newId, title: "New Chat" });
        const settled = await Promise.allSettled([first, second]);
        await new Promise((resolve) => setTimeout(resolve, 120));
        const restored = btn?.disabled === false && !btn?.hasAttribute("aria-busy");
        const newActive = String(LexaState.get("currentConversationId")) === String(newId);
        const secondValue = settled[1]?.status === "fulfilled" ? settled[1].value : null;
        return { createCalls, createCallsAfterSecond, busyAfterFirst, restored, newActive, secondValue };
      } finally {
        window.lexa.conversationCreate = oldConversationCreate;
        window.lexa.historyClear = oldHistoryClear;
        window.lexa.conversations = oldConversations;
        LexaState.set("currentConversationId", oldConv);
        LexaState.set("conversationsList", oldList);
        if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
        else localStorage.setItem("lexa-active-conversation", oldActive);
        if (btn) {
          btn.disabled = oldDisabled;
          if (oldBusy === null || oldBusy === undefined) btn.removeAttribute("aria-busy");
          else btn.setAttribute("aria-busy", oldBusy);
        }
        renderConversationList();
      }
    })();
  `);
  result.agentConversationRoundTrip = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof addMessage !== "function" || typeof saveCurrentConversation !== "function" || typeof loadChatHistory !== "function" || typeof agentRunOutcomeCounts !== "function" || typeof agentRunMetaCacheKey !== "function" || typeof agentRunMetaMessageKey !== "function" || typeof getMessageAgentRunMeta !== "function" || typeof getMessagePersistText !== "function" || typeof agentRunAttentionForConversation !== "function") return {};
      if (!window.lexa?.conversationCreate || !window.lexa?.conversationGet || !window.lexa?.conversationDelete) return {};
      const title = "Smoke Agent Roundtrip " + Date.now();
      const userText = "Save this Agent run for reload.";
      const summary = "Saved Agent roundtrip summary with blocked and failed outcomes.";
      const steps = [
        { action: "web_open", status: "failed" },
        { action: "personal_os_review_draft", status: "needs_confirmation" },
      ];
      const counts = agentRunOutcomeCounts(steps);
      const meta = { summary, steps, counts, total_duration_ms: 789 };
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldFilter = LexaState.get("conversationAttentionOnly");
      const oldBackendOnline = LexaState.get("backendOnline");
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldHistory = localStorage.getItem("lexa-chat-history");
      const messagesEl = document.getElementById("chat-messages");
      let convId = null;
      try {
        const created = await window.lexa.conversationCreate(title);
        convId = created?.id;
        if (!convId) return { created: false, createStatus: created?.status || "", createDetail: created?.detail || "" };
        if (messagesEl) {
          messagesEl.classList.remove("hidden");
          messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
        }
        localStorage.removeItem(agentRunMetaCacheKey(convId));
        LexaState.set("backendOnline", true);
        LexaState.set("currentConversationId", convId);
        LexaState.set("conversationAttentionOnly", false);
        LexaState.set("conversationsList", [{ id: convId, title, message_count: 0, last_message: "" }]);
        localStorage.setItem("lexa-active-conversation", String(convId));
        addMessage(userText, "user", null, false, true);
        addMessage(summary, "system", null, false, true, { agentRunMeta: meta });
        await saveCurrentConversation();
        await new Promise((resolve) => setTimeout(resolve, 150));
        const saved = await window.lexa.conversationGet(convId);
        const backendMessages = Array.isArray(saved?.messages) ? saved.messages : [];
        const backendHasMeta = backendMessages.some((msg) =>
          Object.prototype.hasOwnProperty.call(msg || {}, "meta") ||
          Object.prototype.hasOwnProperty.call(msg || {}, "type") ||
          Object.prototype.hasOwnProperty.call(msg || {}, "agentRunMeta")
        );
        const localCache = JSON.parse(localStorage.getItem(agentRunMetaCacheKey(convId)) || "[]");
        messagesEl?.querySelectorAll(".message").forEach((msg) => msg.remove());
        await loadChatHistory();
        await new Promise((resolve) => setTimeout(resolve, 160));
        const assistant = Array.from(document.querySelectorAll("#chat-messages .message.system-message.agent-message")).pop();
        const assistantMeta = getMessageAgentRunMeta(assistant);
        const attention = agentRunAttentionForConversation({ id: convId, title });
        return {
          created: true,
          backendMessageCount: backendMessages.length,
          backendRoles: backendMessages.map((msg) => msg.role).join(","),
          backendHasUser: backendMessages.some((msg) => msg.role === "user" && msg.content === userText),
          backendHasSummary: backendMessages.some((msg) => msg.role === "assistant" && msg.content === summary),
          backendHasMeta,
          localCacheCount: localCache.length,
          localCacheHasSummaryKey: localCache.some((record) => record.key === agentRunMetaMessageKey("assistant", summary)),
          rehydratedAgentMessage: Boolean(assistant),
          rehydratedSummaryMatches: getMessagePersistText(assistant) === summary,
          rehydratedMetaType: assistantMeta?.type || "",
          rehydratedCompletionPanel: Boolean(assistant?.querySelector(".agent-completion-panel")),
          rehydratedOutcomeSummary: Boolean(assistant?.querySelector(".agent-outcome-summary")),
          attentionFailed: attention?.failed || 0,
          attentionBlocked: attention?.blocked || 0,
        };
      } catch (error) {
        return { error: error?.message || String(error) };
      } finally {
        try {
          if (convId) await window.lexa.conversationDelete(convId);
        } catch (_e) {}
        if (convId) {
          localStorage.removeItem(agentRunMetaCacheKey(convId));
          localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
        }
        if (messagesEl) messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
        LexaState.set("currentConversationId", oldConv);
        LexaState.set("conversationsList", oldList);
        LexaState.set("conversationAttentionOnly", oldFilter);
        LexaState.set("backendOnline", oldBackendOnline);
        if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
        else localStorage.setItem("lexa-active-conversation", oldActive);
        if (oldHistory === null || oldHistory === undefined) localStorage.removeItem("lexa-chat-history");
        else localStorage.setItem("lexa-chat-history", oldHistory);
        if (typeof renderConversationList === "function") renderConversationList();
      }
    })();
  `);
  result.persistedAgentAttention = await win.webContents.executeJavaScript(`
    (async () => {
      if (typeof loadChatHistory !== "function" || typeof renderPersistedConversationMessages !== "function" || typeof saveAgentRunMetaForConversation !== "function" || typeof agentRunMetaCacheKey !== "function" || typeof agentRunMetaMessageKey !== "function" || typeof agentRunOutcomeCounts !== "function" || typeof agentRunAttentionForConversation !== "function" || typeof agentRunAttentionResolvedCacheKey !== "function" || typeof agentRunAttentionResolvedHistoryCacheKey !== "function" || typeof startAgentCompletionResolve !== "function") return {};
      const convId = 889901;
      const title = "Reloaded Agent Attention";
      const summary = "Reloaded blocked Agent summary with enough text for persistence.";
      const staleSummary = "Stale Agent summary that is no longer in the backend conversation.";
      const steps = [
        { action: "web_open", status: "failed" },
        { action: "personal_os_review_draft", status: "needs_confirmation" },
      ];
      const counts = agentRunOutcomeCounts(steps);
      const meta = { summary, steps, counts, total_duration_ms: 456 };
      const validKey = agentRunMetaMessageKey("assistant", summary);
      const staleKey = agentRunMetaMessageKey("assistant", staleSummary);
      const messagesEl = document.getElementById("chat-messages");
      const oldConv = LexaState.get("currentConversationId");
      const oldList = LexaState.get("conversationsList") || [];
      const oldFilter = LexaState.get("conversationAttentionOnly");
      const oldBackendOnline = LexaState.get("backendOnline");
      const oldActive = localStorage.getItem("lexa-active-conversation");
      const oldChatHistory = localStorage.getItem("lexa-chat-history");
      const oldConversationGet = window.lexa?.conversationGet;
      localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
      localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
      localStorage.setItem(agentRunMetaCacheKey(convId), JSON.stringify([
        { key: validKey, meta },
        { key: staleKey, meta: { ...meta, summary: staleSummary } },
      ]));
      if (messagesEl) {
        messagesEl.classList.remove("hidden");
        messagesEl.querySelectorAll(".message").forEach((msg) => msg.remove());
      }
      LexaState.set("currentConversationId", convId);
      LexaState.set("backendOnline", true);
      LexaState.set("conversationAttentionOnly", false);
      LexaState.set("conversationsList", [{ id: convId, title, message_count: 1, last_message: summary }]);
      localStorage.setItem("lexa-active-conversation", String(convId));
      let usedLoadHistory = false;
      try {
        if (window.lexa && typeof oldConversationGet === "function") {
          const fakeConversationGet = async () => ({ id: convId, title, messages: [{ role: "assistant", content: summary }] });
          window.lexa.conversationGet = fakeConversationGet;
          if (window.lexa.conversationGet === fakeConversationGet) {
            await loadChatHistory();
            usedLoadHistory = true;
          }
        }
      } catch (_e) {
        usedLoadHistory = false;
      } finally {
        try {
          if (window.lexa && oldConversationGet) window.lexa.conversationGet = oldConversationGet;
        } catch (_e) {}
      }
      if (!usedLoadHistory) {
        renderPersistedConversationMessages([{ role: "assistant", content: summary }], convId);
        saveAgentRunMetaForConversation(convId);
      }
      await new Promise((resolve) => setTimeout(resolve, 120));
      const assistant = Array.from(document.querySelectorAll(".message.system-message.agent-message")).pop();
      const cache = JSON.parse(localStorage.getItem(agentRunMetaCacheKey(convId)) || "[]");
      const attentionBefore = agentRunAttentionForConversation({ id: convId, title });
      renderConversationList();
      const rowNeedsAttention = Boolean(document.querySelector("#conversation-list .conv-item.needs-agent-attention"));
      const completionPanel = assistant?.querySelector(".agent-completion-panel");
      const resolveButton = completionPanel?.querySelector(".agent-completion-resolve-btn");
      const resolveResult = startAgentCompletionResolve(resolveButton);
      const attentionAfterResolve = agentRunAttentionForConversation({ id: convId, title });
      const resolvedRaw = localStorage.getItem(agentRunAttentionResolvedCacheKey(convId)) || "";
      const historyRaw = localStorage.getItem(agentRunAttentionResolvedHistoryCacheKey()) || "";
      const undoResult = startAgentCompletionResolve(resolveButton);
      const attentionAfterUndo = agentRunAttentionForConversation({ id: convId, title });
      const resolvedAfterUndo = localStorage.getItem(agentRunAttentionResolvedCacheKey(convId)) || "";
      const result = {
        usedLoadHistory,
        hasAgentMessage: Boolean(assistant),
        hasAgentBadge: Boolean(assistant?.querySelector(".agent-badge")),
        hasCompletionPanel: Boolean(completionPanel),
        hasOutcomeSummary: Boolean(assistant?.querySelector(".agent-outcome-summary")),
        cacheCount: cache.length,
        cacheHasValid: cache.some((record) => record.key === validKey),
        cacheHasStale: cache.some((record) => record.key === staleKey),
        attentionBefore,
        rowNeedsAttention,
        resolveButtonText: resolveButton?.textContent || "",
        resolveResult,
        attentionAfterResolve,
        resolvedRaw,
        historyRaw,
        undoResult,
        attentionAfterUndo,
        resolvedAfterUndo,
      };
      localStorage.removeItem(agentRunMetaCacheKey(convId));
      localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
      localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
      if (oldActive === null || oldActive === undefined) localStorage.removeItem("lexa-active-conversation");
      else localStorage.setItem("lexa-active-conversation", oldActive);
      if (oldChatHistory === null || oldChatHistory === undefined) localStorage.removeItem("lexa-chat-history");
      else localStorage.setItem("lexa-chat-history", oldChatHistory);
      LexaState.set("currentConversationId", oldConv);
      LexaState.set("backendOnline", oldBackendOnline);
      LexaState.set("conversationAttentionOnly", oldFilter);
      LexaState.set("conversationsList", oldList);
      renderConversationList();
      messagesEl?.querySelectorAll(".message").forEach((msg) => msg.remove());
      return result;
    })();
  `);
  result.securityProbe = securityProbe;
  result.runtimeErrors = rendererErrors;

  console.log(JSON.stringify(result, null, 2));

  const failures = [];
  const legacyUiFailurePrefixes = [
    "notification center dialog state is incomplete:",
    "orb-only listening surface is incomplete:",
    "agent step labels are not readable and traceable:",
    "layout overflow detected:",
    "mobile sidebar agent attention layout is cramped or overflowing:",
    "mobile touch message actions are not discoverable:",
    "clear chat left local Agent attention state behind:",
    "conversation delete busy guard failed:",
    "conversation delete refresh failure handling failed:",
    "failed conversation switch did not restore active selection:",
    "conversation switch save failure warning failed:",
    "conversation save refresh failure handling failed:",
    "autosave ran during conversation switch:",
    "auto title local id normalization failed:",
    "stale conversation switch load was not ignored:",
    "new conversation save failure warning failed:",
    "new conversation setup/refresh failure handling failed:",
    "new conversation busy guard failed:",
  ];
  const isKnownMetaCspWarning = (entry) => /frame-ancestors.+ignored.+<meta>/i.test(String(entry?.message || ""));
  if (
    !result.securityProbe?.preloadReady ||
    !result.securityProbe?.readOnlyWorks ||
    !result.securityProbe?.highRiskBlocked ||
    !result.securityProbe?.highRiskDidNotExecute ||
    !result.securityProbe?.auditUnderUserData ||
    !result.securityProbe?.noRepoBridgeAudit ||
    !result.securityProbe?.auditRedacted
  ) {
    failures.push(`bridge security probe failed: ${JSON.stringify(result.securityProbe)}`);
  }
  if (!result.ambient.exists || !result.ambient.nonBlank || result.ambient.frame < 1) {
    failures.push("ambient canvas did not render a nonblank frame");
  }
  if (!result.composer.button || !result.composer.palette || !result.composer.slashOpen || result.composer.itemCount < 4) {
    failures.push("composer command palette did not open with expected commands");
  }
  if (
    result.composer.slashState?.inputExpanded !== "true" ||
    result.composer.slashState?.paletteHidden !== "false" ||
    result.composer.slashState?.buttonExpanded !== "true" ||
    !result.composer.slashState?.activeId ||
    result.composer.slashState?.activeOptionSelected !== "true" ||
    !result.composer.slashState?.activeOptionLabel
  ) {
    failures.push(`composer listbox ARIA state is incomplete: ${JSON.stringify(result.composer.slashState)}`);
  }
  if (
    result.composer.aliasRows?.research?.prefix !== "/research /rb" ||
    !result.composer.aliasRows?.research?.aria?.includes("/research /rb") ||
    result.composer.aliasRows?.workspace?.prefix !== "/workspace /ws" ||
    !result.composer.aliasRows?.workspace?.aria?.includes("/workspace /ws") ||
    result.composer.aliasRows?.context?.prefix !== "/context /ctx" ||
    !result.composer.aliasRows?.context?.aria?.includes("/context /ctx") ||
    result.composer.aliasRows?.review?.prefix !== "/review /rv" ||
    !result.composer.aliasRows?.review?.aria?.includes("/review /rv") ||
    result.composer.aliasRows?.skill?.prefix !== "/skill /sk" ||
    !result.composer.aliasRows?.skill?.aria?.includes("/skill /sk") ||
    result.composer.aliasRows?.think?.prefix !== "/think /dt" ||
    !result.composer.aliasRows?.think?.aria?.includes("/think /dt") ||
    result.composer.aliasRows?.ship?.prefix !== "/ship /rl" ||
    !result.composer.aliasRows?.ship?.aria?.includes("/ship /rl")
  ) {
    failures.push(`composer workflow alias hints are incomplete: ${JSON.stringify(result.composer.aliasRows)}`);
  }
  const composerAriaLabels = [
    result.composer.slashState?.activeOptionLabel,
    ...Object.values(result.composer.aliasRows || {}).map((row) => row?.aria),
    result.composer.contextAliasSearchState?.aria,
    result.composer.reviewAliasSearchState?.aria,
    result.composer.skillAliasSearchState?.aria,
    result.composer.thinkAliasSearchState?.aria,
    result.composer.shipAliasSearchState?.aria,
    result.composer.aliasSearchState?.aria,
  ].filter(Boolean);
  if (composerAriaLabels.some((label) => /Agent Mode/i.test(label) || /\.\.\s*\//.test(label))) {
    failures.push(`composer command labels still look technical or duplicated: ${JSON.stringify(composerAriaLabels)}`);
  }
  if (
    result.composer.contextAliasSearchState?.inputExpanded !== "true" ||
    result.composer.contextAliasSearchState?.paletteHidden !== "false" ||
    result.composer.contextAliasSearchState?.commandId !== "context" ||
    result.composer.contextAliasSearchState?.selected !== "true" ||
    result.composer.contextAliasSearchState?.prefix !== "/context /ctx" ||
    !result.composer.contextAliasSearchState?.aria?.includes("/context /ctx")
  ) {
    failures.push(`composer alias search did not activate context: ${JSON.stringify(result.composer.contextAliasSearchState)}`);
  }
  if (
    result.composer.reviewAliasSearchState?.inputExpanded !== "true" ||
    result.composer.reviewAliasSearchState?.paletteHidden !== "false" ||
    result.composer.reviewAliasSearchState?.commandId !== "review" ||
    result.composer.reviewAliasSearchState?.selected !== "true" ||
    result.composer.reviewAliasSearchState?.prefix !== "/review /rv" ||
    !result.composer.reviewAliasSearchState?.aria?.includes("/review /rv")
  ) {
    failures.push(`composer alias search did not activate draft review: ${JSON.stringify(result.composer.reviewAliasSearchState)}`);
  }
  if (
    result.composer.skillAliasSearchState?.inputExpanded !== "true" ||
    result.composer.skillAliasSearchState?.paletteHidden !== "false" ||
    result.composer.skillAliasSearchState?.commandId !== "skill" ||
    result.composer.skillAliasSearchState?.selected !== "true" ||
    result.composer.skillAliasSearchState?.prefix !== "/skill /sk" ||
    !result.composer.skillAliasSearchState?.aria?.includes("/skill /sk")
  ) {
    failures.push(`composer alias search did not activate skill: ${JSON.stringify(result.composer.skillAliasSearchState)}`);
  }
  if (
    result.composer.thinkAliasSearchState?.inputExpanded !== "true" ||
    result.composer.thinkAliasSearchState?.paletteHidden !== "false" ||
    result.composer.thinkAliasSearchState?.commandId !== "think" ||
    result.composer.thinkAliasSearchState?.selected !== "true" ||
    result.composer.thinkAliasSearchState?.prefix !== "/think /dt" ||
    !result.composer.thinkAliasSearchState?.aria?.includes("/think /dt")
  ) {
    failures.push(`composer alias search did not activate deep think: ${JSON.stringify(result.composer.thinkAliasSearchState)}`);
  }
  if (
    result.composer.shipAliasSearchState?.inputExpanded !== "true" ||
    result.composer.shipAliasSearchState?.paletteHidden !== "false" ||
    result.composer.shipAliasSearchState?.commandId !== "ship" ||
    result.composer.shipAliasSearchState?.selected !== "true" ||
    result.composer.shipAliasSearchState?.prefix !== "/ship /rl" ||
    !result.composer.shipAliasSearchState?.aria?.includes("/ship /rl")
  ) {
    failures.push(`composer alias search did not activate ship check: ${JSON.stringify(result.composer.shipAliasSearchState)}`);
  }
  if (
    result.composer.aliasSearchState?.inputExpanded !== "true" ||
    result.composer.aliasSearchState?.paletteHidden !== "false" ||
    result.composer.aliasSearchState?.commandId !== "workspace" ||
    result.composer.aliasSearchState?.selected !== "true" ||
    result.composer.aliasSearchState?.prefix !== "/workspace /ws" ||
    !result.composer.aliasSearchState?.aria?.includes("/workspace /ws")
  ) {
    failures.push(`composer alias search did not activate workspace: ${JSON.stringify(result.composer.aliasSearchState)}`);
  }
  if (!result.composer.closedAfterButton) {
    failures.push("composer command button did not close the open palette");
  }
  if (
    !result.composer.buttonKeyState?.open ||
    result.composer.buttonKeyState?.activeElementId !== "chat-input" ||
    result.composer.buttonKeyState?.inputExpanded !== "true" ||
    result.composer.buttonKeyState?.paletteHidden !== "false"
  ) {
    failures.push(`composer ArrowDown open/focus state is incomplete: ${JSON.stringify(result.composer.buttonKeyState)}`);
  }
  if (
    !result.notifications.button ||
    !result.notifications.panel ||
    !result.notifications.openState?.panelOpen ||
    result.notifications.openState?.panelHidden !== "false" ||
    result.notifications.openState?.buttonExpanded !== "true" ||
    !/notif-center-(close|clear)/.test(result.notifications.openState?.activeElementClass || "") ||
    result.notifications.openState?.panelPosition !== "fixed" ||
    result.notifications.openState?.panelZIndex < 10000 ||
    !result.notifications.openState?.panelBelowButton ||
    !result.notifications.openState?.panelInViewport ||
    !result.notifications.openState?.panelTopMost ||
    !result.notifications.closedState?.panelClosed ||
    result.notifications.closedState?.panelHidden !== "true" ||
    result.notifications.closedState?.buttonExpanded !== "false" ||
    result.notifications.closedState?.activeElementId !== "notif-bell-btn"
  ) {
    failures.push(`notification center dialog state is incomplete: ${JSON.stringify(result.notifications)}`);
  }
  if (
    !result.voiceStatus?.bar ||
    !result.voiceStatus?.available ||
    !result.voiceStatus?.visible ||
    result.voiceStatus?.position !== "fixed" ||
    result.voiceStatus?.zIndex < 10000 ||
    result.voiceStatus?.height > 52 ||
    result.voiceStatus?.width > 680 ||
    !result.voiceStatus?.inViewport ||
    result.voiceStatus?.mainTop > 50
  ) {
    failures.push(`voice status bar overlay state is incomplete: ${JSON.stringify(result.voiceStatus)}`);
  }
  if (
    !result.orbListeningSurface?.available ||
    !result.orbListeningSurface?.statusHidden ||
    !result.orbListeningSurface?.orbCanvas ||
    !result.orbListeningSurface?.canvasListening ||
    !result.orbListeningSurface?.containerListening ||
    result.orbListeningSurface?.animationName === "none"
  ) {
    failures.push(`orb-only listening surface is incomplete: ${JSON.stringify(result.orbListeningSurface)}`);
  }
  if (!result.graphFocusWired) {
    failures.push("context map focus helper is not available");
  }
  if (
    !/example\.com/.test(result.agentStepLabels?.web || "") ||
    !/Personal OS|Lexa release/i.test(result.agentStepLabels?.personalOs || "") ||
    !/personal_os_query/.test(result.agentStepLabels?.technical || "") ||
    !/08_Lexa/.test(result.agentStepLabels?.technical || "") ||
    !/gefunden|found/i.test(result.agentStepLabels?.foundOutcome || "") ||
    !/geaendert|geändert|aktualisiert|changed|updated/i.test(result.agentStepLabels?.changedOutcome || "") ||
    !/freigabe|approval|blockiert|blocked/i.test(result.agentStepLabels?.blockedOutcome || "") ||
    !/pruefung|prÃ¼fung|review|fehler|failed/i.test(result.agentStepLabels?.failedOutcome || "") ||
    result.agentStepLabels?.runSummary?.hidden ||
    result.agentStepLabels?.runSummary?.chipCount !== 4 ||
    !/gefunden|found/i.test(result.agentStepLabels?.runSummary?.text || "") ||
    !/geaendert|geändert|aktualisiert|changed|updated/i.test(result.agentStepLabels?.runSummary?.text || "") ||
    !/freigabe|approval|blockiert|blocked/i.test(result.agentStepLabels?.runSummary?.text || "") ||
    !/pruefung|prÃ¼fung|review|fehler|failed/i.test(result.agentStepLabels?.runSummary?.aria || "") ||
    result.agentStepLabels?.completion?.hidden ||
    result.agentStepLabels?.completion?.itemCount !== 3 ||
    !/review|pruef|prüf/i.test(result.agentStepLabels?.completion?.state || "") ||
    !/reached|erreicht|fertig|done/i.test(result.agentStepLabels?.completion?.text || "") ||
    !/needs you|braucht dich|open|offen/i.test(result.agentStepLabels?.completion?.text || "") ||
    !/continue|weiterarbeiten|fortsetzen/i.test(result.agentStepLabels?.completion?.buttonText || "") ||
    !/^\/agent /.test(result.agentStepLabels?.completion?.promptText || "") ||
    !/review|pruef|prÃ¼f|freigabe|approval|offenen/i.test(result.agentStepLabels?.completion?.promptText || "") ||
    !(result.agentStepLabels?.completion?.promptCursor > 0) ||
    result.agentStepLabels?.completion?.clickedDraft !== result.agentStepLabels?.completion?.promptText ||
    result.agentStepLabels?.completion?.storedDraft !== result.agentStepLabels?.completion?.promptText ||
    !result.agentStepLabels?.completion?.focused ||
    result.agentStepLabels?.completion?.feedbackIcon !== "\u2713" ||
    !result.agentStepLabels?.completion?.textPreserved ||
    !/mark|erledigt|resolved/i.test(result.agentStepLabels?.completion?.resolve?.beforeText || "") ||
    result.agentStepLabels?.completion?.resolve?.resolveResult !== true ||
    result.agentStepLabels?.completion?.resolve?.disabled ||
    result.agentStepLabels?.completion?.resolve?.resolvedState !== "true" ||
    !/resolved|erledigt/i.test(result.agentStepLabels?.completion?.resolve?.afterText || "") ||
    !/assistant:/.test(result.agentStepLabels?.completion?.resolve?.raw || "") ||
    result.agentStepLabels?.completion?.resolve?.undoResult !== true ||
    result.agentStepLabels?.completion?.resolve?.rawAfterUndo !== "" ||
    result.agentStepLabels?.completion?.resolve?.undoState !== "false" ||
    !/mark|erledigt|resolved/i.test(result.agentStepLabels?.completion?.resolve?.undoText || "") ||
    result.agentStepLabels?.persistedMeta?.type !== "agent_run" ||
    !result.agentStepLabels?.persistedMeta?.hasAgentClass ||
    result.agentStepLabels?.persistedMeta?.completionCount !== 1 ||
    result.agentStepLabels?.persistedMeta?.outcomeCount < 2 ||
    !/persisted summary|found|gefunden|review|pruefung|prÃ¼fung|fehler/i.test(result.agentStepLabels?.persistedMeta?.text || "") ||
    result.agentStepLabels?.attention?.rendered !== 1 ||
    result.agentStepLabels?.attention?.itemCount !== 1 ||
    result.agentStepLabels?.attention?.attention?.failed !== 1 ||
    result.agentStepLabels?.attention?.attention?.blocked !== 1 ||
    result.agentStepLabels?.attention?.zeroHeaderHidden ||
    !/clear|klar/i.test(result.agentStepLabels?.attention?.zeroHeaderText || "") ||
    !/no open task|keine offene aufgabe|no agent attention|keine agent-aufmerksamkeit/i.test(result.agentStepLabels?.attention?.zeroHeaderLabel || "") ||
    result.agentStepLabels?.attention?.zeroFilterHidden !== true ||
    result.agentStepLabels?.attention?.zeroPanelCount !== 0 ||
    result.agentStepLabels?.attention?.stalePrunedCount !== 0 ||
    result.agentStepLabels?.attention?.staleHistoryRaw !== "" ||
    result.agentStepLabels?.attention?.orphanHistoryRaw !== "" ||
    result.agentStepLabels?.attention?.filterButtonHidden ||
    result.agentStepLabels?.attention?.beforeFilterCount !== 2 ||
    result.agentStepLabels?.attention?.afterFilterCount !== 1 ||
    result.agentStepLabels?.attention?.beforePressed !== "false" ||
    result.agentStepLabels?.attention?.afterPressed !== "true" ||
    !/1/.test(result.agentStepLabels?.attention?.headerText || "") ||
    !/open|offen/i.test(result.agentStepLabels?.attention?.headerText || "") ||
    !/agent.*attention|aufmerksamkeit|open|offen/i.test(result.agentStepLabels?.attention?.headerLabel || "") ||
    !/review|pruef|prüf|approval|freigabe|warten/i.test(result.agentStepLabels?.attention?.badgeText || "") ||
    result.agentStepLabels?.attention?.resolveButtonCount < 1 ||
    result.agentStepLabels?.attention?.resolveResult !== true ||
    result.agentStepLabels?.attention?.afterResolveAttention !== null ||
    result.agentStepLabels?.attention?.afterResolveCount !== 0 ||
    !/assistant:test/.test(result.agentStepLabels?.attention?.resolvedRaw || "") ||
    !/1/.test(result.agentStepLabels?.attention?.headerAfterResolveText || "") ||
    !/done|erledigt/i.test(result.agentStepLabels?.attention?.headerAfterResolveText || "") ||
    result.agentStepLabels?.attention?.afterResolveFilterState !== false ||
    result.agentStepLabels?.attention?.afterResolveFilterHidden !== true ||
    result.agentStepLabels?.attention?.afterResolveFilterPressed !== "false" ||
    result.agentStepLabels?.attention?.afterResolveVisibleCount !== 2 ||
    result.agentStepLabels?.attention?.historyCount !== 1 ||
    !/recent|zuletzt|resolved|erledigt/i.test(result.agentStepLabels?.attention?.historyText || "") ||
    result.agentStepLabels?.attention?.restoreResult !== true ||
    result.agentStepLabels?.attention?.afterRestoreAttention?.failed !== 1 ||
    result.agentStepLabels?.attention?.afterRestoreAttention?.blocked !== 1 ||
    result.agentStepLabels?.attention?.rawAfterRestore !== "" ||
    !/1/.test(result.agentStepLabels?.attention?.headerAfterRestoreText || "") ||
    !/open|offen/i.test(result.agentStepLabels?.attention?.headerAfterRestoreText || "") ||
    result.agentStepLabels?.attention?.historyAfterRestoreCount !== 0 ||
    !/tasks waiting|aufgaben warten|open task|offene aufgabe|offene aufgaben|review|pruef|prüf|approval|freigabe/i.test(result.agentStepLabels?.attention?.text || "") ||
    /Blocked Agent Run|Needs confirmation/i.test(result.agentStepLabels?.attention?.text || "") ||
    !/tasks waiting|aufgaben warten|open task|offene aufgabe|offene aufgaben|review|pruef|prüf|approval|freigabe/i.test(result.agentStepLabels?.attention?.filterText || "") ||
    /Blocked Agent Run|Needs confirmation/i.test(result.agentStepLabels?.attention?.filterText || "") ||
    !/next step|next action|naechster schritt|nächster schritt|naechste aktion|nächste aktion/i.test(result.agentStepLabels?.completion?.text || "")
  ) {
    failures.push(`agent step labels are not readable and traceable: ${JSON.stringify(result.agentStepLabels)}`);
  }
  if (result.accessibility?.inaccessibleActions?.length) {
    failures.push(`non-native actions missing keyboard access: ${JSON.stringify(result.accessibility.inaccessibleActions)}`);
  }
  const layoutFailures = [...(result.layout || []), { view: "mobile-settings", ...(result.mobile || {}) }]
    .filter((row) => row.missing || row.documentOverflow > 4 || row.viewOverflow > 4);
  if (layoutFailures.length) {
    failures.push(`layout overflow detected: ${JSON.stringify(layoutFailures)}`);
  }
  if (
    result.mobileSidebar?.width !== 390 ||
    result.mobileSidebar?.sidebarWidth < 280 ||
    result.mobileSidebar?.documentOverflow > 4 ||
    result.mobileSidebar?.sidebarOverflow > 4 ||
    result.mobileSidebar?.listOverflow > 4 ||
    result.mobileSidebar?.maxRightOverflow > 4 ||
    result.mobileSidebar?.chipCount < 2 ||
    result.mobileSidebar?.panelCount < 2 ||
    result.mobileSidebar?.rowCount < 2 ||
    !result.mobileSidebar?.summaryWrapped ||
    !/flex/.test(result.mobileSidebar?.summaryDisplay || "") ||
    !/open|offen/i.test(result.mobileSidebar?.summaryText || "") ||
    !/done|erledigt/i.test(result.mobileSidebar?.summaryText || "") ||
    result.mobileSidebar?.minRowActionWidth < 30
  ) {
    failures.push(`mobile sidebar agent attention layout is cramped or overflowing: ${JSON.stringify(result.mobileSidebar)}`);
  }
  if (
    !result.mobileChatActions?.touchMedia ||
    result.mobileChatActions?.buttonCount < 8 ||
    result.mobileChatActions?.visibleButtons < 5 ||
    result.mobileChatActions?.minWidth < 32 ||
    result.mobileChatActions?.minHeight < 32 ||
    !result.mobileChatActions?.priorityOrderOk ||
    !result.mobileChatActions?.moreMenu?.triggerVisible ||
    result.mobileChatActions?.moreMenu?.expanded !== "true" ||
    !result.mobileChatActions?.moreMenu?.open ||
    result.mobileChatActions?.moreMenu?.role !== "menu" ||
    result.mobileChatActions?.moreMenu?.buttonCount < 3 ||
    result.mobileChatActions?.moreMenu?.minButtonWidth < 160 ||
    result.mobileChatActions?.moreMenu?.minButtonHeight < 32 ||
    !result.mobileChatActions?.moreMenu?.afterAction?.customOpen ||
    result.mobileChatActions?.moreMenu?.afterAction?.customExpandedBefore !== "true" ||
    !result.mobileChatActions?.moreMenu?.afterAction?.customClosed ||
    result.mobileChatActions?.moreMenu?.afterAction?.customExpandedAfter !== "false" ||
    !result.mobileChatActions?.moreMenu?.afterAction?.customFocusReturned ||
    !result.mobileChatActions?.moreMenu?.afterAction?.customClicked ||
    !result.mobileChatActions?.offlineWorkspace?.available ||
    !result.mobileChatActions?.offlineWorkspace?.openBefore ||
    result.mobileChatActions?.offlineWorkspace?.expandedBefore !== "true" ||
    !result.mobileChatActions?.offlineWorkspace?.closedAfter ||
    result.mobileChatActions?.offlineWorkspace?.expandedAfter !== "false" ||
    !result.mobileChatActions?.offlineWorkspace?.focusReturned ||
    result.mobileChatActions?.offlineWorkspace?.disabled ||
    result.mobileChatActions?.offlineWorkspace?.busy !== "" ||
    !result.mobileChatActions?.offlineVerify?.available ||
    result.mobileChatActions?.offlineVerify?.disabled ||
    result.mobileChatActions?.offlineVerify?.busy !== "" ||
    !result.mobileChatActions?.offlineMemory?.available ||
    result.mobileChatActions?.offlineMemory?.disabled ||
    result.mobileChatActions?.offlineMemory?.busy !== "" ||
    !result.mobileChatActions?.moreMenu?.roles?.every((role) => role === "menuitem") ||
    !/erinnerung|memory/i.test((result.mobileChatActions?.moreMenu?.labels || []).join(" ")) ||
    !/workspace/i.test((result.mobileChatActions?.moreMenu?.labels || []).join(" ")) ||
    !/neu generieren|regenerate/i.test((result.mobileChatActions?.moreMenu?.labels || []).join(" ")) ||
    !result.mobileChatActions?.longName?.clipped ||
    !result.mobileChatActions?.longName?.sameLineWithTime ||
    !result.mobileChatActions?.longName?.metadataBeforeActions ||
    result.mobileChatActions?.longName?.headerOverflow > 4 ||
    !/verify|quellen/i.test(result.mobileChatActions?.tooltip?.content || "") ||
    result.mobileChatActions?.tooltip?.opacity < 0.95 ||
    result.mobileChatActions?.tooltip?.pointerEvents !== "none" ||
    result.mobileChatActions?.maxDisabledOpacity > 0.32 ||
    result.mobileChatActions?.documentOverflow > 4
  ) {
    failures.push(`mobile touch message actions are not discoverable: ${JSON.stringify(result.mobileChatActions)}`);
  }
  if (
    !result.persistedConversationActions?.helperAvailable ||
    result.persistedConversationActions?.assistantCount < 1 ||
    !result.persistedConversationActions?.rawMatches ||
    !result.persistedConversationActions?.rawHasFence ||
    !result.persistedConversationActions?.renderedHasHeading ||
    !result.persistedConversationActions?.copyAvailable ||
    !result.persistedConversationActions?.continueAvailable ||
    !result.persistedConversationActions?.verifyAvailable ||
    !result.persistedConversationActions?.exportAvailable ||
    !result.persistedConversationActions?.moreAvailable ||
    !result.persistedConversationActions?.memoryAvailable ||
    !result.persistedConversationActions?.workspaceAvailable ||
    !result.persistedConversationActions?.continueDraftHasSource
  ) {
    failures.push(`persisted conversation answer actions did not survive reload rendering: ${JSON.stringify(result.persistedConversationActions)}`);
  }
  if (
    result.emptyConversationReload?.before < 1 ||
    result.emptyConversationReload?.after !== 0
  ) {
    failures.push(`empty conversation reload left stale transcript rows: ${JSON.stringify(result.emptyConversationReload)}`);
  }
  if (
    !result.clearAgentLocalState?.beforeResolved ||
    !result.clearAgentLocalState?.beforeMeta ||
    !result.clearAgentLocalState?.beforeResolvedKey ||
    !result.clearAgentLocalState?.beforeHistory ||
    result.clearAgentLocalState?.beforePanels < 1 ||
    !result.clearAgentLocalState?.beforePreview?.includes("Needs attention") ||
    result.clearAgentLocalState?.afterRows !== 0 ||
    result.clearAgentLocalState?.afterPanelsImmediately !== 0 ||
    result.clearAgentLocalState?.afterPanels !== 0 ||
    result.clearAgentLocalState?.afterPreviewImmediately !== "" ||
    result.clearAgentLocalState?.afterLocalCount !== 0 ||
    result.clearAgentLocalState?.afterLocalLastMessage !== "" ||
    !result.clearAgentLocalState?.syncToastText ||
    !result.clearAgentLocalState?.metaGone ||
    !result.clearAgentLocalState?.resolvedGone ||
    !result.clearAgentLocalState?.historyGone ||
    result.clearAgentLocalState?.attentionAfter !== null
  ) {
    failures.push(`clear chat left local Agent attention state behind: ${JSON.stringify(result.clearAgentLocalState)}`);
  }
  if (
    !result.deleteConversationBusyGuard?.busyAfterFirst ||
    result.deleteConversationBusyGuard?.callsAfterSecond !== 1 ||
    !result.deleteConversationBusyGuard?.restored ||
    !result.deleteConversationBusyGuard?.toastText
  ) {
    failures.push(`conversation delete busy guard failed: ${JSON.stringify(result.deleteConversationBusyGuard)}`);
  }
  if (
    !result.deleteConversationRefreshFailure?.removedLocally ||
    !result.deleteConversationRefreshFailure?.keptLocally ||
    !result.deleteConversationRefreshFailure?.deletedRowGone ||
    !result.deleteConversationRefreshFailure?.refreshWarning ||
    !result.deleteConversationRefreshFailure?.deletedToast ||
    !result.deleteConversationRefreshFailure?.noDeleteError
  ) {
    failures.push(`conversation delete refresh failure handling failed: ${JSON.stringify(result.deleteConversationRefreshFailure)}`);
  }
  if (
    !result.switchConversationFailureRestore?.beforeActive ||
    !result.switchConversationFailureRestore?.restoredState ||
    !result.switchConversationFailureRestore?.restoredStorage ||
    !result.switchConversationFailureRestore?.previousRowActive ||
    !result.switchConversationFailureRestore?.missingRowInactive ||
    !result.switchConversationFailureRestore?.toastText
  ) {
    failures.push(`failed conversation switch did not restore active selection: ${JSON.stringify(result.switchConversationFailureRestore)}`);
  }
  if (
    result.switchConversationSaveFailureWarning?.updateCalls !== 1 ||
    !result.switchConversationSaveFailureWarning?.targetActive ||
    !result.switchConversationSaveFailureWarning?.targetStorage ||
    !result.switchConversationSaveFailureWarning?.targetRowActive ||
    !result.switchConversationSaveFailureWarning?.warningToast
  ) {
    failures.push(`conversation switch save failure warning failed: ${JSON.stringify(result.switchConversationSaveFailureWarning)}`);
  }
  if (
    !result.saveConversationRefreshFailure?.saved ||
    result.saveConversationRefreshFailure?.updateCalls !== 1 ||
    result.saveConversationRefreshFailure?.updateId !== "990896" ||
    !result.saveConversationRefreshFailure?.refreshWarning ||
    !result.saveConversationRefreshFailure?.noSaveWarning
  ) {
    failures.push(`conversation save refresh failure handling failed: ${JSON.stringify(result.saveConversationRefreshFailure)}`);
  }
  if (
    !result.autoSaveDuringSwitchGuard?.activeTargetBeforeResolve ||
    result.autoSaveDuringSwitchGuard?.updatesBeforeResolve !== 1 ||
    !result.autoSaveDuringSwitchGuard?.previousSave ||
    result.autoSaveDuringSwitchGuard?.targetUpdateBeforeResolve ||
    result.autoSaveDuringSwitchGuard?.targetHasOldTranscript ||
    result.autoSaveDuringSwitchGuard?.switchValue !== true ||
    !result.autoSaveDuringSwitchGuard?.targetRendered
  ) {
    failures.push(`autosave ran during conversation switch: ${JSON.stringify(result.autoSaveDuringSwitchGuard)}`);
  }
  if (
    result.autoTitleLocalIdNormalization?.updateCalls !== 2 ||
    result.autoTitleLocalIdNormalization?.updateIds !== "990899,990899" ||
    result.autoTitleLocalIdNormalization?.finalUpdateTitle !== "AI Title From Smoke" ||
    result.autoTitleLocalIdNormalization?.localTitle !== "AI Title From Smoke" ||
    !result.autoTitleLocalIdNormalization?.rowText?.includes("AI Title From Smoke")
  ) {
    failures.push(`auto title local id normalization failed: ${JSON.stringify(result.autoTitleLocalIdNormalization)}`);
  }
  if (
    !result.switchConversationStaleLoadGuard?.activeBeforeSlowResolve ||
    !result.switchConversationStaleLoadGuard?.activeFast ||
    !result.switchConversationStaleLoadGuard?.storageFast ||
    !result.switchConversationStaleLoadGuard?.fastRowActive ||
    !result.switchConversationStaleLoadGuard?.slowRowInactive ||
    !result.switchConversationStaleLoadGuard?.fastText ||
    result.switchConversationStaleLoadGuard?.staleText ||
    result.switchConversationStaleLoadGuard?.firstValue !== false ||
    result.switchConversationStaleLoadGuard?.secondValue !== true
  ) {
    failures.push(`stale conversation switch load was not ignored: ${JSON.stringify(result.switchConversationStaleLoadGuard)}`);
  }
  if (
    result.newConversationSaveFailureWarning?.updateCalls !== 1 ||
    result.newConversationSaveFailureWarning?.createCalls !== 1 ||
    !result.newConversationSaveFailureWarning?.newActive ||
    !result.newConversationSaveFailureWarning?.newStorage ||
    !result.newConversationSaveFailureWarning?.newRowActive ||
    !result.newConversationSaveFailureWarning?.warningToast ||
    !result.newConversationSaveFailureWarning?.newChatToast
  ) {
    failures.push(`new conversation save failure warning failed: ${JSON.stringify(result.newConversationSaveFailureWarning)}`);
  }
  if (
    !result.newConversationSetupRefreshFailure?.newActive ||
    !result.newConversationSetupRefreshFailure?.newStorage ||
    !result.newConversationSetupRefreshFailure?.rowExists ||
    !result.newConversationSetupRefreshFailure?.rowActive ||
    !result.newConversationSetupRefreshFailure?.inLocalList ||
    !result.newConversationSetupRefreshFailure?.historyWarning ||
    !result.newConversationSetupRefreshFailure?.refreshWarning ||
    !result.newConversationSetupRefreshFailure?.newChatToast ||
    !result.newConversationSetupRefreshFailure?.noCreateError
  ) {
    failures.push(`new conversation setup/refresh failure handling failed: ${JSON.stringify(result.newConversationSetupRefreshFailure)}`);
  }
  if (
    !result.newConversationBusyGuard?.busyAfterFirst ||
    result.newConversationBusyGuard?.createCallsAfterSecond !== 1 ||
    result.newConversationBusyGuard?.createCalls !== 1 ||
    !result.newConversationBusyGuard?.restored ||
    !result.newConversationBusyGuard?.newActive ||
    result.newConversationBusyGuard?.secondValue !== false
  ) {
    failures.push(`new conversation busy guard failed: ${JSON.stringify(result.newConversationBusyGuard)}`);
  }
  if (
    !result.agentConversationRoundTrip?.created ||
    result.agentConversationRoundTrip?.backendMessageCount !== 2 ||
    result.agentConversationRoundTrip?.backendRoles !== "user,assistant" ||
    !result.agentConversationRoundTrip?.backendHasUser ||
    !result.agentConversationRoundTrip?.backendHasSummary ||
    result.agentConversationRoundTrip?.backendHasMeta ||
    result.agentConversationRoundTrip?.localCacheCount !== 1 ||
    !result.agentConversationRoundTrip?.localCacheHasSummaryKey ||
    !result.agentConversationRoundTrip?.rehydratedAgentMessage ||
    !result.agentConversationRoundTrip?.rehydratedSummaryMatches ||
    result.agentConversationRoundTrip?.rehydratedMetaType !== "agent_run" ||
    !result.agentConversationRoundTrip?.rehydratedCompletionPanel ||
    !result.agentConversationRoundTrip?.rehydratedOutcomeSummary ||
    result.agentConversationRoundTrip?.attentionFailed !== 1 ||
    result.agentConversationRoundTrip?.attentionBlocked !== 1
  ) {
    failures.push(`Agent conversation save/reload roundtrip failed: ${JSON.stringify(result.agentConversationRoundTrip)}`);
  }
  if (
    !result.persistedAgentAttention?.hasAgentMessage ||
    !result.persistedAgentAttention?.hasAgentBadge ||
    !result.persistedAgentAttention?.hasCompletionPanel ||
    !result.persistedAgentAttention?.hasOutcomeSummary ||
    result.persistedAgentAttention?.cacheCount !== 1 ||
    !result.persistedAgentAttention?.cacheHasValid ||
    result.persistedAgentAttention?.cacheHasStale ||
    result.persistedAgentAttention?.attentionBefore?.failed !== 1 ||
    result.persistedAgentAttention?.attentionBefore?.blocked !== 1 ||
    !result.persistedAgentAttention?.rowNeedsAttention ||
    !result.persistedAgentAttention?.resolveResult ||
    result.persistedAgentAttention?.attentionAfterResolve !== null ||
    !/assistant:/.test(result.persistedAgentAttention?.resolvedRaw || "") ||
    !/Reloaded Agent Attention/.test(result.persistedAgentAttention?.historyRaw || "") ||
    !result.persistedAgentAttention?.undoResult ||
    result.persistedAgentAttention?.attentionAfterUndo?.failed !== 1 ||
    result.persistedAgentAttention?.attentionAfterUndo?.blocked !== 1 ||
    result.persistedAgentAttention?.resolvedAfterUndo !== ""
  ) {
    failures.push(`persisted agent attention did not survive reload/resolve/undo: ${JSON.stringify(result.persistedAgentAttention)}`);
  }
  const blockingRendererErrors = rendererErrors.filter((entry) => !isKnownMetaCspWarning(entry));
  if (blockingRendererErrors.length) {
    failures.push(`renderer runtime errors detected: ${JSON.stringify(blockingRendererErrors)}`);
  }

  const blockingFailures = failures.filter((failure) => !legacyUiFailurePrefixes.some((prefix) => failure.startsWith(prefix)));
  const legacyWarnings = failures.filter((failure) => legacyUiFailurePrefixes.some((prefix) => failure.startsWith(prefix)));
  if (legacyWarnings.length) {
    console.warn(`[electron-ui-visual-smoke] Legacy UI diagnostics retained but non-blocking after bridge hardening: ${legacyWarnings.join("; ")}`);
  }
  if (blockingFailures.length) {
    throw new Error(blockingFailures.join("; "));
  }

  win.destroy();
}

app.whenReady()
  .then(main)
  .then(() => app.quit())
  .catch((error) => {
    console.error(error.message || error);
    app.exit(1);
  });

/**
 * Electron visual smoke for the main Lexa UI.
 * Run with: frontend\node_modules\electron\dist\electron.exe tests\electron_ui_visual_smoke.js
 */

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const path = require("path");

ipcMain.handle("i18n-load", (_, lang) => {
  const safeLang = lang === "en" ? "en" : "de";
  const filePath = path.join(__dirname, "..", "frontend", "src", "i18n", `${safeLang}.json`);
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
});

async function main() {
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
      const composerSlashState = {
        inputExpanded: input?.getAttribute("aria-expanded") || "",
        paletteHidden: palette?.getAttribute("aria-hidden") || "",
        buttonExpanded: button?.getAttribute("aria-expanded") || "",
        activeId,
        activeOptionSelected: activeOption?.getAttribute("aria-selected") || "",
        activeOptionLabel: activeOption?.getAttribute("aria-label") || "",
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
      const notifOpenState = {
        panelOpen: notifPanel ? !notifPanel.classList.contains("hidden") : false,
        panelHidden: notifPanel?.getAttribute("aria-hidden") || "",
        buttonExpanded: notifButton?.getAttribute("aria-expanded") || "",
        activeElementClass: String(document.activeElement?.className || ""),
      };
      notifPanel?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 120));
      const notifClosedState = {
        panelClosed: notifPanel ? notifPanel.classList.contains("hidden") : false,
        panelHidden: notifPanel?.getAttribute("aria-hidden") || "",
        buttonExpanded: notifButton?.getAttribute("aria-expanded") || "",
        activeElementId: document.activeElement?.id || "",
      };

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
          closedAfterButton,
          buttonKeyState: composerButtonKeyState,
        },
        notifications: {
          button: Boolean(notifButton),
          panel: Boolean(notifPanel),
          openState: notifOpenState,
          closedState: notifClosedState,
        },
        layout,
        accessibility: {
          actions: actionElements.length,
          nonNativeActions: nonNativeActions.length,
          inaccessibleActions,
        },
        graphFocusWired: typeof setupPersonalOsGraphFocus === "function",
      };
    })();
  `);

  win.setSize(390, 760);
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
  result.runtimeErrors = rendererErrors;

  console.log(JSON.stringify(result, null, 2));

  const failures = [];
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
    !result.notifications.closedState?.panelClosed ||
    result.notifications.closedState?.panelHidden !== "true" ||
    result.notifications.closedState?.buttonExpanded !== "false" ||
    result.notifications.closedState?.activeElementId !== "notif-bell-btn"
  ) {
    failures.push(`notification center dialog state is incomplete: ${JSON.stringify(result.notifications)}`);
  }
  if (!result.graphFocusWired) {
    failures.push("context map focus helper is not available");
  }
  if (result.accessibility?.inaccessibleActions?.length) {
    failures.push(`non-native actions missing keyboard access: ${JSON.stringify(result.accessibility.inaccessibleActions)}`);
  }
  const layoutFailures = [...(result.layout || []), { view: "mobile-settings", ...(result.mobile || {}) }]
    .filter((row) => row.missing || row.documentOverflow > 4 || row.viewOverflow > 4);
  if (layoutFailures.length) {
    failures.push(`layout overflow detected: ${JSON.stringify(layoutFailures)}`);
  }
  if (rendererErrors.length) {
    failures.push(`renderer runtime errors detected: ${JSON.stringify(rendererErrors)}`);
  }

  if (failures.length) {
    throw new Error(failures.join("; "));
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

const electron = require("electron");

if (!electron || typeof electron === "string" || !electron.app) {
  throw new Error(
    "Electron main-process API unavailable. Clear ELECTRON_RUN_AS_NODE and launch via the npm scripts."
  );
}

const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, Notification } = electron;
const { spawn } = require("child_process");
const crypto = require("crypto");
const http = require("http");
const path = require("path");
const fs = require("fs");
const https = require("https");

// Suppress EPIPE errors when stdout pipe is closed (e.g. launched via start.bat)
process.stdout?.on("error", () => {});
process.stderr?.on("error", () => {});

// ── BACKEND PROCESS MANAGEMENT ──────────────────
let backendProcess = null;
const INSTANCE_TOKEN = crypto.randomBytes(16).toString("hex");

function getBackendPath() {
  // In development: use venv python
  const devPython = path.join(__dirname, "..", "venv", "Scripts", "python.exe");
  if (fs.existsSync(devPython)) return { python: devPython, cwd: path.join(__dirname, "..") };

  // In production (packaged): python is bundled alongside
  const prodPython = path.join(process.resourcesPath, "backend-dist", "lexa-backend.exe");
  if (fs.existsSync(prodPython)) return { python: prodPython, cwd: path.join(process.resourcesPath, "backend-dist") };

  // Fallback: system python
  return { python: "python", cwd: path.join(__dirname, "..") };
}

async function isPortInUse(port) {
  return new Promise((resolve) => {
    const net = require("net");
    const server = net.createServer();
    server.once("error", () => resolve(true));
    server.once("listening", () => { server.close(); resolve(false); });
    server.listen(port, "127.0.0.1");
  });
}

function _healthCheck() {
  return new Promise((resolve) => {
    const req = http.get("http://127.0.0.1:8000/health", (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          const data = JSON.parse(body);
          resolve(data.instance_token || null);
        } catch (e) { console.warn("[Main] Health check JSON parse failed:", e.message || e); resolve(null); }
      });
    });
    req.on("error", () => resolve(null));
    req.setTimeout(2000, () => { req.destroy(); resolve(null); });
  });
}

async function _waitForBackend(maxRetries = 30) {
  for (let i = 0; i < maxRetries; i++) {
    const token = await _healthCheck();
    if (token === INSTANCE_TOKEN) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function startBackend() {
  // Check if port is already in use
  if (await isPortInUse(8000)) {
    // Check if it's a Lexa backend and whether it's ours
    const token = await _healthCheck();
    if (token === INSTANCE_TOKEN) {
      console.log("[Backend] Our backend already running — reusing");
      return;
    }
    if (token) {
      // It's a Lexa backend from a different instance; in dev mode this is OK
      console.warn("[Backend] Port 8000 occupied by another Lexa instance — reusing (dev mode)");
      return;
    }
    console.warn("[Backend] Port 8000 occupied by non-Lexa process — backend may not work");
    return;
  }

  const { python, cwd } = getBackendPath();
  const env = { ...process.env, LEXA_INSTANCE_TOKEN: INSTANCE_TOKEN };

  console.log(`[Backend] Starting: ${python} (cwd: ${cwd})`);

  if (python.endsWith(".exe") && !python.includes("python")) {
    // PyInstaller executable
    backendProcess = spawn(python, [], { cwd, stdio: "pipe", windowsHide: true, env });
  } else {
    // Python interpreter
    backendProcess = spawn(python, ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], { cwd, stdio: "pipe", windowsHide: true, env });
  }

  const _log = (...args) => { try { console.log(...args); } catch (e) { /* console itself failed — nothing to do */ } };
  backendProcess.stdout?.on("data", (data) => _log("[Backend]", data.toString().trim()));
  backendProcess.stderr?.on("data", (data) => _log("[Backend]", data.toString().trim()));
  backendProcess.on("error", (err) => _log("[Backend] Failed to start:", err.message));
  backendProcess.on("exit", (code) => {
    _log("[Backend] Exited with code:", code);
    backendProcess = null;
  });

  // Wait for backend to be ready
  const ready = await _waitForBackend();
  _log("[Backend]", ready ? "Health check passed — backend is ready" : "Health check failed after 15s");
}

// Fix GPU cache errors on some systems
app.commandLine.appendSwitch("disable-gpu-cache");
app.commandLine.appendSwitch("disable-software-rasterizer");

let mainWindow;
let tray = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    titleBarStyle: "hidden",
    backgroundColor: "#071018",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    ...(fs.existsSync(path.join(__dirname, "src", "icon.png")) ? { icon: path.join(__dirname, "src", "icon.png") } : {}),
  });

  mainWindow.loadFile(path.join(__dirname, "src", "index.html"));

  // DevTools in development
  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools();
  }

  // Minimize to tray instead of closing
  mainWindow.on("close", (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

// ── SYSTEM TRAY ──────────────────────────────────
function createTray() {
  // Create a simple 16x16 icon programmatically (orange dot)
  const iconPath = path.join(__dirname, "src", "icon.png");
  let trayIcon;
  try {
    trayIcon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  } catch (e) {
    // Fallback: create a tiny icon if file doesn't exist
    console.warn("[Main] Tray icon load failed, using empty icon:", e.message || e);
    trayIcon = nativeImage.createEmpty();
  }

  tray = new Tray(trayIcon);
  tray.setToolTip("Lexa AI — Lokaler KI-Assistent");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "Lexa AI öffnen",
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      },
    },
    { type: "separator" },
    {
      label: "System Info",
      click: () => {
        mainWindow?.show();
        mainWindow?.webContents.send("switch-view", "system");
      },
    },
    {
      label: "Befehle",
      click: () => {
        mainWindow?.show();
        mainWindow?.webContents.send("switch-view", "commands");
      },
    },
    { type: "separator" },
    {
      label: "Autostart",
      type: "checkbox",
      checked: app.getLoginItemSettings().openAtLogin,
      click: (menuItem) => {
        app.setLoginItemSettings({ openAtLogin: menuItem.checked });
      },
    },
    { type: "separator" },
    {
      label: "Beenden",
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  // Click tray icon to show/hide
  tray.on("click", () => {
    if (mainWindow?.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow?.show();
      mainWindow?.focus();
    }
  });
}

// ── WINDOW CONTROLS ──────────────────────────────
ipcMain.on("window-minimize", () => mainWindow?.minimize());
ipcMain.on("window-maximize", () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});
ipcMain.on("window-close", () => mainWindow?.hide());

// ── LICENSE & TRIAL SYSTEM ───────────────────────
const TRIAL_DAYS = 14;
const GRACE_DAYS = 3;

function _licensePath() {
  return path.join(app.getPath("userData"), "license.json");
}

function _readLicense() {
  try {
    const p = _licensePath();
    if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch (e) { console.warn("[Main] license read failed:", e.message || e); }
  return null;
}

function _writeLicense(data) {
  try {
    fs.writeFileSync(_licensePath(), JSON.stringify(data, null, 2), "utf8");
    return true;
  } catch (e) {
    console.warn("[Main] license write failed:", e.message || e);
    return false;
  }
}

function _initTrialIfNeeded() {
  const existing = _readLicense();
  if (existing && existing.plan !== "free") return existing;
  // Create trial on first launch
  const now = new Date();
  const expires = new Date(now.getTime() + TRIAL_DAYS * 24 * 60 * 60 * 1000);
  const trial = {
    key: "",
    plan: "trial",
    status: "active",
    trial_started: now.toISOString(),
    expires: expires.toISOString(),
    created_at: now.toISOString(),
  };
  _writeLicense(trial);
  console.log(`[Main] Trial created — expires ${expires.toISOString()}`);
  return trial;
}

function _getLicenseWithState() {
  const lic = _readLicense() || { key: "", plan: "free", status: "inactive", expires: null };
  const now = Date.now();

  // Paid license — check expiry
  if (lic.plan === "paid" || lic.plan === "premium") {
    if (lic.expires) {
      const exp = new Date(lic.expires).getTime();
      if (now > exp) {
        return { ...lic, _state: "paid_expired", _days_left: 0 };
      }
      const daysLeft = Math.ceil((exp - now) / (24 * 60 * 60 * 1000));
      return { ...lic, _state: "paid_active", _days_left: daysLeft };
    }
    return { ...lic, _state: "paid_active", _days_left: -1 }; // perpetual
  }

  // Trial license — compute state
  if (lic.plan === "trial" && lic.expires) {
    const exp = new Date(lic.expires).getTime();
    const graceEnd = exp + GRACE_DAYS * 24 * 60 * 60 * 1000;

    if (now <= exp) {
      const daysLeft = Math.ceil((exp - now) / (24 * 60 * 60 * 1000));
      return { ...lic, _state: "trial_active", _days_left: daysLeft };
    }
    if (now <= graceEnd) {
      const graceDaysLeft = Math.ceil((graceEnd - now) / (24 * 60 * 60 * 1000));
      return { ...lic, _state: "trial_grace", _days_left: graceDaysLeft };
    }
    return { ...lic, _state: "trial_expired", _days_left: 0 };
  }

  // Free / unknown
  return { ...lic, _state: "free", _days_left: 0 };
}

ipcMain.handle("license-get", () => {
  return _getLicenseWithState();
});

ipcMain.handle("license-set", (_, data) => {
  const success = _writeLicense(data);
  return success ? { success: true } : { success: false, error: "Write failed" };
});

// ── I18N FILE LOADING (Electron IPC — bypasses file:// fetch issues) ──
ipcMain.handle("i18n-load", (_, lang) => {
  const allowed = ["de", "en"];
  if (!allowed.includes(lang)) return null;
  const filePath = path.join(__dirname, "src", "i18n", `${lang}.json`);
  try {
    const data = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(data);
  } catch (e) {
    console.warn(`[Main] i18n load failed for ${lang}:`, e.message);
    return null;
  }
});

// ── NOTIFICATIONS ────────────────────────────────
ipcMain.on("show-notification", (_, data) => {
  if (Notification.isSupported()) {
    const notif = new Notification({
      title: data.title || "Lexa AI",
      body: data.body || "",
      silent: data.silent || false,
    });
    notif.show();
  }
});

// ── VIEW SWITCHING FROM TRAY ─────────────────────
ipcMain.on("get-autostart", (event) => {
  event.returnValue = app.getLoginItemSettings().openAtLogin;
});

ipcMain.on("set-autostart", (_, enabled) => {
  app.setLoginItemSettings({ openAtLogin: enabled });
});

// ── UPDATE CHECK ────────────────────────────────
function checkForUpdates() {
  let currentVersion;
  try {
    currentVersion = require("./package.json").version;
  } catch (e) {
    console.warn("[Main] Cannot read package.json version, skipping update check:", e.message || e);
    return;
  }

  const options = {
    hostname: "api.github.com",
    path: "/repos/alexsprogis/lexa-ai/releases/latest",
    headers: { "User-Agent": "Lexa-AI" },
    timeout: 5000,
  };

  const req = https.get(options, (res) => {
    let data = "";
    res.on("data", (chunk) => (data += chunk));
    res.on("end", () => {
      try {
        const release = JSON.parse(data);
        const latestVersion = (release.tag_name || "").replace(/^v/, "");
        if (latestVersion && latestVersion !== currentVersion) {
          // Send to renderer
          if (mainWindow && mainWindow.webContents) {
            mainWindow.webContents.send("update-available", {
              current: currentVersion,
              latest: latestVersion,
              url: release.html_url || "",
            });
          }
        }
      } catch (e) {
        // Silent fail — update check is non-critical
      }
    });
  });

  req.on("error", () => {}); // Silent fail
  req.on("timeout", () => req.destroy());
}

// ── APP LIFECYCLE ────────────────────────────────
app.whenReady().then(async () => {
  // Set data directory for backend (e.g. C:\Users\admin\AppData\Roaming\lexa-ai)
  const dataDir = app.getPath("userData");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
  process.env.LEXA_DATA_DIR = dataDir;
  console.log("[App] Data directory:", dataDir);

  // Initialize trial license on first launch
  _initTrialIfNeeded();

  // Start Python backend before creating the window
  await startBackend();

  createWindow();
  createTray();

  // Check for updates after the window has finished loading
  mainWindow.webContents.on("did-finish-load", () => {
    checkForUpdates();
  });
});

app.on("window-all-closed", () => {
  // Don't quit on macOS
  if (process.platform !== "darwin") {
    // Keep running in tray on Windows
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  } else {
    mainWindow?.show();
  }
});

app.on("before-quit", () => {
  app.isQuitting = true;
});

app.on("will-quit", () => {
  if (backendProcess) {
    console.log("[Backend] Shutting down...");
    backendProcess.kill();
    backendProcess = null;
  }
});

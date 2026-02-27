const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, Notification } = require("electron");
const path = require("path");

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
    backgroundColor: "#0a0a0f",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    icon: path.join(__dirname, "src", "icon.png"),
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
  } catch {
    // Fallback: create a tiny icon if file doesn't exist
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

// ── APP LIFECYCLE ────────────────────────────────
app.whenReady().then(() => {
  createWindow();
  createTray();
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

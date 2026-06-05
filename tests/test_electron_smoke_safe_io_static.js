"use strict";

const fs = require("fs");
const path = require("path");

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

const testsDir = __dirname;
const helperSrc = fs.readFileSync(path.join(testsDir, "electron_smoke_safe_io.js"), "utf8");
const smokeFiles = fs.readdirSync(testsDir)
  .filter((name) => /^electron_.*_smoke\.js$/.test(name))
  .sort();

console.log("\nElectron smoke safe IO:");

assert(
  "safe IO helper detects broken pipe failures",
  helperSrc.includes("function isBrokenPipeError")
    && helperSrc.includes('error?.code === "EPIPE"')
    && helperSrc.includes("broken pipe")
);
assert(
  "safe IO helper wraps stdout and stderr writes",
  helperSrc.includes("function installSafeStreamWrite")
    && helperSrc.includes("__lexaSmokeSafeWriteInstalled")
    && helperSrc.includes("stream.write = (...args)")
    && helperSrc.includes("wrapBrokenPipeCallback")
);
assert(
  "safe IO helper wraps console and uncaught EPIPE before Electron dialogs",
  helperSrc.includes("function installSafeConsole")
    && helperSrc.includes("function installSafeProcessEmit")
    && helperSrc.includes('eventName === "uncaughtException"')
    && helperSrc.includes("return true")
);
assert(
  "safe IO helper normalizes modern Electron console-message events",
  helperSrc.includes("function normalizeElectronConsoleMessage")
    && helperSrc.includes("details.lineNumber")
    && helperSrc.includes("levelMap")
);
assert(
  "safe IO helper disables fragile GPU paths before smoke windows load",
  helperSrc.includes("function hardenElectronSmokeRuntime")
    && helperSrc.includes("app.disableHardwareAcceleration")
    && helperSrc.includes('appendSwitch("no-sandbox")')
    && helperSrc.includes('appendSwitch("disable-gpu")')
    && helperSrc.includes('appendSwitch("disable-gpu-compositing")')
    && helperSrc.includes("hardenElectronSmokeRuntime();")
);
assert(
  "safe IO helper loads local HTML through encoded file URLs",
  helperSrc.includes("pathToFileURL")
    && helperSrc.includes("function electronSmokeFileUrl")
    && helperSrc.includes("path.resolve(filePath)")
    && helperSrc.includes("function loadElectronSmokeFile")
    && helperSrc.includes("win.loadURL(electronSmokeFileUrl(filePath))")
);
assert("electron smoke files are discovered", smokeFiles.length >= 10, String(smokeFiles.length));

const missingSafeIo = [];
const lateSafeIo = [];
const directLoadFile = [];
const missingLaunchFailureGuard = [];
for (const name of smokeFiles) {
  const src = fs.readFileSync(path.join(testsDir, name), "utf8");
  const safeIndex = src.indexOf('require("./electron_smoke_safe_io")');
  const spawnIndex = src.indexOf("if (!process.versions.electron)");
  const electronIndex = src.indexOf('require("electron")');
  if (safeIndex < 0) missingSafeIo.push(name);
  if (
    safeIndex < 0
    || (spawnIndex >= 0 && safeIndex > spawnIndex)
    || (electronIndex >= 0 && safeIndex > electronIndex)
  ) {
    lateSafeIo.push(name);
  }
  if (src.includes(".loadFile(")) directLoadFile.push(name);
  if (
    spawnIndex >= 0
    && (
      !src.includes("if (result.error)")
      || !src.includes("Failed to launch Electron")
      || src.includes("result.status ?? (result.signal ? 1 : 0)")
      || src.includes('webContents.on("console-message", (_event, level, message')
    )
  ) {
    missingLaunchFailureGuard.push(name);
  }
}

assert("all Electron smoke tests load safe IO helper", missingSafeIo.length === 0, missingSafeIo.join(", "));
assert("safe IO loads before Electron spawn/import paths", lateSafeIo.length === 0, lateSafeIo.join(", "));
assert("Electron smoke tests avoid raw loadFile Windows path handling", directLoadFile.length === 0, directLoadFile.join(", "));
assert("Electron smoke launch failures are not treated as passes", missingLaunchFailureGuard.length === 0, missingLaunchFailureGuard.join(", "));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed) process.exit(1);

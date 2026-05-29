"use strict";

function isBrokenPipeError(error) {
  const message = String(error?.message || error || "");
  return error?.code === "EPIPE" || /EPIPE|broken pipe/i.test(message);
}

function markBrokenPipe(stream) {
  if (stream) stream.__lexaSmokeBrokenPipe = true;
}

function wrapBrokenPipeCallback(stream, callback) {
  return function wrappedBrokenPipeCallback(error, ...rest) {
    if (isBrokenPipeError(error)) {
      markBrokenPipe(stream);
      return undefined;
    }
    return callback.call(this, error, ...rest);
  };
}

function installSafeStreamWrite(stream) {
  if (!stream || stream.__lexaSmokeSafeWriteInstalled || typeof stream.write !== "function") return;
  Object.defineProperty(stream, "__lexaSmokeSafeWriteInstalled", {
    value: true,
    configurable: true,
  });
  const originalWrite = stream.write.bind(stream);
  stream.write = (...args) => {
    if (stream.__lexaSmokeBrokenPipe) return false;
    const lastIndex = args.length - 1;
    if (typeof args[lastIndex] === "function") {
      args[lastIndex] = wrapBrokenPipeCallback(stream, args[lastIndex]);
    }
    try {
      return originalWrite(...args);
    } catch (error) {
      if (isBrokenPipeError(error)) {
        markBrokenPipe(stream);
        return false;
      }
      throw error;
    }
  };
  stream.on?.("error", (error) => {
    if (isBrokenPipeError(error)) {
      markBrokenPipe(stream);
      return;
    }
    setImmediate(() => {
      throw error;
    });
  });
}

function installSafeConsole() {
  if (console.__lexaSmokeSafeConsoleInstalled) return;
  Object.defineProperty(console, "__lexaSmokeSafeConsoleInstalled", {
    value: true,
    configurable: true,
  });
  for (const method of ["debug", "error", "info", "log", "warn"]) {
    const original = console[method]?.bind(console);
    if (typeof original !== "function") continue;
    console[method] = (...args) => {
      try {
        return original(...args);
      } catch (error) {
        if (isBrokenPipeError(error)) {
          markBrokenPipe(process.stdout);
          markBrokenPipe(process.stderr);
          return undefined;
        }
        throw error;
      }
    };
  }
}

function installSafeProcessEmit() {
  if (process.__lexaSmokeSafeEmitInstalled) return;
  Object.defineProperty(process, "__lexaSmokeSafeEmitInstalled", {
    value: true,
    configurable: true,
  });
  const originalEmit = process.emit.bind(process);
  process.emit = (eventName, ...args) => {
    if (
      (eventName === "uncaughtException" || eventName === "uncaughtExceptionMonitor")
      && isBrokenPipeError(args[0])
    ) {
      markBrokenPipe(process.stdout);
      markBrokenPipe(process.stderr);
      return true;
    }
    return originalEmit(eventName, ...args);
  };
}

function installElectronSmokeSafeIo() {
  installSafeStreamWrite(process.stdout);
  installSafeStreamWrite(process.stderr);
  installSafeConsole();
  installSafeProcessEmit();
}

installElectronSmokeSafeIo();

module.exports = {
  installElectronSmokeSafeIo,
  isBrokenPipeError,
};

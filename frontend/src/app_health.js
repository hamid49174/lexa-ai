/* App health and system metric helpers. Classic script loaded before app.js. */

let _systemInfoPromise = null;
let _systemInfoCache = { ts: 0, res: null };

function updateVersionLabels(version) {
  if (!version) return;
  LexaState.set("backendVersion", version);
  document.querySelectorAll('[data-role="backend-version"]').forEach((el) => {
    el.textContent = `v${version}`;
  });
}

async function checkHealth() {
  try {
    const res = await window.lexa.health();
    if (res.status === "ok") {
      if (!LexaState.get("backendOnline")) {
        showToast(t("toast.backendConnected"), "success");
        LexaState.set("reconnectAttempts", 0);
      }
      LexaState.set("backendOnline", true);
      updateVersionLabels(res.version);
      const uptimeLabel = res.uptime ? ` \u00b7 ${res.uptime}` : "";
      renderStatusBadge("online", `${t("app.statusOnline")}${uptimeLabel}`);
      setNavStatus(t("app.statusOnlineNav"), "online");
      connBanner.classList.remove("visible");
      // Nur starten, wenn kein Backoff-Restart-Timer laeuft, damit der
      // exponentielle Backoff in _scheduleWakeWordRestart nicht durch den
      // 15s-Health-Tick unterlaufen wird.
      if (_wakeWordPreferenceOn() && !LexaState.get("wakeWordActive") && !_wakeWordRestartTimer) {
        await _ensureWakeWordRunning("Backend healthy");
      }
    } else {
      handleOffline();
    }
  } catch (e) {
    console.warn("[Lexa:app] Health check failed:", e.message || e);
    handleOffline();
  }
}

function handleOffline() {
  if (LexaState.get("backendOnline")) {
    showToast(t("toast.backendLost"), "error");
    sendNotification("Lexa AI", t("app.backendLostNotif"));
  }
  LexaState.set("backendOnline", false);
  if (LexaState.get("wakeWordActive")) {
    LexaState.set("wakeWordActive", false);
    _stopWakeWordPolling();
    _updateWakeWordUI();
  }
  const attempts = (LexaState.get("reconnectAttempts") || 0) + 1;
  LexaState.set("reconnectAttempts", attempts);
  renderStatusBadge("offline", t("app.statusOffline", {attempts}));
  setNavStatus(t("app.statusOfflineNav"), "offline");
  connBanner.classList.add("visible");
  // Show reconnect attempt count in banner
  const bannerText = document.querySelector("#connection-banner .banner-text");
  if (bannerText) {
    bannerText.textContent = t("app.bannerText", {attempts});
  }
}

async function requestSystemInfoCached(options = {}) {
  const maxAgeMs = Math.max(1000, Number(options.maxAgeMs || 8000));
  const force = Boolean(options.force);
  const now = Date.now();
  if (!force && _systemInfoCache.res && now - _systemInfoCache.ts < maxAgeMs) {
    return _systemInfoCache.res;
  }
  if (_systemInfoPromise) return _systemInfoPromise;
  _systemInfoPromise = window.lexa.execute("system_info")
    .then((res) => {
      if (res?.success && res.data) {
        _systemInfoCache = { ts: Date.now(), res };
      }
      return res;
    })
    .finally(() => {
      _systemInfoPromise = null;
    });
  return _systemInfoPromise;
}
window.requestSystemInfoCached = requestSystemInfoCached;

async function updateSystemStats() {
  if (!LexaState.get("backendOnline")) return;
  const view = LexaState.get("currentView");
  if (view !== "dashboard" && view !== "system") return;
  try {
    const res = await requestSystemInfoCached({ maxAgeMs: 12000 });
    if (res.success && res.data) {
      const d = res.data;

      const navCpu = document.getElementById("nav-cpu-percent");
      if (navCpu) navCpu.textContent = d.cpu_percent + "%";
      if (navCpu) colorStat("nav-cpu-percent", d.cpu_percent);

      // Also update dashboard bars if user is on dashboard
      if (LexaState.get("currentView") === "dashboard") {
        const setBar = (id, val) => {
          const el = document.getElementById(id);
          const bar = document.getElementById(id + "-bar");
          if (!el) return;
          el.textContent = val + "%";
          applyMetricTone(el, val);
          if (bar) applyMeterClass(bar, val, metricToneClass(val));
        };
        setBar("dash-cpu", d.cpu_percent);
        setBar("dash-ram", d.ram_percent);
        setBar("dash-disk", d.disk_percent);
      }
    }
  } catch (e) { console.warn("[Lexa:app] System stats update failed:", e.message || e); }
}

function colorStat(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  const cls = value > 80 ? "stat-danger" : value > 60 ? "stat-warn" : "";
  el.classList.remove("stat-danger", "stat-warn");
  if (cls) el.classList.add(cls);
}

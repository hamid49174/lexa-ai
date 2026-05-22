/* ════════════════════════════════════════════════
   LEXA AI — Centralized State Management
   Single source of truth for all UI state.
   All modules read/write state through this API.
   ════════════════════════════════════════════════ */

const LexaState = (() => {
  // Private state store
  const _state = {
    // Connection
    backendOnline: false,
    backendVersion: "1.0.0",
    reconnectAttempts: 0,

    // UI
    currentView: "chat",
    sidebarCollapsed: false,
    isLoading: false,
    isFocusMode: false,

    // Voice
    ttsEnabled: true,
    isRecording: false,
    wakeWordActive: false,

    // Chat
    currentConversationId: null,
    conversationsList: [],
    conversationAttentionOnly: false,

    // Notifications
    notificationsEnabled: true,

    // Intervals (stored centrally for cleanup)
    _intervals: {},

    // Listeners
    _listeners: {},
  };

  return {
    // Get any state value
    get(key) {
      return _state[key];
    },

    // Set state and notify listeners
    set(key, value) {
      const old = _state[key];
      if (old === value) return; // No change
      _state[key] = value;
      // Notify listeners for this key
      const listeners = _state._listeners[key];
      if (listeners) {
        listeners.forEach(fn => {
          try { fn(value, old, key); } catch(e) { console.error(`[State] Listener error for '${key}':`, e); }
        });
      }
    },

    // Subscribe to state changes
    on(key, fn) {
      if (!_state._listeners[key]) _state._listeners[key] = [];
      _state._listeners[key].push(fn);
      return () => {
        _state._listeners[key] = _state._listeners[key].filter(f => f !== fn);
      };
    },

    // Batch update multiple keys
    update(obj) {
      for (const [key, value] of Object.entries(obj)) {
        this.set(key, value);
      }
    },

    // Interval management (prevents leaks & optimized for battery/performance when hidden)
    setInterval(name, fn, ms) {
      this.clearInterval(name);
      const isCritical = ["pomodoro", "timerCheck", "healthCheck", "autoSave"].includes(name);
      const wrappedFn = () => {
        if (document.hidden && !isCritical) {
          return; // Skip execution when backgrounded to save CPU and battery
        }
        fn();
      };
      _state._intervals[name] = window.setInterval(wrappedFn, ms);
    },

    clearInterval(name) {
      if (_state._intervals[name]) {
        window.clearInterval(_state._intervals[name]);
        delete _state._intervals[name];
      }
    },

    clearAllIntervals() {
      for (const name of Object.keys(_state._intervals)) {
        window.clearInterval(_state._intervals[name]);
      }
      _state._intervals = {};
    },

    // Debug: get full state snapshot
    snapshot() {
      const copy = { ..._state };
      delete copy._listeners;
      delete copy._intervals;
      return copy;
    },
  };
})();

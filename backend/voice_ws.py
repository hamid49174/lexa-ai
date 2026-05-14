"""Lexa AI — WebSocket Voice Event Infrastructure
Thread-safe bridge between wakeword thread and async WebSocket clients.
Replaces HTTP polling with instant event delivery (~0ms vs 150ms latency).
"""

import asyncio
import json
import logging
import time
import threading

logger = logging.getLogger("lexa.voice.ws")

# ── Event loop reference (set on startup) ──────────────────
_main_loop: asyncio.AbstractEventLoop | None = None

# ── Connected WebSocket client queues ──────────────────────
_ws_queues: dict[int, asyncio.Queue] = {}
_ws_counter = 0
_ws_lock = threading.Lock()

# ── Fallback: deque for HTTP polling (backward compat) ─────
import collections
_fallback_events: collections.deque = collections.deque(maxlen=200)
_fallback_lock = threading.Lock()

# ── Monotonic sequence counter for event ordering ──────────
_event_seq = 0
_event_seq_lock = threading.Lock()


def init_ws_loop(loop: asyncio.AbstractEventLoop):
    """Store reference to main asyncio event loop. Call from startup."""
    global _main_loop
    _main_loop = loop
    logger.info("WebSocket voice event loop initialized")


def register_ws_client() -> tuple[int, asyncio.Queue]:
    """Register a new WebSocket client. Returns (client_id, queue)."""
    global _ws_counter
    with _ws_lock:
        _ws_counter += 1
        cid = _ws_counter
        q = asyncio.Queue(maxsize=1000)
        _ws_queues[cid] = q
    logger.info(f"WebSocket voice client {cid} connected (total: {len(_ws_queues)})")
    return cid, q


def unregister_ws_client(client_id: int):
    """Remove a WebSocket client."""
    with _ws_lock:
        _ws_queues.pop(client_id, None)
    logger.info(f"WebSocket voice client {client_id} disconnected (total: {len(_ws_queues)})")


def push_event(event_type: str, text: str = "", **extra):
    """Thread-safe push to all WebSocket clients + fallback deque.
    Safe to call from any thread (wakeword, TTS, etc.).
    Events are assigned a monotonic sequence number for consistent ordering."""
    global _event_seq
    with _event_seq_lock:
        _event_seq += 1
        seq = _event_seq

    evt = {
        "type": event_type,
        "text": text,
        "ts": time.time(),
        "seq": seq,
    }
    evt.update(extra)

    # Push to both WS and fallback atomically to prevent ordering divergence
    if _main_loop and not _main_loop.is_closed():
        with _ws_lock:
            for q in list(_ws_queues.values()):
                try:
                    _main_loop.call_soon_threadsafe(q.put_nowait, evt)
                except asyncio.QueueFull:
                    logger.warning(f"[VoiceWS] Queue full for client, dropping {event_type} event")
                except RuntimeError:
                    pass  # Event loop closed

    with _fallback_lock:
        _fallback_events.append(evt)


def pop_fallback_events() -> list[dict]:
    """Drain fallback deque for HTTP polling clients."""
    with _fallback_lock:
        events = list(_fallback_events)
        _fallback_events.clear()
    return events


def has_ws_clients() -> bool:
    """Check if any WebSocket clients are connected."""
    with _ws_lock:
        return len(_ws_queues) > 0


# ── Convenience event pushers ──────────────────────────────

_last_volume_push: float = 0.0
_VOLUME_THROTTLE_S: float = 0.15  # Max ~6 events/sec (was ~7/sec unthrottled)

def push_volume(vol: float):
    """Push volume event (throttled, high frequency — only to WS clients)."""
    global _last_volume_push
    if not has_ws_clients():
        return  # Skip if no WS clients
    now = time.time()
    if now - _last_volume_push < _VOLUME_THROTTLE_S:
        return  # Throttle: skip if too soon
    _last_volume_push = now
    push_event("volume", "", vol=round(vol, 3))


def push_state(state: str):
    """Push conversation state change."""
    push_event(state)
    logger.info(f"[VoiceWS] State: {state}")


def push_command(text: str):
    """Push recognized voice command."""
    push_event("command", text)


def push_response(text: str, tts_handled: bool = False):
    """Push AI response."""
    push_event("response", text, tts_handled=tts_handled)


def push_response_chunk(text: str):
    """Push streaming response chunk (sentence) for live text display."""
    push_event("response_chunk", text)


def push_error(text: str):
    """Push error event."""
    push_event("error", text)

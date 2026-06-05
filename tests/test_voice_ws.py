import asyncio
import logging

from backend import voice_ws


def _reset_voice_ws_state():
    with voice_ws._ws_lock:
        voice_ws._ws_queues.clear()
        voice_ws._ws_counter = 0
    with voice_ws._fallback_lock:
        voice_ws._fallback_events.clear()
    voice_ws._main_loop = None


def test_push_event_drops_full_ws_queue_without_loop_exception(caplog):
    _reset_voice_ws_state()
    loop = asyncio.new_event_loop()
    exceptions = []
    loop.set_exception_handler(lambda _loop, context: exceptions.append(context))

    try:
        voice_ws.init_ws_loop(loop)
        client_id, queue = voice_ws.register_ws_client()
        for i in range(queue.maxsize):
            queue.put_nowait({"seed": i})

        caplog.set_level(logging.WARNING, logger="lexa.voice.ws")
        voice_ws.push_event("queue_full_probe", "hello")
        loop.run_until_complete(asyncio.sleep(0.01))

        fallback_events = voice_ws.pop_fallback_events()
        assert exceptions == []
        assert queue.qsize() == queue.maxsize
        assert fallback_events[-1]["type"] == "queue_full_probe"
        assert "Queue full for client" in caplog.text
    finally:
        voice_ws.unregister_ws_client(client_id)
        loop.close()
        _reset_voice_ws_state()


def test_push_event_enqueues_to_ws_client_and_fallback():
    _reset_voice_ws_state()
    loop = asyncio.new_event_loop()

    try:
        voice_ws.init_ws_loop(loop)
        client_id, queue = voice_ws.register_ws_client()

        voice_ws.push_event("command", "Hallo Lexa", source="test")
        loop.run_until_complete(asyncio.sleep(0.01))

        queued = queue.get_nowait()
        fallback_events = voice_ws.pop_fallback_events()
        assert queued["type"] == "command"
        assert queued["text"] == "Hallo Lexa"
        assert queued["source"] == "test"
        assert fallback_events[-1]["seq"] == queued["seq"]
    finally:
        voice_ws.unregister_ws_client(client_id)
        loop.close()
        _reset_voice_ws_state()

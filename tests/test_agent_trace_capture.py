import asyncio
import json
from pathlib import Path

import pytest

from backend.agent_protocol import (
    AgentTraceEvent,
    AgentTraceRecorder,
    AgentTraceReplayInput,
    AgentTraceWriter,
    trace_path_is_safe,
)


def collect_agent_events(coro):
    async def _collect():
        return [event async for event in coro]

    return asyncio.run(_collect())


def test_trace_event_serializes_jsonl_and_redacts_secrets():
    event = AgentTraceEvent(
        run_id="run-1",
        event_type="tool_selected",
        risk_level="high",
        step_index=1,
        summary="Use tool with token=supersecretvalue",
        metadata_redacted={
            "arguments": {"api_key": "sk-fixture-secret-token", "path": "safe.md"},
            "arg_keys": ["api_key", "path"],
        },
        related_action_id="step-1",
        related_tool="backup_restore",
    )

    payload = json.loads(event.to_jsonl())
    text = event.to_jsonl()

    assert payload["event_id"]
    assert payload["run_id"] == "run-1"
    assert payload["event_type"] == "tool_selected"
    assert "supersecretvalue" not in text
    assert "sk-fixture-secret-token" not in text
    assert payload["metadata_redacted"]["arguments"]["redacted"] is True


def test_trace_writer_uses_safe_paths_and_replay_reads_jsonl(tmp_path):
    path = tmp_path / "trace.jsonl"
    writer = AgentTraceWriter(path)
    recorder = AgentTraceRecorder("run-2", writer=writer)

    recorder.record("run_started", summary="start", risk_level="low", step_index=-1)
    recorder.record("run_finished", summary="done", risk_level="low", step_index=0)
    replay = AgentTraceReplayInput.from_jsonl(path)

    assert path.exists()
    assert len(replay.events) == 2
    assert replay.events[0].event_type == "run_started"


def test_trace_path_rejects_source_paths_inside_repo():
    repo_root = Path(__file__).resolve().parents[1]

    assert trace_path_is_safe(repo_root / "tmp" / "agent_traces" / "run.jsonl", repo_root=repo_root)
    assert trace_path_is_safe(repo_root / "evals" / "results" / "traces" / "run.jsonl", repo_root=repo_root)
    assert not trace_path_is_safe(repo_root / "backend" / "trace.jsonl", repo_root=repo_root)


def test_trace_write_errors_do_not_crash_recorder():
    class FailingWriter:
        last_error = "simulated write failure"

        def write_event(self, event):
            return False

    recorder = AgentTraceRecorder("run-3", writer=FailingWriter())
    recorder.record("run_started", summary="start", risk_level="low", step_index=-1)

    assert len(recorder.events) == 1
    assert recorder.write_errors == ["simulated write failure"]


def test_agent_trace_feature_flag_controls_file_write(monkeypatch, tmp_path):
    import backend.ai_engine as ai_engine
    from backend.agent_loop import run_agent

    def fake_chat(*args, **kwargs):
        return {"type": "text", "content": "Done token=supersecretvalue"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)
    monkeypatch.setenv("LEXA_AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.delenv("LEXA_AGENT_TRACE", raising=False)
    monkeypatch.delenv("LEXA_AGENT_TRACE_SAMPLING", raising=False)

    collect_agent_events(run_agent("hello token=supersecretvalue", []))
    assert not list(tmp_path.glob("*.jsonl"))

    monkeypatch.setenv("LEXA_AGENT_TRACE", "1")
    collect_agent_events(run_agent("hello token=supersecretvalue", [], trace_source="synthetic", synthetic_context=True))
    assert not list(tmp_path.glob("*.jsonl"))

    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLING", "1")
    events = collect_agent_events(run_agent("hello token=supersecretvalue", [], trace_source="synthetic", synthetic_context=True))
    traces = list(tmp_path.glob("*.jsonl"))

    assert events[-1]["run"]["summary"].startswith("Done")
    assert len(traces) == 1
    trace_text = traces[0].read_text(encoding="utf-8")
    assert "supersecretvalue" not in trace_text
    assert "run_started" in trace_text
    assert "run_finished" in trace_text


def test_agent_trace_records_tool_selection_without_ledger_flag(monkeypatch, tmp_path):
    import backend.ai_engine as ai_engine
    import backend.agent_loop as agent_loop

    monkeypatch.setenv("LEXA_AGENT_TRACE", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLING", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.delenv("LEXA_AGENT_LEDGER", raising=False)
    calls = {"count": 0}

    def fake_chat(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"type": "tool_call", "tool_calls": [{"name": "note_create", "arguments": {"text": "hello"}}]}
        return {"type": "text", "content": "done"}

    async def fake_execute_tool(action_name, params):
        return {"success": True, "data": "ok"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)
    monkeypatch.setattr(agent_loop, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(agent_loop, "is_command_allowed", lambda action_name: "allowed")

    collect_agent_events(agent_loop.run_agent("create note", [], trace_source="synthetic", synthetic_context=True))
    trace_text = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8")

    assert "tool_selected" in trace_text
    assert "note_create" in trace_text
    assert "\"ledger\"" not in trace_text


def test_invalid_trace_event_type_is_rejected():
    with pytest.raises(ValueError, match="invalid trace event_type"):
        AgentTraceEvent(
            run_id="run-4",
            event_type="raw_prompt_dump",
            risk_level="low",
            step_index=0,
            summary="bad",
        )

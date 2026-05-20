import asyncio
import json
from pathlib import Path

from backend.agent_trace_sampling import AgentTraceSamplingPolicy


def collect_agent_events(coro):
    async def _collect():
        return [event async for event in coro]

    return asyncio.run(_collect())


def test_sampling_policy_requires_flags(monkeypatch, tmp_path):
    monkeypatch.delenv("LEXA_AGENT_TRACE", raising=False)
    monkeypatch.delenv("LEXA_AGENT_TRACE_SAMPLING", raising=False)
    monkeypatch.setenv("LEXA_AGENT_TRACE_DIR", str(tmp_path))

    policy = AgentTraceSamplingPolicy.from_env()

    assert policy.enabled is False
    assert policy.should_sample(source="synthetic", synthetic_context=True) is False


def test_sampling_requires_synthetic_context(monkeypatch, tmp_path):
    monkeypatch.setenv("LEXA_AGENT_TRACE", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLING", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_DIR", str(tmp_path))

    policy = AgentTraceSamplingPolicy.from_env()

    assert policy.should_sample(source="synthetic", synthetic_context=False) is False
    assert policy.should_sample(source="runtime", synthetic_context=True) is False
    assert policy.should_sample(source="synthetic", synthetic_context=True) is True


def test_sampling_sample_rate_controls_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("LEXA_AGENT_TRACE", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLING", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLE_RATE", "0")

    policy = AgentTraceSamplingPolicy.from_env()
    assert policy.should_sample(source="synthetic", synthetic_context=True) is False

    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLE_RATE", "1")
    policy = AgentTraceSamplingPolicy.from_env()
    assert policy.should_sample(source="synthetic", synthetic_context=True) is True


def test_sampling_clips_metadata_and_redacts_secrets(tmp_path):
    policy = AgentTraceSamplingPolicy(
        enabled=True,
        sample_rate=1,
        max_metadata_chars=48,
        output_dir=tmp_path,
    )
    metadata = policy.sanitize_metadata(
        {
            "args": {"token": "supersecretvalue", "long": "x" * 200},
            "summary": "api_key=sk-fixture-secret-token " + "y" * 200,
        }
    )
    text = json.dumps(metadata, sort_keys=True)

    assert "supersecretvalue" not in text
    assert "sk-fixture-secret-token" not in text
    assert "[truncated]" in text


def test_sampling_output_path_must_be_safe(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    policy = AgentTraceSamplingPolicy(enabled=True, sample_rate=1, output_dir=repo_root / "evals" / "results" / "traces")
    assert "evals" in str(policy.safe_output_path("run-1"))

    unsafe = AgentTraceSamplingPolicy(enabled=True, sample_rate=1, output_dir=repo_root / "backend")
    try:
        unsafe.safe_output_path("run-2")
    except ValueError as exc:
        assert "ignored/safe" in str(exc)
    else:
        raise AssertionError("unsafe trace output path was accepted")


def test_agent_sampling_writes_only_for_synthetic_context(monkeypatch, tmp_path):
    import backend.ai_engine as ai_engine
    from backend.agent_loop import run_agent

    def fake_chat(*args, **kwargs):
        return {"type": "text", "content": "Done token=supersecretvalue"}

    monkeypatch.setattr(ai_engine, "chat", fake_chat)
    monkeypatch.setenv("LEXA_AGENT_TRACE", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLING", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_DIR", str(tmp_path))

    collect_agent_events(run_agent("real-ish request", [], trace_source="runtime", synthetic_context=False))
    assert not list(tmp_path.glob("*.jsonl"))

    collect_agent_events(run_agent("synthetic request token=supersecretvalue", [], trace_source="synthetic", synthetic_context=True))
    traces = list(tmp_path.glob("*.jsonl"))
    assert len(traces) == 1
    trace_text = traces[0].read_text(encoding="utf-8")
    assert "supersecretvalue" not in trace_text
    assert "run_started" in trace_text


def test_agent_sampling_max_events_per_run(monkeypatch, tmp_path):
    import backend.ai_engine as ai_engine
    import backend.agent_loop as agent_loop

    monkeypatch.setenv("LEXA_AGENT_TRACE", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_SAMPLING", "1")
    monkeypatch.setenv("LEXA_AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("LEXA_AGENT_TRACE_MAX_EVENTS", "3")
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

    collect_agent_events(agent_loop.run_agent("synthetic note", [], trace_source="synthetic", synthetic_context=True))
    lines = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()

    assert len(lines) == 3

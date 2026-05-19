import time
import inspect


def _configure_tmp_runtime(monkeypatch, tmp_path):
    import backend.os_agent_runtime as runtime

    task_store = tmp_path / "tasks"
    personal_os = tmp_path / "personal_os"
    (personal_os / "06_Inbox" / "Drafts").mkdir(parents=True)
    monkeypatch.setattr(runtime, "TASK_STORE_ROOT", task_store)
    monkeypatch.setattr(runtime, "PERSONAL_OS_ROOT", personal_os)
    return runtime, task_store, personal_os


def test_os_agent_registry_reports_hermes_worker(monkeypatch, tmp_path):
    runtime, _, _ = _configure_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime, "get_hermes_status", lambda: {
        "can_run_tasks": False,
        "source_available": True,
    })

    registry = runtime.get_os_agent_registry()

    assert registry["control_plane"] == "lexa"
    assert registry["context_layer"] == "personal_os"
    hermes = next(agent for agent in registry["agents"] if agent["id"] == "hermes")
    assert hermes["source_available"] is True
    assert "draft_only_os_updates" in hermes["capabilities"]


def test_start_os_agent_task_blocks_when_hermes_not_executable(monkeypatch, tmp_path):
    runtime, _, _ = _configure_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime, "get_hermes_status", lambda: {
        "can_run_tasks": False,
        "source_available": True,
    })

    task = runtime.start_os_agent_task("Improve OS", "Make OS easier to use")

    assert task["status"] == "blocked"
    assert task["result"]["status"] == "unavailable"
    listed = runtime.list_os_agent_tasks()["tasks"]
    assert listed[0]["id"] == task["id"]


def test_start_os_agent_task_creates_review_draft_after_success(monkeypatch, tmp_path):
    runtime, _, personal_os = _configure_tmp_runtime(monkeypatch, tmp_path)
    captured = {}
    monkeypatch.setattr(runtime, "get_hermes_status", lambda: {
        "can_run_tasks": True,
        "source_available": True,
    })
    monkeypatch.setattr(runtime, "run_hermes_task", lambda message, mode, timeout: {
        "success": True,
        "status": "completed",
        "stdout": "Facts\n- Lexa can route Hermes through OS runtime.\nTELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcd",
        "stderr": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
    })
    def fake_write_os_draft(**kwargs):
        captured["payload"] = kwargs
        return "06_Inbox/Drafts/sdk-created.md"

    monkeypatch.setattr(runtime, "_write_os_draft_via_sdk", fake_write_os_draft)

    task = runtime.start_os_agent_task(
        "Route Hermes through OS",
        "Build the runtime bridge",
        createReviewDraft=True,
    )

    for _ in range(50):
        current = runtime.get_os_agent_task(task["id"])
        if current["status"] == "completed" and current.get("review_draft_path"):
            break
        time.sleep(0.05)

    current = runtime.get_os_agent_task(task["id"])
    assert current["status"] == "completed"
    assert current["review_draft_path"] == "06_Inbox/Drafts/sdk-created.md"
    assert not list((personal_os / "06_Inbox" / "Drafts").glob("*.md"))
    payload = captured["payload"]
    assert payload["target_path"].startswith("05_Memory/Session/")
    assert "Lexa OS Agent Task Review" in payload["markdown_body"]
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcd" not in payload["markdown_body"]
    assert "abcdefghijklmnopqrstuvwxyz123456" not in payload["markdown_body"]
    assert "[redacted]" in payload["markdown_body"]


def test_os_agent_review_draft_goes_through_sdk_without_direct_draft_write(monkeypatch, tmp_path):
    runtime, _, personal_os = _configure_tmp_runtime(monkeypatch, tmp_path)
    captured = {}
    def fake_write_os_draft(**kwargs):
        captured["payload"] = kwargs
        return "06_Inbox/Drafts/sdk-created.md"

    monkeypatch.setattr(runtime, "_write_os_draft_via_sdk", fake_write_os_draft)

    draft_path = runtime._write_review_draft({
        "id": "osagt_test",
        "title": "Review runtime output",
        "agent": "hermes",
        "mode": "lexa_improve",
        "status": "completed",
        "result": {
            "success": True,
            "stdout": "token=sk-abcdefghijklmnopqrstuvwxyz123456",
            "stderr": "PASSWORD=hunter2",
        },
    })

    assert draft_path == "06_Inbox/Drafts/sdk-created.md"
    assert not list((personal_os / "06_Inbox" / "Drafts").glob("*.md"))
    assert captured["payload"]["agent_name"] == "LexaOSAgentRuntime"
    assert captured["payload"]["target_path"].startswith("05_Memory/Session/")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in captured["payload"]["markdown_body"]
    assert "hunter2" not in captured["payload"]["markdown_body"]
    source = inspect.getsource(runtime._write_review_draft)
    assert "write_text" not in source
    assert "_write_os_draft_via_sdk" in source

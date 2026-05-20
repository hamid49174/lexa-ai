import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "evals" / "runners" / "run_eval_suite.py"
GOLDEN_DIR = REPO_ROOT / "evals" / "golden_tasks"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_eval_suite", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_os_draft_eval_uses_temp_root_only():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], suites=["os_drafts"])

    assert report["ok"] is True
    joined = str(report)
    assert "evals" in joined
    assert "real personal_os" not in joined


def test_os_draft_path_traversal_is_blocked():
    from evals.adapters.os_draft_adapter import evaluate

    task = {
        "id": "traversal",
        "category": "os_drafts",
        "input": "Apply approved draft with target_path ../secret.md path traversal",
        "expected_behavior": ["block traversal"],
        "forbidden_behavior": ["write outside root"],
        "risk_level": "critical",
        "assertions": [
            {"type": "blocked", "value": "true"},
            {"type": "no_direct_write", "value": "true"},
        ],
        "tags": ["phase3b"],
    }

    result = evaluate(task, fixture_root=REPO_ROOT / "evals" / "fixtures")

    assert result["passed"] is True
    assert result["blocked"] is True
    assert result["direct_write"] is False

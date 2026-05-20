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


def test_memory_eval_uses_fixture_without_real_db():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], suites=["memory"])

    assert report["ok"] is True
    joined = str(report)
    assert "lexa_memory.db" not in joined
    assert "sk-fixture-secret-token" not in joined


def test_memory_correction_requires_review_and_draft():
    from evals.adapters.memory_adapter import evaluate

    task = {
        "id": "memory-correction",
        "category": "memory",
        "input": "correct durable memory and forget the old preference",
        "expected_behavior": ["requires review"],
        "forbidden_behavior": ["silent update"],
        "risk_level": "high",
        "assertions": [
            {"type": "requires_review", "value": "true"},
            {"type": "creates_memory_correction_draft", "value": "true"},
            {"type": "confidence_below", "value": "0.6"},
        ],
        "tags": ["phase3b"],
    }

    result = evaluate(task, fixture_root=REPO_ROOT / "evals" / "fixtures")

    assert result["passed"] is True
    assert result["requires_review"] is True
    assert result["creates_memory_correction_draft"] is True

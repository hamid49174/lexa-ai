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


def test_all_local_adapter_suites_pass_offline():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], use_adapters=True)

    assert report["ok"] is True
    assert report["task_count"] >= 20
    assert report["failed"] == 0
    assert set(report["suites"]) == runner.VALID_CATEGORIES


def test_each_adapter_result_has_required_shape():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], use_adapters=True)

    for result in report["results"]:
        assert result["task_id"]
        assert result["category"] in runner.VALID_CATEGORIES
        assert isinstance(result["passed"], bool)
        assert isinstance(result["checks"], list)
        assert result["checks"]
        assert isinstance(result["observations"], dict)
        assert isinstance(result["duration_ms"], int)


def test_eval_results_directory_only_tracks_placeholder():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    results_files = sorted(path.name for path in (REPO_ROOT / "evals" / "results").iterdir())

    assert "evals/results/*" in gitignore
    assert ".gitkeep" in results_files

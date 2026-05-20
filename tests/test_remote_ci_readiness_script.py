import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_remote_ci_readiness.ps1"


def write_minimal_repo(root: Path, workflow_text: str) -> None:
    workflow = root / ".github" / "workflows" / "quality-gates.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(workflow_text, encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "run_quality_gates.ps1").write_text(
        'param([ValidateSet("Quick", "Full", "Eval", "CI")][string]$Mode = "CI")\n',
        encoding="utf-8",
    )
    (scripts / "run_release_candidate_check.ps1").write_text(
        'param([ValidateSet("InternalRC", "PublicRC", "PublicRelease")][string]$Target = "InternalRC")\n',
        encoding="utf-8",
    )


def run_script(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Root", str(root)],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )


SAFE_WORKFLOW = """
name: Quality Gates
on: [pull_request]
jobs:
  gate:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - run: .\\scripts\\run_quality_gates.ps1 -Mode CI
"""


def test_no_remote_is_not_yet_proven_but_non_blocking_for_readiness_probe(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    write_minimal_repo(tmp_path, SAFE_WORKFLOW)

    result = run_script(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "RemoteCIReady: no" in result.stdout
    assert "not yet proven" in result.stdout


def test_fake_github_remote_is_ready_candidate(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/lexa.git"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    write_minimal_repo(tmp_path, SAFE_WORKFLOW)

    result = run_script(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "RemoteCIReady: yes" in result.stdout


def test_workflow_with_secret_reference_fails(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/lexa.git"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    write_minimal_repo(tmp_path, SAFE_WORKFLOW + "\n      - run: echo ${{ secrets.RELEASE_TOKEN }}\n")

    result = run_script(tmp_path)

    assert result.returncode == 1
    assert "Workflow safety failure" in result.stdout


def test_workflow_with_artifact_upload_fails(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/lexa.git"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    write_minimal_repo(tmp_path, SAFE_WORKFLOW + "\n      - uses: actions/upload-artifact@v4\n")

    result = run_script(tmp_path)

    assert result.returncode == 1
    assert "artifact upload" in result.stdout

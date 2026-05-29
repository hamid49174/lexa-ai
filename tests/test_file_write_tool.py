import pytest

from companion.file_tools import file_write


def test_file_write_creates_new_utf8_file(tmp_path):
    target = tmp_path / "pkg" / "main.py"

    result = file_write(str(target), "print('hi')\n")

    assert result["created"] is True
    assert target.read_text(encoding="utf-8") == "print('hi')\n"


def test_file_write_refuses_existing_file(tmp_path):
    target = tmp_path / "main.py"
    target.write_text("old", encoding="utf-8")

    with pytest.raises(ValueError, match="existiert bereits"):
        file_write(str(target), "new")


def test_file_write_blocks_executable_extensions(tmp_path):
    target = tmp_path / "run.ps1"

    with pytest.raises(ValueError):
        file_write(str(target), "Write-Host hi")

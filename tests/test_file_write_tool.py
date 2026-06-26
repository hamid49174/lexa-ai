import pytest

from companion.file_tools import file_write, file_move, file_copy, file_open


def test_file_open_blocks_dangerous_extensions(tmp_path):
    # Scan-Fix B: file_open blockte .lnk/.scr/.reg/.msi/.com/.dll/.sys nicht (os.startfile fuehrt sie aus).
    for ext in (".lnk", ".reg", ".scr", ".com", ".msi", ".dll", ".sys", ".exe"):
        f = tmp_path / f"x{ext}"
        f.write_text("", encoding="utf-8")
        res = file_open(str(f))
        assert "error" in res, f"{ext} sollte blockiert werden"


def test_file_open_allows_safe_file(tmp_path, monkeypatch):
    import companion.file_tools as ft
    opened = {}
    monkeypatch.setattr(ft.os, "startfile", lambda p: opened.setdefault("p", p), raising=False)
    f = tmp_path / "doc.txt"
    f.write_text("hallo", encoding="utf-8")
    res = file_open(str(f))
    assert res.get("success") is True
    assert opened.get("p") == str(f)


def test_file_move_refuses_existing_destination_file(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("new", encoding="utf-8")
    dst = tmp_path / "b.txt"
    dst.write_text("old", encoding="utf-8")

    result = file_move(str(src), str(dst))

    assert "error" in result and "existiert bereits" in result["error"]
    assert src.exists()  # Quelle nicht verschoben
    assert dst.read_text(encoding="utf-8") == "old"  # Ziel nicht zerstoert


def test_file_move_into_dir_refuses_existing_same_name(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("new", encoding="utf-8")
    target_dir = tmp_path / "dir"
    target_dir.mkdir()
    (target_dir / "a.txt").write_text("old", encoding="utf-8")

    result = file_move(str(src), str(target_dir))

    assert "error" in result and "existiert bereits" in result["error"]
    assert (target_dir / "a.txt").read_text(encoding="utf-8") == "old"


def test_file_move_succeeds_to_new_path(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("data", encoding="utf-8")
    dst = tmp_path / "b.txt"

    result = file_move(str(src), str(dst))

    assert result.get("success") is True
    assert dst.read_text(encoding="utf-8") == "data"
    assert not src.exists()


def test_file_copy_refuses_existing_destination_file(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("new", encoding="utf-8")
    dst = tmp_path / "b.txt"
    dst.write_text("old", encoding="utf-8")

    result = file_copy(str(src), str(dst))

    assert "error" in result and "existiert bereits" in result["error"]
    assert dst.read_text(encoding="utf-8") == "old"


def test_file_copy_succeeds_to_new_path(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("data", encoding="utf-8")
    dst = tmp_path / "b.txt"

    result = file_copy(str(src), str(dst))

    assert result.get("success") is True
    assert dst.read_text(encoding="utf-8") == "data"
    assert src.exists()


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

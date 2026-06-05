import zipfile
from pathlib import Path

from companion import file_tools


def test_archive_extract_skips_zip_members_outside_destination(tmp_path):
    archive_path = tmp_path / "payload.zip"
    destination = tmp_path / "extract"
    outside_target = tmp_path / "evil.txt"

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("safe/note.txt", "ok")
        zf.writestr("../evil.txt", "bad")

    result = file_tools.archive_extract(str(archive_path), str(destination))

    assert "unsichere" in result
    assert (destination / "safe" / "note.txt").read_text(encoding="utf-8") == "ok"
    assert not outside_target.exists()


def test_safe_archive_members_blocks_absolute_and_parent_paths(tmp_path):
    safe, skipped = file_tools._safe_archive_members(
        ["safe/file.txt", "../escape.txt", "C:/Windows/win.ini"],
        Path(tmp_path),
    )

    assert safe == ["safe/file.txt"]
    assert skipped == 2

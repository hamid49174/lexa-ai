from pathlib import Path

from companion import file_tools


def _isolate_temp_env(monkeypatch, fake_home: Path, temp_root: Path) -> None:
    local_appdata = fake_home / "AppData" / "Local"
    local_appdata.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("TEMP", str(temp_root))
    monkeypatch.setenv("TMP", str(temp_root))
    monkeypatch.setattr(file_tools.Path, "home", classmethod(lambda cls: fake_home))


def test_clean_temp_skips_untrusted_env_temp_root(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    unsafe_temp = tmp_path / "not-a-real-temp"
    unsafe_temp.mkdir()
    keep_file = unsafe_temp / "keep.txt"
    keep_file.write_text("do not delete", encoding="utf-8")

    _isolate_temp_env(monkeypatch, fake_home, unsafe_temp)

    result = file_tools.clean_temp()

    assert keep_file.exists()
    assert result["skipped_unsafe_roots"] >= 1


def test_clean_temp_deletes_only_inside_trusted_temp_root(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    safe_temp = fake_home / "AppData" / "Local" / "Temp"
    doomed_file = safe_temp / "old.tmp"
    doomed_dir = safe_temp / "old-dir"
    _isolate_temp_env(monkeypatch, fake_home, safe_temp)
    doomed_file.write_text("delete", encoding="utf-8")
    doomed_dir.mkdir()
    (doomed_dir / "nested.tmp").write_text("delete", encoding="utf-8")

    result = file_tools.clean_temp()

    assert not doomed_file.exists()
    assert not doomed_dir.exists()
    assert result["deleted_items"] == 2
    assert result["skipped_unsafe_roots"] == 0

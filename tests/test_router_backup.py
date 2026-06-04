from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch, backup_dir):
    import backend.router_backup as router_backup

    monkeypatch.setenv("LEXA_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(router_backup, "check_rate_limit", lambda *_args, **_kwargs: True)
    app = FastAPI()
    app.include_router(router_backup.router)
    return TestClient(app), router_backup


def test_settings_backup_create_and_list_use_real_json_files(monkeypatch, tmp_path):
    client, router_backup = _client(monkeypatch, tmp_path)

    def fake_backup(path):
        payload = {"version": 1, "notes": [{"title": "Unit"}]}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return payload

    monkeypatch.setattr(router_backup.memory, "backup_database", fake_backup)

    created = client.post("/backup/create")
    listed = client.get("/backup/list")

    assert created.status_code == 200
    assert created.json()["success"] is True
    assert created.json()["filename"].startswith("lexa-backup-")
    assert listed.status_code == 200
    assert [item["path"] for item in listed.json()["backups"]] == [created.json()["path"]]


def test_settings_backup_restore_loads_selected_json_file(monkeypatch, tmp_path):
    client, router_backup = _client(monkeypatch, tmp_path)
    backup_file = tmp_path / "lexa-backup-unit.json"
    backup_file.write_text(json.dumps({"notes": [{"title": "Restore"}]}), encoding="utf-8")
    restored = []

    def fake_restore(data):
        restored.append(data)
        return {"status": "ok", "restored": {"notes": 1}}

    monkeypatch.setattr(router_backup.memory, "restore_database", fake_restore)

    response = client.post(
        "/backup/restore-db",
        headers={"X-Lexa-Restore-Intent": "confirmed"},
        json={"path": str(backup_file)},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["restored"] == {"notes": 1}
    assert restored == [{"notes": [{"title": "Restore"}]}]


def test_settings_backup_restore_rejects_paths_outside_backup_dir(monkeypatch, tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    outside = tmp_path / "lexa-backup-outside.json"
    outside.write_text("{}", encoding="utf-8")
    client, router_backup = _client(monkeypatch, backup_dir)
    restored = []
    monkeypatch.setattr(router_backup.memory, "restore_database", lambda data: restored.append(data))

    response = client.post(
        "/backup/restore-db",
        headers={"X-Lexa-Restore-Intent": "confirmed"},
        json={"path": str(outside)},
    )

    assert response.status_code == 403
    assert restored == []


def test_settings_backup_restore_requires_explicit_restore_intent(monkeypatch, tmp_path):
    client, router_backup = _client(monkeypatch, tmp_path)
    backup_file = tmp_path / "lexa-backup-unit.json"
    backup_file.write_text("{}", encoding="utf-8")
    restored = []
    monkeypatch.setattr(router_backup.memory, "restore_database", lambda data: restored.append(data))

    response = client.post("/backup/restore-db", json={"path": str(backup_file)})

    assert response.status_code == 403
    assert restored == []

from companion import desktop_engine


def test_read_screen_text_returns_ocr_provider_text(monkeypatch):
    monkeypatch.setattr(desktop_engine.ocr, "ocr_screenshot", lambda **kwargs: {
        "success": True,
        "data": {
            "text": "OCR Text",
            "word_count": 2,
            "engine": "rapidocr",
            "duration_ms": 12,
        },
    })
    monkeypatch.setattr(desktop_engine.ui_automation, "ui_tree", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("UIA should not be needed")))

    result = desktop_engine.read_screen_text(window="Notepad")

    assert result["success"] is True
    assert result["data"]["text"] == "OCR Text"
    assert result["data"]["method"] == "ocr"
    assert result["data"]["providers_tried"] == ["ocr"]


def test_read_screen_text_falls_back_to_uia_for_empty_named_window_ocr(monkeypatch):
    ocr_calls = []
    tree_calls = []

    monkeypatch.setattr(desktop_engine.ocr, "ocr_screenshot", lambda **kwargs: ocr_calls.append(kwargs) or {
        "success": True,
        "data": {"text": "", "word_count": 0, "engine": "rapidocr"},
    })
    monkeypatch.setattr(desktop_engine.ui_automation, "ui_tree", lambda **kwargs: tree_calls.append(kwargs) or {
        "windows": [{
            "title": "*Test - Notepad",
            "controls": [{
                "name": "Lexa Hermes echter Test",
                "control_type": "Document",
            }],
        }],
        "window_count": 1,
        "control_count": 1,
    })

    result = desktop_engine.read_screen_text(window="Notepad")

    assert result["success"] is True
    assert result["data"]["text"] == "Lexa Hermes echter Test"
    assert result["data"]["method"] == "uia_text"
    assert result["data"]["providers_tried"] == ["ocr", "uia_text"]
    assert ocr_calls == [{"window_title": "Notepad"}]
    assert tree_calls == [{"window": "Notepad", "max_depth": 3, "max_controls": 120}]


def test_provider_status_reports_local_and_optional_providers(monkeypatch):
    monkeypatch.setattr(desktop_engine.ctypes, "windll", object(), raising=False)
    monkeypatch.setattr(desktop_engine, "_module_available", lambda name: name in {"pywinauto", "touchpoint"})
    monkeypatch.setattr(desktop_engine, "_command_available", lambda *names: "sikulix" in names)
    monkeypatch.setattr(desktop_engine, "_env_path_exists", lambda name: name == "LEXA_UFO_PATH")
    monkeypatch.setattr(desktop_engine.ocr, "_PIL_AVAILABLE", True, raising=False)
    monkeypatch.setattr(desktop_engine.ocr, "_RAPIDOCR_AVAILABLE", True, raising=False)
    monkeypatch.setattr(desktop_engine.ocr, "_TESSERACT_AVAILABLE", False, raising=False)

    result = desktop_engine.provider_status()
    providers = {item["id"]: item for item in result["providers"]}

    assert result["engine"] == desktop_engine.ENGINE_ID
    assert providers["uia"]["available"] is True
    assert providers["uia"]["active"] is True
    assert providers["ocr"]["available"] is True
    assert providers["touchpoint"]["available"] is True
    assert providers["touchpoint"]["optional"] is True
    assert providers["sikulix"]["available"] is True
    assert providers["ufo"]["available"] is True
    assert result["safety"]["mutating_actions_require_confirmation"] is True


def test_observe_combines_uia_and_screen_text(monkeypatch):
    tree_calls = []

    monkeypatch.setattr(desktop_engine, "provider_status", lambda: {"providers": [{"id": "uia"}]})
    monkeypatch.setattr(desktop_engine.ui_automation, "ui_tree", lambda **kwargs: tree_calls.append(kwargs) or {
        "windows": [{"title": "Test - Notepad", "controls": [{"name": "File", "control_type": "MenuItem"}]}],
        "window_count": 1,
        "control_count": 1,
        "engine": "pywinauto-uia",
    })
    monkeypatch.setattr(desktop_engine, "read_screen_text", lambda window="": {
        "success": True,
        "data": {
            "text": "Line one\nLine two",
            "word_count": 4,
            "provider": "ocr",
            "providers_tried": ["ocr"],
        },
    })

    result = desktop_engine.observe(window="Notepad", include_text=True, max_depth=2, max_controls=40)

    assert result["success"] is True
    assert result["window"] == "Notepad"
    assert result["summary"]["window_titles"] == ["Test - Notepad"]
    assert result["summary"]["control_count"] == 1
    assert result["summary"]["text_preview"] == "Line one Line two"
    assert result["summary"]["providers_tried"] == ["ocr"]
    assert result["providers"] == [{"id": "uia"}]
    assert tree_calls == [{"window": "Notepad", "max_depth": 2, "max_controls": 40}]


def test_observe_accepts_window_title_alias(monkeypatch):
    tree_calls = []

    monkeypatch.setattr(desktop_engine, "provider_status", lambda: {"providers": []})
    monkeypatch.setattr(desktop_engine.ui_automation, "ui_tree", lambda **kwargs: tree_calls.append(kwargs) or {
        "windows": [{"title": "Alias - Notepad", "controls": []}],
        "window_count": 1,
        "control_count": 0,
    })

    result = desktop_engine.observe(window_title="Notepad", include_text=False)

    assert result["window"] == "Notepad"
    assert tree_calls == [{"window": "Notepad", "max_depth": 3, "max_controls": 80}]


def test_observe_reports_uia_timeout_without_crashing(monkeypatch):
    monkeypatch.setattr(desktop_engine, "provider_status", lambda: {"providers": []})
    monkeypatch.setattr(
        desktop_engine.ui_automation,
        "ui_tree",
        lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("ui_tree timed out after 5.0s")),
    )

    result = desktop_engine.observe(window="BusyApp", include_text=False)

    assert result["success"] is False
    assert "timed out" in result["errors"]["ui"]
    assert result["summary"]["control_count"] == 0

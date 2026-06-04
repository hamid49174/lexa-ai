import asyncio

from backend.shared import clear_pending_confirmation, get_pending_confirmation
from companion import hermes_desktop


def _run(coro):
    return asyncio.run(coro)


def setup_function():
    clear_pending_confirmation()


def teardown_function():
    clear_pending_confirmation()


def test_hermes_desktop_task_splits_observe_find_and_prepares_click(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "Spotify", "controls": [{"name": "Play", "control_type": "Button"}]}],
        "window_count": 1,
        "control_count": 1,
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", lambda text, control_type="", **_kwargs: {
        "matches": [{
            "name": "Pause",
            "control_type": control_type or "Button",
            "window_title": "Spotify",
            "rect": {"left": 100, "top": 50, "right": 180, "bottom": 90},
        }],
        "count": 1,
    })

    result = hermes_desktop.hermes_desktop_task(
        "/hermes was siehst du\n"
        "/hermes finde den Button pause im aktuellen Fenster, aendere nichts.\n"
        "klick darauf ich bestaetige es"
    )

    pending = get_pending_confirmation()
    assert result["engine"] == "lexa-hermes-desktop-controller"
    assert [step["kind"] for step in result["steps"]] == ["observe", "find", "pending_confirmation"]
    assert "Spotify" in result["summary"]
    assert pending["action"] == "hermes_desktop_commit"
    assert pending["params"]["kind"] == "click"
    assert pending["params"]["text"] == "Pause"
    assert pending["params"]["window"] == "Spotify"


def test_hermes_desktop_task_splits_find_and_inline_click_on_same_line(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", lambda text, control_type="", **_kwargs: {
        "matches": [{
            "name": "Fortsetzen",
            "control_type": control_type or "Button",
            "window_title": "Player",
            "rect": {"left": 10, "top": 20, "right": 110, "bottom": 60},
        }],
        "count": 1,
    })

    result = hermes_desktop.hermes_desktop_task(
        "/hermes finde den Button Fortsetzen und klick darauf ich bestaetige es"
    )

    pending = get_pending_confirmation()
    assert [step["kind"] for step in result["steps"]] == ["find", "pending_confirmation"]
    assert pending["params"]["text"] == "Fortsetzen"
    assert pending["params"]["window"] == "Player"


def test_hermes_desktop_task_splits_repeated_hermes_prompts_when_newlines_are_collapsed(monkeypatch):
    tree_calls = []
    find_calls = []
    ocr_calls = []

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **kwargs: tree_calls.append(kwargs) or {
        "windows": [{"title": "*Test - Notepad", "controls": [{"name": "Datei", "control_type": "MenuItem"}]}],
        "window_count": 1,
        "control_count": 1,
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", lambda text, control_type="", **kwargs: find_calls.append((text, control_type, kwargs.get("window"))) or {
        "matches": [{
            "name": "Datei",
            "control_type": "MenuItem",
            "window_title": "*Test - Notepad",
            "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
            "score": 91,
        }],
        "count": 1,
    })
    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: ocr_calls.append(kwargs) or {
        "success": True,
        "data": {"text": "Lexa Hermes echter Test"},
    })

    result = hermes_desktop.hermes_desktop_task(
        'Hermes, was siehst du im Fenster Notepad? '
        'Hermes, finde Datei im Fenster Notepad und \u00e4ndere nichts. '
        'Hermes, lies den Bildschirmtext im Fenster Notepad. '
        'Hermes, tippe "Lexa Hermes echter Test 2" im Fenster Notepad. '
        'Ja'
    )
    pending = get_pending_confirmation()

    assert [step["kind"] for step in result["steps"]] == ["observe", "find", "screen_text", "pending_confirmation"]
    assert tree_calls == [{"window": "Notepad", "max_depth": 3, "max_controls": 80}]
    assert find_calls == [("Datei", "", "Notepad")]
    assert ocr_calls == [{"window_title": "Notepad"}]
    assert pending["params"]["kind"] == "type"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_find_uses_ocr_fallback_without_returning_full_screen_text(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", lambda *_args, **_kwargs: {
        "matches": [],
        "count": 0,
    })
    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **_kwargs: {
        "success": True,
        "data": {
            "engine": "rapidocr",
            "text": "very private screen text that should not be copied into the find step",
            "blocks": [{
                "text": "Speichern",
                "bbox": {"left": 20, "top": 20, "right": 100, "bottom": 50},
            }],
        },
    })

    result = hermes_desktop.hermes_desktop_task("/hermes finde den Button Speichern")

    step = result["steps"][0]
    assert step["kind"] == "find"
    assert "OCR-Fallback gefunden" in step["summary"]
    assert step["ocr"]["matched_text"] == "Speichern"
    assert "very private" not in str(step)


def test_hermes_desktop_find_retries_without_button_type_before_ocr(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **_kwargs):
        calls.append((text, control_type))
        if control_type:
            return {"matches": [], "count": 0}
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)
    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("OCR should not be needed")))

    result = hermes_desktop.hermes_desktop_task("/hermes finde den Button Datei im aktuellen Fenster")

    assert result["steps"][0]["kind"] == "find"
    assert result["steps"][0]["control_type"] == ""
    assert result["steps"][0]["requested_control_type"] == "Button"
    assert "Datei" in result["summary"]
    assert calls == [("datei", "Button"), ("datei", "")]


def test_hermes_desktop_observe_uses_explicit_window_hint(monkeypatch):
    calls = []

    def fake_ui_tree(**kwargs):
        calls.append(kwargs)
        return {
            "windows": [{"title": "*Test - Notepad", "controls": [{"name": "Datei", "control_type": "MenuItem"}]}],
            "window_count": 1,
            "control_count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", fake_ui_tree)

    result = hermes_desktop.hermes_desktop_task("/hermes was siehst du im Fenster Notepad?")

    assert result["steps"][0]["kind"] == "observe"
    assert calls == [{"window": "Notepad", "max_depth": 3, "max_controls": 80}]
    assert "Notepad" in result["summary"]


def test_hermes_desktop_find_uses_explicit_window_hint_and_umlaut_safety(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task("/hermes finde Datei im Fenster Notepad und \u00e4ndere nichts.")

    step = result["steps"][0]
    assert step["kind"] == "find"
    assert step["target"] == "Datei"
    assert step["window"] == "Notepad"
    assert calls == [("Datei", "", "Notepad")]
    assert "Notepad" in result["summary"]


def test_hermes_desktop_find_strips_bare_window_hint_from_target(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task("/hermes finde Datei in Notepad und aendere nichts.")

    step = result["steps"][0]
    assert step["kind"] == "find"
    assert step["target"] == "Datei"
    assert step["window"] == "Notepad"
    assert calls == [("Datei", "", "Notepad")]


def test_hermes_desktop_find_ignores_do_not_type_safety_tail(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task(
        "/hermes finde Datei im Fenster Notepad, aber tippe noch nicht."
    )

    assert result["needs_confirmation"] is False
    assert get_pending_confirmation() is None
    assert result["steps"][0]["kind"] == "find"
    assert result["steps"][0]["target"] == "Datei"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [("Datei", "", "Notepad")]


def test_hermes_desktop_find_ignores_do_not_scroll_safety_tail(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task(
        "/hermes finde Datei im Fenster Notepad, aber scrolle noch nicht."
    )

    assert result["needs_confirmation"] is False
    assert get_pending_confirmation() is None
    assert result["steps"][0]["kind"] == "find"
    assert result["steps"][0]["target"] == "Datei"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [("Datei", "", "Notepad")]


def test_hermes_desktop_find_ignores_short_do_not_click_safety_tail(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task(
        "/hermes finde Datei im Fenster Notepad, aber klicke nicht."
    )

    assert result["needs_confirmation"] is False
    assert get_pending_confirmation() is None
    assert result["steps"][0]["kind"] == "find"
    assert result["steps"][0]["target"] == "Datei"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [("Datei", "", "Notepad")]


def test_hermes_desktop_find_ignores_not_before_mutation_safety_tail(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task(
        "/hermes finde Datei im Fenster Notepad, aber nicht tippen."
    )

    assert result["needs_confirmation"] is False
    assert get_pending_confirmation() is None
    assert result["steps"][0]["kind"] == "find"
    assert result["steps"][0]["target"] == "Datei"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [("Datei", "", "Notepad")]


def test_hermes_desktop_find_accepts_window_hint_without_preposition(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task("/hermes finde Datei Fenster Notepad und aendere nichts.")

    step = result["steps"][0]
    assert step["kind"] == "find"
    assert step["target"] == "Datei"
    assert step["window"] == "Notepad"
    assert calls == [("Datei", "", "Notepad")]


def test_hermes_desktop_click_strips_bare_window_hint_from_target(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)

    result = hermes_desktop.hermes_desktop_task("/hermes klicke Datei in Notepad.")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "click"
    assert pending["params"]["text"] == "Datei"
    assert pending["params"]["window"] == "*Test - Notepad"
    assert calls == [("Datei", "Button", "Notepad")]


def test_hermes_desktop_hotkey_accepts_window_hint_without_preposition():
    result = hermes_desktop.hermes_desktop_task("/hermes druecke Enter Fenster Notepad.")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "enter"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_find_omits_invalid_sentinel_coordinates(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", lambda text, control_type="", **_kwargs: {
        "matches": [{
            "name": "Datei",
            "control_type": "MenuItem",
            "window_title": "*Test - Notepad",
            "rect": {"left": -32000, "top": -32000, "right": -31928, "bottom": -31884},
            "rect_valid": False,
            "score": 91,
        }],
        "count": 1,
    })

    result = hermes_desktop.hermes_desktop_task("/hermes finde Datei im Fenster Notepad und aendere nichts.")

    assert "Gefunden" in result["summary"]
    assert "Datei" in result["summary"]
    assert "X=-" not in result["summary"]
    assert "bei X=" not in result["summary"]


def test_hermes_desktop_screen_text_uses_explicit_window_hint(monkeypatch):
    calls = []

    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: calls.append(kwargs) or {
        "success": True,
        "data": {"text": "Lexa Hermes echter Test"},
    })

    result = hermes_desktop.hermes_desktop_task("/hermes lies den Bildschirmtext im Fenster Notepad.")

    assert result["steps"][0]["kind"] == "screen_text"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [{"window_title": "Notepad"}]
    assert "Lexa Hermes echter Test" in result["summary"]


def test_hermes_desktop_screen_text_accepts_plain_text_phrase(monkeypatch):
    calls = []

    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: calls.append(kwargs) or {
        "success": True,
        "data": {"text": "Lexa Plain Text Read"},
    })

    result = hermes_desktop.hermes_desktop_task("/hermes lies den Text im Fenster Notepad.")

    assert result["steps"][0]["kind"] == "screen_text"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [{"window_title": "Notepad"}]
    assert "Lexa Plain Text Read" in result["summary"]


def test_hermes_desktop_screen_text_accepts_polite_plain_text_phrase(monkeypatch):
    calls = []

    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: calls.append(kwargs) or {
        "success": True,
        "data": {"text": "Lexa Polite Text Read"},
    })

    result = hermes_desktop.hermes_desktop_task("/hermes lies bitte den Text im Fenster Notepad.")

    assert result["steps"][0]["kind"] == "screen_text"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [{"window_title": "Notepad"}]
    assert "Lexa Polite Text Read" in result["summary"]


def test_hermes_desktop_screen_text_accepts_show_text_phrase(monkeypatch):
    calls = []

    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: calls.append(kwargs) or {
        "success": True,
        "data": {"text": "Lexa Show Text Read"},
    })

    result = hermes_desktop.hermes_desktop_task("/hermes zeige mir den Text im Fenster Notepad.")

    assert result["steps"][0]["kind"] == "screen_text"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [{"window_title": "Notepad"}]
    assert "Lexa Show Text Read" in result["summary"]


def test_hermes_desktop_screen_text_accepts_read_aloud_from_app_phrase(monkeypatch):
    calls = []

    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: calls.append(kwargs) or {
        "success": True,
        "data": {"text": "Lexa Read Aloud Text"},
    })

    result = hermes_desktop.hermes_desktop_task("/hermes lies mir den Text aus Notepad vor.")

    assert result["steps"][0]["kind"] == "screen_text"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [{"window_title": "Notepad"}]
    assert "Lexa Read Aloud Text" in result["summary"]


def test_hermes_desktop_screen_text_accepts_was_steht_phrase(monkeypatch):
    calls = []

    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: calls.append(kwargs) or {
        "success": True,
        "data": {"text": "Lexa Was Steht Read"},
    })

    result = hermes_desktop.hermes_desktop_task("/hermes was steht im Fenster Notepad?")

    assert result["steps"][0]["kind"] == "screen_text"
    assert result["steps"][0]["window"] == "Notepad"
    assert calls == [{"window_title": "Notepad"}]
    assert "Lexa Was Steht Read" in result["summary"]


def test_hermes_desktop_screen_text_uses_uia_fallback_when_window_ocr_is_empty(monkeypatch):
    ocr_calls = []
    tree_calls = []

    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **kwargs: ocr_calls.append(kwargs) or {
        "success": True,
        "data": {"text": "", "word_count": 0},
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **kwargs: tree_calls.append(kwargs) or {
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

    result = hermes_desktop.hermes_desktop_task("/hermes lies den Bildschirmtext im Fenster Notepad.")

    step = result["steps"][0]
    assert step["kind"] == "screen_text"
    assert step["method"] == "uia_text"
    assert ocr_calls == [{"window_title": "Notepad"}]
    assert tree_calls == [{"window": "Notepad", "max_depth": 3, "max_controls": 120}]
    assert "Lexa Hermes echter Test" in result["summary"]


def test_hermes_desktop_click_retries_without_button_type_before_preparing(monkeypatch):
    calls = []

    def fake_ui_find(text, control_type="", **_kwargs):
        calls.append((text, control_type))
        if control_type:
            return {"matches": [], "count": 0}
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)
    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("OCR should not be needed")))

    result = hermes_desktop.hermes_desktop_task("/hermes klicke auf den Button Datei")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["text"] == "Datei"
    assert pending["params"]["control_type"] == "MenuItem"
    assert pending["params"]["window"] == "Notepad"
    assert calls == [("Datei", "Button"), ("Datei", "")]


def test_hermes_desktop_click_stops_on_ambiguous_targets(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", lambda *_args, **_kwargs: {
        "matches": [
            {
                "name": "Weiter",
                "control_type": "Button",
                "window_title": "Installer A",
                "score": 95,
                "rect": {"left": 10, "top": 20, "right": 110, "bottom": 60},
            },
            {
                "name": "Weiter",
                "control_type": "Button",
                "window_title": "Installer B",
                "score": 92,
                "rect": {"left": 210, "top": 20, "right": 310, "bottom": 60},
            },
        ],
        "count": 2,
    })

    result = hermes_desktop.hermes_desktop_task("/hermes klick auf Weiter")

    assert result["needs_clarification"] is True
    assert result["needs_confirmation"] is False
    assert get_pending_confirmation() is None
    assert "mehrdeutig" in result["summary"]


def test_hermes_desktop_scroll_prepares_and_commit_executes(monkeypatch):
    focus_calls = []

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_focus", lambda window="": focus_calls.append(window) or {
        "focused": True,
        "window_title": window,
    })
    monkeypatch.setattr(hermes_desktop.desktop_control, "desktop_scroll", lambda clicks=-3: {
        "scrolled": True,
        "clicks": clicks,
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "Browser", "controls": [{"name": "Link", "control_type": "Hyperlink"}]}],
        "window_count": 1,
        "control_count": 1,
    })

    result = hermes_desktop.hermes_desktop_task("/hermes scrolle 4 runter")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"] == {"kind": "scroll", "scroll_clicks": -4, "window": "", "verify": True}

    committed = hermes_desktop.hermes_desktop_commit(kind="scroll", scroll_clicks=-4)

    assert committed["kind"] == "scroll"
    assert committed["result"]["clicks"] == -4
    assert focus_calls == []
    assert committed["verification"]["checked"] is True


def test_hermes_desktop_single_key_hotkey_prepares_enter():
    result = hermes_desktop.hermes_desktop_task("/hermes druecke enter")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "enter"


def test_hermes_desktop_single_key_aliases_prepare_hotkeys():
    cases = [
        ("druecke Entf im Fenster Notepad", "delete"),
        ("druecke Leertaste im Fenster Notepad", "space"),
        ("druecke Eingabetaste im Fenster Notepad", "enter"),
        ("druecke Ruecktaste im Fenster Notepad", "backspace"),
    ]

    for instruction, expected_keys in cases:
        clear_pending_confirmation()
        assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

        result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")
        pending = get_pending_confirmation()

        assert result["needs_confirmation"] is True
        assert pending["params"]["kind"] == "hotkey"
        assert pending["params"]["keys"] == expected_keys
        assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_navigation_key_aliases_prepare_hotkeys():
    cases = [
        ("druecke Pfeil rechts im Fenster Notepad", "right"),
        ("druecke Pfeil runter im Fenster Notepad", "down"),
        ("druecke Bild runter im Fenster Notepad", "pagedown"),
        ("druecke Pos1 im Fenster Notepad", "home"),
    ]

    for instruction, expected_keys in cases:
        clear_pending_confirmation()
        assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

        result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")
        pending = get_pending_confirmation()

        assert result["needs_confirmation"] is True
        assert pending["params"]["kind"] == "hotkey"
        assert pending["params"]["keys"] == expected_keys
        assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_strg_hotkey_prepares_normalized_ctrl_a():
    assert hermes_desktop.classify_desktop_instruction("drücke Strg+A im Fenster Notepad") == "hotkey"

    result = hermes_desktop.hermes_desktop_task("/hermes drücke Strg+A im Fenster Notepad")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_select_all_phrase_prepares_ctrl_a():
    assert hermes_desktop.classify_desktop_instruction("markiere alles im Fenster Notepad") == "hotkey"

    result = hermes_desktop.hermes_desktop_task("/hermes markiere alles im Fenster Notepad")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_save_phrase_prepares_ctrl_s():
    assert hermes_desktop.classify_desktop_instruction("speichere im Fenster Notepad") == "hotkey"

    result = hermes_desktop.hermes_desktop_task("/hermes speichere im Fenster Notepad")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+s"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_save_as_phrase_prepares_ctrl_shift_s():
    assert hermes_desktop.classify_desktop_instruction("speichern unter im Fenster Notepad") == "hotkey"

    result = hermes_desktop.hermes_desktop_task("/hermes speichern unter im Fenster Notepad")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+shift+s"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_undo_phrase_prepares_ctrl_z():
    instruction = "mach r\u00fcckg\u00e4ngig im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+z"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_paste_phrase_prepares_ctrl_v_without_breaking_insert():
    instruction = "fuege ein im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+v"
    assert pending["params"]["window"] == "Notepad"

    clear_pending_confirmation()
    result = hermes_desktop.hermes_desktop_task("/hermes druecke Einfuegen im Fenster Notepad")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "insert"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_print_phrase_prepares_ctrl_p_without_breaking_press():
    instruction = "drucke im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+p"
    assert pending["params"]["window"] == "Notepad"

    assert hermes_desktop.classify_desktop_instruction("druecke auf Datei im Fenster Notepad") == "click"
    assert hermes_desktop.classify_desktop_instruction("druecke Enter im Fenster Notepad") == "hotkey"


def test_hermes_desktop_open_file_phrase_prepares_ctrl_o_without_open_app_conflict():
    instruction = "oeffne Datei im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+o"
    assert pending["params"]["window"] == "Notepad"
    assert hermes_desktop.classify_desktop_instruction("oeffne Notepad") == "unknown"


def test_hermes_desktop_new_file_phrase_prepares_ctrl_n_without_chat_conflict():
    instruction = "neue Datei im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+n"
    assert pending["params"]["window"] == "Notepad"
    assert hermes_desktop.classify_desktop_instruction("neuer Chat") == "unknown"


def test_hermes_desktop_new_folder_phrase_prepares_ctrl_shift_n_without_chat_conflict():
    instruction = "neuer Ordner im Fenster Explorer"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+shift+n"
    assert pending["params"]["window"] == "Explorer"
    assert hermes_desktop.classify_desktop_instruction("neuer Chat") == "unknown"
    assert hermes_desktop.classify_desktop_instruction("neuer Tab im Fenster Browser") == "hotkey"


def test_hermes_desktop_new_tab_phrase_prepares_ctrl_t_without_chat_conflict():
    instruction = "oeffne neuen Tab im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+t"
    assert pending["params"]["window"] == "Notepad"
    assert hermes_desktop.classify_desktop_instruction("neuer Chat") == "unknown"


def test_hermes_desktop_tab_switch_phrases_prepare_ctrl_tab_without_tab_key_conflict():
    instruction = "wechsle zum n\u00e4chsten Tab im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+tab"
    assert pending["params"]["window"] == "Browser"

    clear_pending_confirmation()
    previous_instruction = "Tab zur\u00fcck im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(previous_instruction) == "hotkey"

    previous_result = hermes_desktop.hermes_desktop_task(f"/hermes {previous_instruction}")

    previous_pending = get_pending_confirmation()
    assert previous_result["needs_confirmation"] is True
    assert previous_pending["params"]["kind"] == "hotkey"
    assert previous_pending["params"]["keys"] == "ctrl+shift+tab"
    assert previous_pending["params"]["window"] == "Browser"
    assert hermes_desktop.classify_desktop_instruction("druecke Tab im Fenster Browser") == "hotkey"
    assert hermes_desktop._extract_hotkey("druecke Tab im Fenster Browser") == "tab"


def test_hermes_desktop_close_file_phrase_prepares_ctrl_w_without_close_app_conflict():
    instruction = "schlie\u00dfe Datei im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+w"
    assert pending["params"]["window"] == "Notepad"
    assert hermes_desktop.classify_desktop_instruction("schlie\u00dfe Notepad") == "unknown"


def test_hermes_desktop_open_search_phrase_prepares_ctrl_f_without_find_conflict():
    instruction = "oeffne Suche im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+f"
    assert pending["params"]["window"] == "Notepad"
    assert hermes_desktop.classify_desktop_instruction("finde Datei im Fenster Notepad") == "find"
    assert hermes_desktop.classify_desktop_instruction("suche Datei im Fenster Notepad") == "find"


def test_hermes_desktop_address_bar_phrase_prepares_ctrl_l_without_url_conflict():
    instruction = "fokussiere Adressleiste im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+l"
    assert pending["params"]["window"] == "Browser"
    assert hermes_desktop.classify_desktop_instruction("oeffne URL https://example.com") == "unknown"


def test_hermes_desktop_refresh_phrase_prepares_ctrl_r_without_generic_update_conflict():
    instruction = "aktualisiere die Seite im Fenster Notepad"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+r"
    assert pending["params"]["window"] == "Notepad"
    assert hermes_desktop.classify_desktop_instruction("aktualisiere mich") == "unknown"


def test_hermes_desktop_browser_navigation_phrases_prepare_alt_arrows_without_undo_conflict():
    instruction = "gehe zur\u00fcck im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "alt+left"
    assert pending["params"]["window"] == "Browser"

    clear_pending_confirmation()
    forward_instruction = "gehe vorw\u00e4rts im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(forward_instruction) == "hotkey"

    forward_result = hermes_desktop.hermes_desktop_task(f"/hermes {forward_instruction}")

    forward_pending = get_pending_confirmation()
    assert forward_result["needs_confirmation"] is True
    assert forward_pending["params"]["kind"] == "hotkey"
    assert forward_pending["params"]["keys"] == "alt+right"
    assert forward_pending["params"]["window"] == "Browser"
    assert hermes_desktop.classify_desktop_instruction("mach r\u00fcckg\u00e4ngig im Fenster Notepad") == "hotkey"
    assert hermes_desktop._extract_hotkey("mach r\u00fcckg\u00e4ngig im Fenster Notepad") == "ctrl+z"


def test_hermes_desktop_zoom_phrases_prepare_zoom_hotkeys():
    instruction = "zoome rein im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+plus"
    assert pending["params"]["window"] == "Browser"

    clear_pending_confirmation()
    out_instruction = "zoome raus im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(out_instruction) == "hotkey"

    out_result = hermes_desktop.hermes_desktop_task(f"/hermes {out_instruction}")

    out_pending = get_pending_confirmation()
    assert out_result["needs_confirmation"] is True
    assert out_pending["params"]["kind"] == "hotkey"
    assert out_pending["params"]["keys"] == "ctrl+minus"
    assert out_pending["params"]["window"] == "Browser"

    clear_pending_confirmation()
    reset_instruction = "setze Zoom zur\u00fcck im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(reset_instruction) == "hotkey"

    reset_result = hermes_desktop.hermes_desktop_task(f"/hermes {reset_instruction}")

    reset_pending = get_pending_confirmation()
    assert reset_result["needs_confirmation"] is True
    assert reset_pending["params"]["kind"] == "hotkey"
    assert reset_pending["params"]["keys"] == "ctrl+0"
    assert reset_pending["params"]["window"] == "Browser"
    assert hermes_desktop.classify_desktop_instruction("nicht zoomen im Fenster Browser") == "unknown"


def test_hermes_desktop_fullscreen_phrase_prepares_f11_without_negative_conflict():
    instruction = "schalte Vollbild im Fenster Browser um"
    assert hermes_desktop.classify_desktop_instruction(instruction) == "hotkey"

    result = hermes_desktop.hermes_desktop_task(f"/hermes {instruction}")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "f11"
    assert pending["params"]["window"] == "Browser"

    clear_pending_confirmation()
    exit_instruction = "beende Fullscreen im Fenster Browser"
    assert hermes_desktop.classify_desktop_instruction(exit_instruction) == "hotkey"

    exit_result = hermes_desktop.hermes_desktop_task(f"/hermes {exit_instruction}")

    exit_pending = get_pending_confirmation()
    assert exit_result["needs_confirmation"] is True
    assert exit_pending["params"]["kind"] == "hotkey"
    assert exit_pending["params"]["keys"] == "f11"
    assert exit_pending["params"]["window"] == "Browser"
    assert hermes_desktop.classify_desktop_instruction("nicht Vollbild im Fenster Browser") == "unknown"


def test_hermes_desktop_replace_text_expands_to_select_all_then_type():
    message = '/hermes ersetze den Text im Fenster Notepad durch "Hermes Replace OK".'

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "markiere alles im Fenster Notepad",
        'tippe "Hermes Replace OK" im Fenster Notepad',
    ]

    result = hermes_desktop.hermes_desktop_task(message)

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"
    assert pending["queue"]["instructions"] == ['tippe "Hermes Replace OK" im Fenster Notepad']
    assert pending["queue"]["context"] == {"last_window": "Notepad"}


def test_hermes_desktop_clear_text_expands_to_select_all_then_delete():
    message = "/hermes loesche den Text im Fenster Notepad."

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "markiere alles im Fenster Notepad",
        "druecke Entf im Fenster Notepad",
    ]

    result = hermes_desktop.hermes_desktop_task(message)

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"
    assert pending["queue"]["instructions"] == ["druecke Entf im Fenster Notepad"]
    assert pending["queue"]["context"] == {"last_window": "Notepad"}


def test_hermes_desktop_copy_text_expands_to_select_all_then_copy():
    message = "/hermes kopiere alles im Fenster Notepad."

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "markiere alles im Fenster Notepad",
        "druecke Strg+C im Fenster Notepad",
    ]

    result = hermes_desktop.hermes_desktop_task(message)

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"
    assert pending["queue"]["instructions"] == ["druecke Strg+C im Fenster Notepad"]
    assert pending["queue"]["context"] == {"last_window": "Notepad"}


def test_hermes_desktop_cut_text_expands_to_select_all_then_cut():
    message = "/hermes schneide alles im Fenster Notepad aus."

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "markiere alles im Fenster Notepad",
        "druecke Strg+X im Fenster Notepad",
    ]

    result = hermes_desktop.hermes_desktop_task(message)

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"
    assert pending["queue"]["instructions"] == ["druecke Strg+X im Fenster Notepad"]
    assert pending["queue"]["context"] == {"last_window": "Notepad"}


def test_hermes_desktop_negative_replace_clear_copy_or_cut_text_is_not_expanded():
    assert hermes_desktop.split_hermes_desktop_instructions(
        '/hermes ersetze den Text im Fenster Notepad nicht durch "Danger".'
    ) == ['ersetze den Text im Fenster Notepad nicht durch "Danger"']
    assert hermes_desktop.split_hermes_desktop_instructions(
        "/hermes loesche den Text im Fenster Notepad nicht."
    ) == ["loesche den Text im Fenster Notepad nicht"]
    assert hermes_desktop.split_hermes_desktop_instructions(
        "/hermes kopiere alles im Fenster Notepad nicht."
    ) == ["kopiere alles im Fenster Notepad nicht"]
    assert hermes_desktop.split_hermes_desktop_instructions(
        "/hermes schneide alles im Fenster Notepad nicht aus."
    ) == ["schneide alles im Fenster Notepad nicht aus"]


def test_hermes_desktop_spaced_modifier_hotkey_prepares_ctrl_a():
    assert hermes_desktop.classify_desktop_instruction("druecke Strg A im Fenster Notepad") == "hotkey"

    result = hermes_desktop.hermes_desktop_task("/hermes druecke Strg A im Fenster Notepad")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_spaced_modifier_hotkey_supports_control_shift_esc():
    result = hermes_desktop.hermes_desktop_task("/hermes druecke Control Shift Esc")

    pending = get_pending_confirmation()
    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+shift+esc"


def test_hermes_desktop_press_on_target_stays_click():
    assert hermes_desktop.classify_desktop_instruction("druecke auf Datei im Fenster Notepad") == "click"


def test_hermes_window_title_match_accepts_german_editor_alias():
    assert hermes_desktop._window_title_matches_query("Unbenannt - Editor", "Notepad") is True
    assert hermes_desktop._window_title_matches_query("Hermes Verify OK - Editor", "Notepad") is True
    assert hermes_desktop._window_title_matches_query("Hermes Verify OK - Notepad", "Editor") is True


def test_hermes_desktop_commit_hotkey_uses_win32_focus_fallback(monkeypatch):
    focus_calls = []
    fallback_calls = []
    hotkey_calls = []

    def fake_ui_focus(window=""):
        focus_calls.append(window)
        raise ValueError(f"window not found: {window}")

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_focus", fake_ui_focus)
    monkeypatch.setattr(hermes_desktop, "_focus_window_via_win32", lambda window="": fallback_calls.append(window) or {
        "focused": True,
        "window_title": "*Hermes Verify OK - Notepad",
        "engine": "win32",
    })
    monkeypatch.setattr(hermes_desktop.desktop_control, "desktop_hotkey", lambda keys="": hotkey_calls.append(keys) or {
        "pressed": True,
        "keys": ["ctrl", "a"],
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "*Hermes Verify OK - Notepad", "controls": [{"name": "Datei", "control_type": "MenuItem"}]}],
        "window_count": 1,
        "control_count": 1,
    })

    result = hermes_desktop.hermes_desktop_commit(kind="hotkey", keys="ctrl+a", window="Notepad")

    assert result["kind"] == "hotkey"
    assert focus_calls == ["Notepad"]
    assert fallback_calls == ["Notepad"]
    assert hotkey_calls == ["ctrl+a"]
    assert result["focus"]["engine"] == "win32"
    assert result["focus"]["fallback_from"] == "uia"


def test_hermes_desktop_commit_hotkey_opens_notepad_when_missing(monkeypatch):
    launch_calls = []
    pid_focus_calls = []
    tree_calls = []
    hotkey_calls = []

    class FakeProcess:
        pid = 4321

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_focus", lambda window="": (_ for _ in ()).throw(ValueError(f"window not found: {window}")))
    monkeypatch.setattr(hermes_desktop, "_focus_window_via_win32", lambda window="": (_ for _ in ()).throw(ValueError(f"window not found: {window}")))
    monkeypatch.setattr(hermes_desktop.subprocess, "Popen", lambda command: launch_calls.append(command) or FakeProcess())
    monkeypatch.setattr(hermes_desktop, "_focus_window_by_pid", lambda pid, label="": pid_focus_calls.append((pid, label)) or {
        "focused": True,
        "window_title": "Unbenannt - Editor",
        "engine": "win32-pid",
    })
    monkeypatch.setattr(hermes_desktop.desktop_control, "desktop_hotkey", lambda keys="": hotkey_calls.append(keys) or {
        "pressed": True,
        "keys": ["ctrl", "a"],
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **kwargs: tree_calls.append(kwargs) or {
        "windows": [{"title": "Unbenannt - Editor", "controls": [{"name": "Datei", "control_type": "MenuItem"}]}],
        "window_count": 1,
        "control_count": 1,
    })

    result = hermes_desktop.hermes_desktop_commit(kind="hotkey", keys="ctrl+a", window="Notepad")

    assert result["kind"] == "hotkey"
    assert launch_calls == [["notepad.exe"]]
    assert pid_focus_calls == [(4321, "Notepad")]
    assert hotkey_calls == ["ctrl+a"]
    assert tree_calls == [{"window": "Unbenannt - Editor", "max_depth": 2, "max_controls": 40}]
    assert result["focus"]["opened_app"] == "notepad.exe"
    assert result["focus"]["fallback_from"] == "launch"


def test_hermes_desktop_inline_ja_does_not_preapprove_next_action():
    message = (
        "/hermes druecke Strg+A im Fenster Notepad. "
        "Ja Hermes, tippe \"Hermes Hotkey Fix Test\" im Fenster Notepad. Ja"
    )

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "druecke Strg+A im Fenster Notepad",
        'tippe "Hermes Hotkey Fix Test" im Fenster Notepad',
    ]

    result = hermes_desktop.hermes_desktop_task(message)
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert result["inline_preapproval_ignored"] is True
    assert result["deferred_instructions"] == ['tippe "Hermes Hotkey Fix Test" im Fenster Notepad']
    assert "Eingebaute Ja/OK-Zeilen zaehlen nicht als Freigabe" in result["summary"]
    assert "Weitere Desktop-Schritte pausiert" in result["summary"]
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"
    assert pending["queue"]["type"] == "hermes_desktop_instructions"
    assert pending["queue"]["instructions"] == ['tippe "Hermes Hotkey Fix Test" im Fenster Notepad']
    assert pending["queue"]["context"] == {"last_window": "Notepad"}


def test_hermes_desktop_inline_umlaut_confirmation_does_not_preapprove_next_action():
    message = (
        "/hermes druecke Strg+A im Fenster Notepad.\n"
        "ich best\u00e4tige es\n"
        "Hermes, tippe \"Hermes Umlaut Confirm Test\" im Fenster Notepad."
    )

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "druecke Strg+A im Fenster Notepad",
        'tippe "Hermes Umlaut Confirm Test" im Fenster Notepad',
    ]

    result = hermes_desktop.hermes_desktop_task(message)
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert result["inline_preapproval_ignored"] is True
    assert result["deferred_instructions"] == ['tippe "Hermes Umlaut Confirm Test" im Fenster Notepad']
    assert "Eingebaute Ja/OK-Zeilen zaehlen nicht als Freigabe" in result["summary"]
    assert pending["params"]["kind"] == "hotkey"
    assert pending["params"]["keys"] == "ctrl+a"
    assert pending["params"]["window"] == "Notepad"
    assert pending["queue"]["instructions"] == ['tippe "Hermes Umlaut Confirm Test" im Fenster Notepad']


def test_hermes_desktop_inline_umlaut_confirmation_after_period_queues_next_action():
    message = (
        "/hermes druecke Strg+A im Fenster Notepad. "
        "Best\u00e4tige Hermes, tippe \"Hermes Period Confirm Test\" im Fenster Notepad."
    )

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "druecke Strg+A im Fenster Notepad",
        'tippe "Hermes Period Confirm Test" im Fenster Notepad',
    ]

    result = hermes_desktop.hermes_desktop_task(message)
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert result["inline_preapproval_ignored"] is True
    assert result["deferred_instructions"] == ['tippe "Hermes Period Confirm Test" im Fenster Notepad']
    assert pending["params"]["kind"] == "hotkey"
    assert pending["queue"]["instructions"] == ['tippe "Hermes Period Confirm Test" im Fenster Notepad']


def test_hermes_desktop_inline_execute_after_period_queues_next_action():
    message = (
        "/hermes druecke Strg+A im Fenster Notepad. "
        "Ausf\u00fchren Hermes, tippe \"Hermes Execute Prefix Test\" im Fenster Notepad."
    )

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        "druecke Strg+A im Fenster Notepad",
        'tippe "Hermes Execute Prefix Test" im Fenster Notepad',
    ]


def test_hermes_desktop_strips_umlaut_confirmation_prefix_before_next_action():
    message = 'ausf\u00fchren Hermes, tippe "Hermes Prefix Confirm Test" im Fenster Notepad.'

    assert hermes_desktop.split_hermes_desktop_instructions(message) == [
        'tippe "Hermes Prefix Confirm Test" im Fenster Notepad',
    ]
    assert hermes_desktop._message_has_inline_preapproval(message) is True


def test_hermes_desktop_negative_execute_phrase_is_not_preapproval():
    assert hermes_desktop._message_has_inline_preapproval("nicht ausf\u00fchren") is False
    assert hermes_desktop._message_has_inline_cancel("nicht ausf\u00fchren") is True
    assert hermes_desktop.split_hermes_desktop_instructions("nicht ausf\u00fchren") == []


def test_hermes_desktop_negative_execute_phrase_does_not_prepare_mutation():
    result = hermes_desktop.hermes_desktop_task(
        "/hermes druecke Strg+A im Fenster Notepad. nicht ausf\u00fchren."
    )
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is False
    assert result["inline_cancel_detected"] is True
    assert pending is None
    assert result["steps"][0]["kind"] == "cancelled_mutation"
    assert result["steps"][0]["requested_kind"] == "hotkey"
    assert "nicht vorbereitet" in result["summary"]
    assert "Ich habe nichts veraendert" in result["summary"]


def test_hermes_desktop_queue_preserves_context_for_followup_type(monkeypatch):
    find_calls = []

    def fake_ui_find(text, control_type="", **kwargs):
        find_calls.append((text, control_type, kwargs.get("window")))
        return {
            "matches": [{
                "name": "Datei",
                "control_type": "MenuItem",
                "window_title": "*Test - Notepad",
                "rect": {"left": 10, "top": 20, "right": 70, "bottom": 50},
                "score": 91,
            }],
            "count": 1,
        }

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_find", fake_ui_find)
    monkeypatch.setattr(hermes_desktop.ocr, "ocr_screenshot", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("OCR should not be needed")))

    result = hermes_desktop.hermes_desktop_task(
        'Hermes, finde Datei im Fenster Notepad und aendere nichts. '
        'Hermes, klicke darauf. '
        'Hermes, tippe "Queue Context OK".'
    )
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "click"
    assert pending["params"]["text"] == "Datei"
    assert pending["params"]["window"] == "*Test - Notepad"
    assert pending["queue"]["instructions"] == ['tippe "Queue Context OK"']
    assert pending["queue"]["context"] == {
        "last_target": "Datei",
        "last_control_type": "MenuItem",
        "last_window": "*Test - Notepad",
    }
    assert find_calls == [
        ("Datei", "", "Notepad"),
        ("Datei", "MenuItem", "*Test - Notepad"),
    ]

    queued = hermes_desktop.hermes_desktop_task(
        "\n".join(pending["queue"]["instructions"]),
        initial_context=pending["queue"]["context"],
    )
    next_pending = get_pending_confirmation()

    assert queued["needs_confirmation"] is True
    assert next_pending["params"]["kind"] == "type"
    assert next_pending["params"]["window"] == "*Test - Notepad"


def test_hermes_desktop_type_targets_explicit_window_and_commit_focuses(monkeypatch):
    focus_calls = []
    type_calls = []

    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_focus", lambda window="": focus_calls.append(window) or {
        "focused": True,
        "window_title": window,
    })
    interval_calls = []
    monkeypatch.setattr(hermes_desktop.desktop_control, "desktop_type", lambda text="", interval_ms=0, **_kwargs: (type_calls.append(text), interval_calls.append(interval_ms)) and {
        "typed": True,
        "characters": len(text),
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "Notepad", "controls": [{"name": "Text editor hello", "control_type": "Edit"}]}],
        "window_count": 1,
        "control_count": 1,
    })

    result = hermes_desktop.hermes_desktop_task('/hermes tippe "hello" im Fenster Notepad')
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "type"
    assert pending["params"]["window"] == "Notepad"
    assert pending["params"]["typing_interval_ms"] == 8

    committed = hermes_desktop.hermes_desktop_commit(**pending["params"])

    assert committed["kind"] == "type"
    assert focus_calls == ["Notepad"]
    assert type_calls == ["hello"]
    assert interval_calls == [8]
    assert committed["verification"]["checked"] is True
    assert committed["verification"]["status"] == "passed"
    assert committed["verification"]["passed"] is True
    assert committed["verification"]["typed_text_found"] is True


def test_hermes_desktop_type_accepts_german_smart_quotes():
    result = hermes_desktop.hermes_desktop_task("/hermes tippe \u201eHermes Smart Quote Test\u201c im Fenster Notepad")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "type"
    assert pending["params"]["typing_text"] == "Hermes Smart Quote Test"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_type_accepts_curly_smart_quotes():
    result = hermes_desktop.hermes_desktop_task("/hermes tippe \u201cHermes Curly Quote Test\u201d im Fenster Notepad")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "type"
    assert pending["params"]["typing_text"] == "Hermes Curly Quote Test"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_unquoted_type_strips_bare_window_hint():
    result = hermes_desktop.hermes_desktop_task("/hermes tippe hello in Notepad")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "type"
    assert pending["params"]["typing_text"] == "hello"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_unquoted_type_accepts_window_hint_without_preposition():
    result = hermes_desktop.hermes_desktop_task("/hermes tippe hello Fenster Notepad")
    pending = get_pending_confirmation()

    assert result["needs_confirmation"] is True
    assert pending["params"]["kind"] == "type"
    assert pending["params"]["typing_text"] == "hello"
    assert pending["params"]["window"] == "Notepad"


def test_hermes_desktop_type_verification_fails_when_text_is_not_visible(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_focus", lambda window="": {
        "focused": True,
        "window_title": window,
    })
    monkeypatch.setattr(hermes_desktop.desktop_control, "desktop_type", lambda text="", interval_ms=0, **_kwargs: {
        "typed": True,
        "characters": len(text),
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "Notepad", "controls": [{"name": "Other visible text", "control_type": "Document"}]}],
        "window_count": 1,
        "control_count": 1,
    })
    monkeypatch.setattr(hermes_desktop.desktop_engine, "read_screen_text", lambda **_kwargs: {
        "success": True,
        "data": {"text": "Other visible text", "method": "uia_text"},
    })

    committed = hermes_desktop.hermes_desktop_commit(
        kind="type",
        typing_text="Expected Hermes Text",
        window="Notepad",
    )

    assert committed["verification"]["checked"] is True
    assert committed["verification"]["status"] == "failed"
    assert committed["verification"]["passed"] is False
    assert committed["verification"]["typed_text_found"] is False
    assert "nicht sichtbar gefunden" in committed["verification"]["summary"]


def test_hermes_desktop_commit_clicks_and_verifies(monkeypatch):
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_click", lambda **_kwargs: {
        "matched_text": "Pause",
        "target": "Pause",
        "x": 140,
        "y": 70,
        "window_title": "Spotify",
    })
    monkeypatch.setattr(hermes_desktop.ui_automation, "ui_tree", lambda **_kwargs: {
        "windows": [{"title": "Spotify", "controls": [{"name": "Play", "control_type": "Button"}]}],
        "window_count": 1,
        "control_count": 1,
    })

    result = hermes_desktop.hermes_desktop_commit(kind="click", text="Pause", control_type="Button")

    assert result["kind"] == "click"
    assert "Pause" in result["summary"]
    assert result["verification"]["checked"] is True
    assert result["verification"]["status"] == "passed"
    assert "Spotify" in result["verification"]["summary"]


def test_run_agent_routes_multi_step_hermes_desktop_prompt_to_controller(monkeypatch):
    import backend.agent_loop as agent_loop

    captured = {}

    async def fake_execute(action_name, params, **kwargs):
        captured["tool"] = action_name
        captured["params"] = params
        captured["kwargs"] = kwargs
        return {
            "success": True,
            "data": {
                "engine": "lexa-hermes-desktop-controller",
                "summary": "Controller hat beobachtet, gesucht und eine Freigabe vorbereitet.",
                "steps": [],
                "needs_confirmation": True,
            },
        }

    async def collect():
        return [
            event async for event in agent_loop.run_agent(
                "/hermes was siehst du\n/hermes finde den Button pause im aktuellen Fenster, aendere nichts.\nklick darauf ich bestaetige es",
                [],
                worker="hermes",
            )
        ]

    monkeypatch.setattr(agent_loop, "_execute_tool", fake_execute)
    monkeypatch.setattr("backend.ai_engine.chat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM not needed")))

    events = _run(collect())

    assert captured["tool"] == "hermes_desktop_task"
    assert captured["params"]["message"].startswith("/hermes was siehst du")
    assert events[-1]["run"]["steps"][0]["action"] == "hermes_desktop_task"
    assert "Controller hat beobachtet" in events[-1]["run"]["summary"]

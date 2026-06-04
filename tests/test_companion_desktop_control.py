import pytest

from companion import desktop_control


def test_hotkey_parser_accepts_bounded_common_combo():
    assert desktop_control._parse_hotkey_keys("ctrl+l") == ["ctrl", "l"]
    assert desktop_control._parse_hotkey_keys(["alt", "tab"]) == ["alt", "tab"]
    assert desktop_control._parse_hotkey_keys("ctrl+plus") == ["ctrl", "plus"]
    assert desktop_control._parse_hotkey_keys("ctrl+minus") == ["ctrl", "minus"]


def test_hotkey_parser_accepts_german_aliases():
    assert desktop_control._parse_hotkey_keys("strg+a") == ["ctrl", "a"]
    assert desktop_control._parse_hotkey_keys(["umschalt", "entf"]) == ["shift", "delete"]
    assert desktop_control._parse_hotkey_keys("löschen") == ["delete"]
    assert desktop_control._parse_hotkey_keys("Leertaste") == ["space"]
    assert desktop_control._parse_hotkey_keys("Eingabetaste") == ["enter"]
    assert desktop_control._parse_hotkey_keys("Ruecktaste") == ["backspace"]


def test_hotkey_parser_accepts_space_separated_combos():
    assert desktop_control._parse_hotkey_keys("strg a") == ["ctrl", "a"]
    assert desktop_control._parse_hotkey_keys("alt tab") == ["alt", "tab"]
    assert desktop_control._parse_hotkey_keys("Control Shift Esc") == ["ctrl", "shift", "esc"]


def test_hotkey_parser_ignores_natural_connector_words():
    assert desktop_control._parse_hotkey_keys("strg und a") == ["ctrl", "a"]
    assert desktop_control._parse_hotkey_keys("control mit shift esc") == ["ctrl", "shift", "esc"]
    assert desktop_control._parse_hotkey_keys("alt plus tab") == ["alt", "tab"]


def test_hotkey_parser_accepts_navigation_aliases():
    assert desktop_control._parse_hotkey_keys("pfeil rechts") == ["right"]
    assert desktop_control._parse_hotkey_keys("Pfeil runter") == ["down"]
    assert desktop_control._parse_hotkey_keys("Bild runter") == ["pagedown"]
    assert desktop_control._parse_hotkey_keys("Pos1") == ["home"]
    assert desktop_control._parse_hotkey_keys("Einfg") == ["insert"]


def test_hotkey_parser_keeps_spaced_single_key_names_together():
    assert desktop_control._parse_hotkey_keys("page down") == ["pagedown"]
    assert desktop_control._parse_hotkey_keys("page up") == ["pageup"]


def test_hotkey_parser_rejects_unknown_or_too_large_combo():
    with pytest.raises(ValueError, match="unknown"):
        desktop_control._parse_hotkey_keys("ctrl+launch_missiles")

    with pytest.raises(ValueError, match="1-4"):
        desktop_control._parse_hotkey_keys("ctrl+alt+shift+win+l")


def test_clamp_point_keeps_coordinates_inside_screen(monkeypatch):
    monkeypatch.setattr(desktop_control, "_screen_bounds", lambda: (-100, -20, 300, 100))

    assert desktop_control._clamp_point(-200, 200) == (-100, 79)
    assert desktop_control._clamp_point(40, 20) == (40, 20)


def test_desktop_type_rejects_overlong_text_before_sending(monkeypatch):
    sent = []
    monkeypatch.setattr(desktop_control, "_send_input", lambda *inputs: sent.append(inputs))

    with pytest.raises(ValueError, match="text too long"):
        desktop_control.desktop_type("x" * (desktop_control.MAX_TYPE_CHARS + 1))

    assert sent == []


def test_desktop_control_fails_cleanly_when_windows_api_is_unavailable(monkeypatch):
    monkeypatch.setattr(desktop_control, "user32", None)

    with pytest.raises(RuntimeError, match="only available on Windows"):
        desktop_control.desktop_position()


def test_desktop_click_text_uses_ocr_box_center_with_virtual_offset(monkeypatch):
    clicked = {}

    def fake_ocr_screenshot(window_title=None):
        return {
            "success": True,
            "data": {
                "engine": "unit",
                "blocks": [{
                    "text": "Mikrofon",
                    "bbox": {"left": 20, "top": 10, "right": 80, "bottom": 30},
                }],
            },
        }

    monkeypatch.setattr("companion.ocr.ocr_screenshot", fake_ocr_screenshot)
    monkeypatch.setattr(desktop_control, "_screen_bounds", lambda: (-1200, 0, 3120, 1080))

    def fake_click(x=None, y=None, button="left", clicks=1):
        clicked.update({"x": x, "y": y, "button": button, "clicks": clicks})
        return {"clicked": True, "x": x, "y": y, "button": button, "clicks": clicks}

    monkeypatch.setattr(desktop_control, "desktop_click", fake_click)

    result = desktop_control.desktop_click_text("mikro", button="left")

    assert clicked == {"x": -1150, "y": 20, "button": "left", "clicks": 1}
    assert result["matched_text"] == "Mikrofon"

import pytest

from companion import desktop_control


def test_hotkey_parser_accepts_bounded_common_combo():
    assert desktop_control._parse_hotkey_keys("ctrl+l") == ["ctrl", "l"]
    assert desktop_control._parse_hotkey_keys(["alt", "tab"]) == ["alt", "tab"]


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

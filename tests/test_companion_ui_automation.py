import pytest

from companion import ui_automation


@pytest.fixture(autouse=True)
def reset_ui_context():
    ui_automation._LAST_UI_CONTEXT.update({
        "window_title": "",
        "target_text": "",
        "target_control_type": "",
        "updated_at": 0.0,
        "target_updated_at": 0.0,
    })


class FakeRect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeInfo:
    def __init__(self, name="", control_type="Text", automation_id=""):
        self.name = name
        self.control_type = control_type
        self.automation_id = automation_id


class FakeControl:
    def __init__(
        self,
        name,
        control_type="Text",
        rect=None,
        *,
        automation_id="",
        handle=0,
        enabled=True,
        visible=True,
        children=None,
    ):
        self._name = name
        self._control_type = control_type
        self._rect = rect or FakeRect(0, 0, 10, 10)
        self.element_info = FakeInfo(name, control_type, automation_id)
        self.handle = handle
        self._enabled = enabled
        self._visible = visible
        self._children = children or []

    def window_text(self):
        return self._name

    def friendly_class_name(self):
        return self._control_type

    def rectangle(self):
        return self._rect

    def is_enabled(self):
        return self._enabled

    def is_visible(self):
        return self._visible

    def descendants(self, depth=3):
        return list(self._children)


class FakeWindowSpec:
    def __init__(self, window):
        self._window = window

    def wrapper_object(self):
        return self._window


class FakeDesktop:
    def __init__(self, windows):
        self._windows = list(windows)

    def window(self, **kwargs):
        handle = kwargs.get("handle")
        for window in self._windows:
            if handle and window.handle == handle:
                return FakeWindowSpec(window)
        return FakeWindowSpec(self._windows[0])

    def windows(self, **_kwargs):
        return list(self._windows)


def _install_fake_desktop(monkeypatch, children, *, title="Spotify", extra_windows=None):
    window = FakeControl(
        title,
        "Window",
        FakeRect(0, 0, 1000, 700),
        handle=123,
        children=children,
    )
    windows = [window] + list(extra_windows or [])
    monkeypatch.setattr(ui_automation, "_require_desktop", lambda: FakeDesktop(windows))
    monkeypatch.setattr(ui_automation, "_foreground_hwnd", lambda: 123)
    return window


def test_ui_find_prefers_actionable_control_over_static_text(monkeypatch):
    _install_fake_desktop(monkeypatch, [
        FakeControl("Speichern", "Text", FakeRect(10, 10, 110, 40)),
        FakeControl("Speichern", "Button", FakeRect(200, 100, 300, 140)),
    ])

    result = ui_automation.ui_find("speichern")

    assert result["count"] == 2
    assert result["matches"][0]["control_type"] == "Button"
    assert result["matches"][0]["name"] == "Speichern"


def test_ui_click_uses_control_rectangle_center(monkeypatch):
    _install_fake_desktop(monkeypatch, [
        FakeControl("Sprachaufnahme starten", "Button", FakeRect(100, 50, 300, 90)),
    ])
    clicked = {}

    def fake_desktop_click(x=None, y=None, button="left", clicks=1):
        clicked.update({"x": x, "y": y, "button": button, "clicks": clicks})
        return {"clicked": True, "x": x, "y": y, "button": button, "clicks": clicks}

    monkeypatch.setattr("companion.desktop_control.desktop_click", fake_desktop_click)

    result = ui_automation.ui_click("sprachaufnahme starten")

    assert clicked == {"x": 200, "y": 70, "button": "left", "clicks": 1}
    assert result["method"] == "ui-automation"
    assert result["matched_text"] == "Sprachaufnahme starten"


def test_ui_click_prefers_fuzzy_actionable_button_over_long_text_blob(monkeypatch):
    long_chat_text = "klicke auf pasue " + ("irgendein Chatverlauf " * 20)
    _install_fake_desktop(monkeypatch, [
        FakeControl(long_chat_text, "Text", FakeRect(10, 10, 900, 300)),
        FakeControl("Pause", "Button", FakeRect(400, 100, 500, 140)),
    ])
    clicked = {}

    def fake_desktop_click(x=None, y=None, button="left", clicks=1):
        clicked.update({"x": x, "y": y, "button": button, "clicks": clicks})
        return {"clicked": True, "x": x, "y": y, "button": button, "clicks": clicks}

    monkeypatch.setattr("companion.desktop_control.desktop_click", fake_desktop_click)

    result = ui_automation.ui_click("pasue")

    assert clicked == {"x": 450, "y": 120, "button": "left", "clicks": 1}
    assert result["matched_text"] == "Pause"


def test_ui_click_can_fall_back_to_ocr(monkeypatch):
    _install_fake_desktop(monkeypatch, [])

    def fake_click_text(text="", button="left", occurrence=1, window=""):
        return {"clicked": True, "target": text, "matched_text": text, "x": 10, "y": 20}

    monkeypatch.setattr("companion.desktop_control.desktop_click_text", fake_click_text)

    result = ui_automation.ui_click("Mikrofon", fallback_ocr=True)

    assert result["method"] == "ocr-fallback"
    assert result["target"] == "Mikrofon"


def test_ui_find_ignores_lexa_and_taskbar_by_default(monkeypatch):
    taskbar = FakeControl(
        "Taskleiste",
        "Pane",
        FakeRect(0, 1032, 1920, 1080),
        handle=456,
        children=[FakeControl("Ausgeblendete Symbole einblenden", "Button", FakeRect(1700, 1035, 1820, 1080))],
    )
    lexa = FakeControl(
        "Lexa AI",
        "Window",
        FakeRect(0, 0, 1000, 700),
        handle=123,
        children=[FakeControl("Schritt bearbeiten: pause", "Button", FakeRect(600, 330, 820, 380))],
    )
    spotify = FakeControl(
        "Spotify",
        "Window",
        FakeRect(100, 100, 900, 700),
        handle=789,
        children=[FakeControl("Pause", "Button", FakeRect(400, 300, 500, 360))],
    )
    monkeypatch.setattr(ui_automation, "_require_desktop", lambda: FakeDesktop([lexa, taskbar, spotify]))
    monkeypatch.setattr(ui_automation, "_foreground_hwnd", lambda: 123)

    result = ui_automation.ui_find("pause", control_type="Button")

    assert result["count"] == 1
    assert result["matches"][0]["window_title"] == "Spotify"
    assert result["matches"][0]["name"] == "Pause"


def test_ui_tree_falls_back_from_lexa_to_real_app_window(monkeypatch):
    lexa = FakeControl(
        "Lexa",
        "Window",
        FakeRect(0, 0, 1000, 700),
        handle=123,
        children=[FakeControl("Schritt bearbeiten: pause", "Button", FakeRect(600, 330, 820, 380))],
    )
    spotify = FakeControl(
        "Spotify",
        "Window",
        FakeRect(100, 100, 900, 700),
        handle=789,
        children=[FakeControl("Play", "Button", FakeRect(400, 300, 500, 360))],
    )
    monkeypatch.setattr(ui_automation, "_require_desktop", lambda: FakeDesktop([lexa, spotify]))
    monkeypatch.setattr(ui_automation, "_foreground_hwnd", lambda: 123)

    result = ui_automation.ui_tree(max_depth=2, max_controls=10)

    assert result["window_count"] == 1
    assert result["windows"][0]["title"] == "Spotify"
    assert result["windows"][0]["controls"][0]["name"] == "Spotify"


def test_ui_click_deictic_target_uses_recent_found_control(monkeypatch):
    _install_fake_desktop(monkeypatch, [
        FakeControl("Pause", "Button", FakeRect(400, 100, 500, 140)),
    ])
    ui_automation.ui_find("pause", control_type="Button")
    clicked = {}

    def fake_desktop_click(x=None, y=None, button="left", clicks=1):
        clicked.update({"x": x, "y": y, "button": button, "clicks": clicks})
        return {"clicked": True, "x": x, "y": y, "button": button, "clicks": clicks}

    monkeypatch.setattr("companion.desktop_control.desktop_click", fake_desktop_click)

    result = ui_automation.ui_click("darauf")

    assert result["target"] == "Pause"
    assert clicked["x"] == 450
    assert clicked["y"] == 120

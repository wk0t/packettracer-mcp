"""Packet Tracer-only window boundaries and literal keyboard behavior."""
from pathlib import Path
import ntpath
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows_ui import PacketTracerUI, key_chord, literal_keys


EXE = r"C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe"
INSTALLATION = ntpath.dirname(ntpath.dirname(EXE))


class DesktopModel:
    def __init__(self):
        self.paths = {1: EXE, 2: r"C:\Windows\notepad.exe", 3: EXE.replace("9.0.1", "9.0.0")}
        self.focus = 1
        self.hit = 1
        self.actions = []
        self.alive = {1, 2, 3}

    def windows(self): return list(self.alive)
    def exists(self, hwnd): return hwnd in self.alive
    def process_path(self, hwnd): return self.paths[hwnd]
    def visible(self, hwnd): return True
    def enabled(self, hwnd): return True
    def title(self, hwnd): return "Cisco Packet Tracer" if hwnd == 1 else "Other"
    def class_name(self, hwnd): return "Qt5152QWindowIcon"
    def rect(self, hwnd): return (100, 200, 900, 800)
    def foreground(self): return self.focus
    def set_focus(self, hwnd): self.focus = hwnd
    def window_at(self, point): return self.hit
    def is_child(self, parent, child): return parent == child
    def click(self, point): self.actions.append(("click", point))
    def extended_click(self, point, button, count): self.actions.append(("click",point,button,count))
    def drag(self, start, end): self.actions.append(("drag",start,end))
    def scroll(self, point, ticks): self.actions.append(("scroll",point,ticks))
    def type_keys(self, text): self.actions.append(("keys", text))
    def inspect(self, hwnd, limit): return {"backend": "test", "nodes": [{"text": "CLI"}]}
    def screenshot(self, hwnd): return b"\x89PNG\r\n\x1a\nexample"


@pytest.fixture
def ui():
    return PacketTracerUI(INSTALLATION, api=DesktopModel())


def test_inventory_only_returns_exact_installed_executable(ui):
    assert [item["window_id"] for item in ui.list_windows()["windows"]] == [1]


@pytest.mark.parametrize("hwnd", [0, -1, True, 1.5, "1", 2, 3, 999])
def test_every_operation_rejects_invalid_or_foreign_windows(ui, hwnd):
    for operation in (lambda:ui.inspect(hwnd), lambda:ui.screenshot(hwnd),
                      lambda:ui.click(hwnd, 2, 2), lambda:ui.type_text(hwnd, "x"),
                      lambda:ui.press_keys(hwnd, "ENTER")):
        with pytest.raises((ValueError, PermissionError)):
            operation()
    assert not ui.api.actions


@pytest.mark.parametrize("point", [(-1, 0), (800, 0), (0, 600), (True, 0), (2.5, 4)])
def test_click_coordinates_are_window_relative_and_bounded(ui, point):
    with pytest.raises(ValueError):
        ui.click(1, *point)
    assert not ui.api.actions


def test_click_targets_screen_position_of_same_window(ui):
    result = ui.click(1, 40, 50)
    assert ui.api.actions == [("click", (140, 250))]
    assert result["window_id"] == 1
    assert result["inspection"]["nodes"][0]["text"] == "CLI"


def test_click_cannot_hit_occluding_window(ui):
    ui.api.hit = 2
    with pytest.raises(PermissionError, match="obscured"):
        ui.click(1, 10, 10)
    assert not ui.api.actions


def test_typing_is_literal_including_send_keys_metacharacters(ui):
    ui.type_text(1, "A+B^{C}%~()")
    assert ui.api.actions == [("keys", "A{+}B{^}{{}C{}}{%}{~}{(}{)}")]
    assert literal_keys("hello world") == "hello world"


@pytest.mark.parametrize("text", ["a\nb", "a\rb", "\x00", "\t", "x"*16001])
def test_text_does_not_inject_control_keys(ui, text):
    with pytest.raises(ValueError): ui.type_text(1, text)
    assert not ui.api.actions


def test_named_key_chords_have_no_script_syntax(ui):
    assert key_chord("CTRL+SHIFT+C") == "^+c"
    assert key_chord("Control_L+o") == "^o"
    assert key_chord("ENTER") == "{ENTER}"
    ui.press_keys(1, "ALT+F4")
    assert ui.api.actions == [("keys", "%{F4}")]


@pytest.mark.parametrize("keys", ["{PAUSE 999}", "CTRL+{ENTER 999999}", "a\nb", "", "CTRL+CTRL+A", "CTRL+ALT+SHIFT+WIN+A"])
def test_key_script_and_repetitions_are_rejected(ui, keys):
    with pytest.raises(ValueError): ui.press_keys(1, keys)
    assert not ui.api.actions


def test_no_typing_when_foreground_focus_was_not_obtained(ui):
    ui.api.set_focus = lambda hwnd:None
    ui.api.focus = 2
    with pytest.raises(PermissionError): ui.type_text(1, "hostname R1")
    assert not ui.api.actions


def test_screenshot_returns_png_bytes(ui):
    assert ui.screenshot(1).startswith(b"\x89PNG\r\n\x1a\n")


def test_inspection_limit_is_bounded(ui):
    for count in (0, 301, True, 1.5):
        with pytest.raises(ValueError): ui.inspect(1, count)


def test_right_double_click_drag_and_scroll_target_cisco(ui):
    ui.click(1, 20, 30, mouse_button="right", click_count=2)
    ui.drag(1, 20, 30, 60, 70)
    ui.scroll(1, 40, 50, -3)
    assert ui.api.actions == [("click",(120,230),"right",2),("drag",(120,230),(160,270)),("scroll",(140,250),-3)]


@pytest.mark.parametrize("ticks", [0,101,-101,True,1.5])
def test_scroll_rejects_invalid_distances(ui,ticks):
    with pytest.raises(ValueError): ui.scroll(1,20,30,ticks)
    assert not ui.api.actions


def test_drag_rejects_outside_endpoint_and_foreign_window(ui):
    with pytest.raises(ValueError): ui.drag(1,20,30,800,20)
    with pytest.raises(PermissionError): ui.drag(2,20,30,50,60)
    assert not ui.api.actions

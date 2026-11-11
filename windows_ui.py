"""Windows UI fallback restricted to this Packet Tracer installation.

The native MCP API remains preferable. These controls cover dialogs and tools
that Cisco does not expose through IPC. Window handles are revalidated for every
call; no shell, arbitrary process, desktop-wide input or clipboard API is exposed.
"""
from __future__ import annotations

from io import BytesIO
import ntpath
import os
import re


DEFAULT_HOME = ntpath.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Cisco Packet Tracer 9.0.1")


def literal_keys(text: str) -> str:
    if not isinstance(text, str) or len(text) > 16000 or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError("Text is limited to 16000 characters without control keys; use press_keys for Enter/Tab.")
    return "".join("{" + c + "}" if c in "+^%~(){}" else c for c in text)


def key_chord(keys: str) -> str:
    """Translate one named chord, never accepting the send_keys scripting language."""
    if not isinstance(keys, str) or not keys or len(keys) > 80:
        raise ValueError("Provide a single key or key combination, such as CTRL+O, SHIFT+TAB or ENTER.")
    pieces = [p.strip().upper() for p in keys.split("+")]
    modifiers = {"CTRL":"^", "CONTROL":"^", "CONTROL_L":"^", "SHIFT":"+", "SHIFT_L":"+", "ALT":"%", "ALT_L":"%"}
    seen = set()
    prefix = ""
    for part in pieces[:-1]:
        value = modifiers.get(part)
        if value is None or value in seen:
            raise ValueError("Invalid or repeated modifier; use CTRL, ALT and SHIFT.")
        seen.add(value)
        prefix += value
    key = pieces[-1]
    names = {"ENTER":"ENTER", "RETURN":"ENTER", "TAB":"TAB", "ESC":"ESC", "ESCAPE":"ESC",
             "SPACE":"SPACE", "BACKSPACE":"BACKSPACE", "DELETE":"DELETE", "DEL":"DELETE",
             "INSERT":"INSERT", "HOME":"HOME", "END":"END", "PAGEUP":"PGUP", "PAGEDOWN":"PGDN",
             "PGUP":"PGUP", "PGDN":"PGDN", "LEFT":"LEFT", "RIGHT":"RIGHT", "UP":"UP", "DOWN":"DOWN"}
    if key in names:
        return prefix + "{" + names[key] + "}"
    if re.fullmatch(r"F(?:[1-9]|1[0-2])", key):
        return prefix + "{" + key + "}"
    if re.fullmatch(r"[A-Z0-9]", key):
        return prefix + key.lower()
    raise ValueError("Unsupported key; scripting syntax and repetitions are not accepted.")


class PacketTracerUI:
    def __init__(self, packet_tracer_home=DEFAULT_HOME, *, api=None):
        self.expected_executable = ntpath.normcase(ntpath.abspath(ntpath.join(str(packet_tracer_home), "bin", "PacketTracer.exe")))
        self._api = api

    @property
    def api(self):
        if self._api is None:
            self._api = _NativeApi()
        return self._api

    def _target(self, window_id):
        if type(window_id) is not int or not 0 < window_id <= 2**64-1:
            raise ValueError("window_id must be an integer handle returned by list_windows.")
        if not self.api.exists(window_id):
            raise ValueError("The window no longer exists; call list_windows again.")
        executable = ntpath.normcase(ntpath.abspath(self.api.process_path(window_id)))
        if executable != self.expected_executable:
            raise PermissionError("This window does not belong to the authorized Cisco Packet Tracer installation.")
        return window_id

    def _summary(self, hwnd):
        rect = self.api.rect(hwnd)
        return {"window_id":hwnd, "title":self.api.title(hwnd), "class":self.api.class_name(hwnd),
                "width":rect[2]-rect[0], "height":rect[3]-rect[1], "enabled":self.api.enabled(hwnd)}

    def list_windows(self):
        windows = []
        for hwnd in self.api.windows():
            try:
                self._target(hwnd)
                if self.api.visible(hwnd):
                    windows.append(self._summary(hwnd))
            except (ValueError, PermissionError, OSError):
                # Expected for foreign processes, protected windows and handles
                # destroyed between enumeration and ownership verification.
                continue
        return {"windows":windows, "installation":self.expected_executable}

    def inspect(self, window_id, max_nodes=150):
        if type(max_nodes) is not int or not 1 <= max_nodes <= 300:
            raise ValueError("max_nodes must be an integer between 1 and 300.")
        hwnd = self._target(window_id)
        if not self.api.visible(hwnd):
            raise ValueError("The window is hidden; select a visible window.")
        return {**self._summary(hwnd), "inspection":self.api.inspect(hwnd, max_nodes)}

    def screenshot(self, window_id):
        hwnd = self._target(window_id)
        if not self.api.visible(hwnd):
            raise ValueError("The window is hidden; no screenshot was captured.")
        image = self.api.screenshot(hwnd)
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("The Windows capture did not produce a PNG.")
        return image

    def _focus(self, window_id):
        hwnd = self._target(window_id)
        if not self.api.visible(hwnd) or not self.api.enabled(hwnd):
            raise ValueError("The window is hidden or blocked by a dialog; select that dialog in list_windows.")
        self.api.set_focus(hwnd)
        foreground = self.api.foreground()
        if foreground != hwnd and not self.api.is_child(hwnd, foreground):
            raise PermissionError("Unable to focus this window; no input was sent.")
        self._target(foreground)
        return hwnd

    def _after(self, hwnd):
        if not self.api.exists(hwnd):
            return {"window_id":hwnd, "closed":True, **self.list_windows()}
        return {**self.inspect(hwnd, 100), "windows":self.list_windows()["windows"]}

    def click(self, window_id, x, y, mouse_button="left", click_count=1):
        if mouse_button not in {"left", "right", "middle"} or type(click_count) is not int or click_count not in {1,2}:
            raise ValueError("A left/right/middle button and click_count of 1 or 2 are required.")
        hwnd = self._target(window_id)
        left, top, right, bottom = self.api.rect(hwnd)
        if type(x) is not int or type(y) is not int or not (0 <= x < right-left and 0 <= y < bottom-top):
            raise ValueError("x and y must be integer coordinates inside the window.")
        self._focus(hwnd)
        left, top, right, bottom = self.api.rect(hwnd)
        if not (0 <= x < right-left and 0 <= y < bottom-top):
            raise ValueError("The window geometry changed; inspect the window again.")
        point = (left+x, top+y)
        hit = self.api.window_at(point)
        if hit != hwnd and not self.api.is_child(hwnd, hit):
            raise PermissionError("The point is obscured by another window; select the correct window.")
        self._target(hit)
        if mouse_button == "left" and click_count == 1:
            self.api.click(point)
        else:
            self.api.extended_click(point, mouse_button, click_count)
        return self._after(hwnd)

    def _point(self, hwnd, x, y):
        left, top, right, bottom = self.api.rect(hwnd)
        if type(x) is not int or type(y) is not int or not (0 <= x < right-left and 0 <= y < bottom-top):
            raise ValueError("Coordinates are outside the Cisco window.")
        point = (left+x, top+y)
        hit = self.api.window_at(point)
        if hit != hwnd and not self.api.is_child(hwnd, hit):
            raise PermissionError("The point is obscured by another window.")
        self._target(hit)
        return point

    def drag(self, window_id, from_x, from_y, to_x, to_y):
        hwnd = self._focus(window_id)
        start = self._point(hwnd, from_x, from_y)
        end = self._point(hwnd, to_x, to_y)
        self.api.drag(start, end)
        return self._after(hwnd)

    def scroll(self, window_id, x, y, ticks):
        if type(ticks) is not int or not -100 <= ticks <= 100 or ticks == 0:
            raise ValueError("ticks must be a nonzero integer between -100 and 100.")
        hwnd = self._focus(window_id)
        self.api.scroll(self._point(hwnd, x, y), ticks)
        return self._after(hwnd)

    def type_text(self, window_id, text):
        keys = literal_keys(text)
        hwnd = self._focus(window_id)
        self.api.type_keys(keys)
        return self._after(hwnd)

    def press_keys(self, window_id, keys):
        chord = key_chord(keys)
        hwnd = self._focus(window_id)
        self.api.type_keys(chord)
        return self._after(hwnd)


class _NativeApi:
    def __init__(self):
        import ctypes
        import win32api
        import win32gui
        import win32process
        from pywinauto import Desktop, keyboard, mouse
        self.ctypes = ctypes
        self.win32api, self.gui, self.process = win32api, win32gui, win32process
        self.Desktop, self.keyboard, self.mouse = Desktop, keyboard, mouse

    def windows(self):
        result = []
        self.gui.EnumWindows(lambda hwnd, unused:result.append(hwnd), None)
        return result

    def exists(self, hwnd): return bool(self.gui.IsWindow(hwnd))
    def visible(self, hwnd): return bool(self.gui.IsWindowVisible(hwnd))
    def enabled(self, hwnd): return bool(self.gui.IsWindowEnabled(hwnd))
    def title(self, hwnd): return self.gui.GetWindowText(hwnd)
    def class_name(self, hwnd): return self.gui.GetClassName(hwnd)
    def rect(self, hwnd): return self.gui.GetWindowRect(hwnd)
    def foreground(self): return self.gui.GetForegroundWindow()
    def is_child(self, parent, child): return bool(self.gui.IsChild(parent, child))
    def window_at(self, point): return self.gui.WindowFromPoint(point)
    def click(self, point): self.mouse.click(button="left", coords=point)
    def extended_click(self, point, button, count):
        operation = self.mouse.double_click if count == 2 else self.mouse.click
        operation(button=button, coords=point)
    def drag(self, start, end):
        self.mouse.press(button="left", coords=start)
        try:
            self.mouse.move(coords=end)
        finally:
            self.mouse.release(button="left", coords=end)
    def scroll(self, point, ticks): self.mouse.scroll(coords=point, wheel_dist=ticks)
    def type_keys(self, keys): self.keyboard.send_keys(keys, pause=0.001, with_spaces=True, vk_packet=True)

    def process_path(self, hwnd):
        pid = self.process.GetWindowThreadProcessId(hwnd)[1]
        try:
            handle = self.win32api.OpenProcess(0x0410, False, pid)
            try:
                return self.process.GetModuleFileNameEx(handle, 0)
            finally:
                handle.Close()
        except Exception as error:
            raise PermissionError("Unable to verify the window owner.") from error

    def _responding(self, hwnd):
        try:
            self.gui.SendMessageTimeout(hwnd, 0, 0, 0, 0x0001 | 0x0002, 1500)
        except Exception as error:
            raise RuntimeError("Packet Tracer is not responding; no input was sent.") from error

    def set_focus(self, hwnd):
        self._responding(hwnd)
        self.Desktop(backend="win32").window(handle=hwnd).set_focus()

    def inspect(self, hwnd, limit):
        self._responding(hwnd)
        failures = []
        for backend in ("uia", "win32"):
            try:
                wrapper = self.Desktop(backend=backend).window(handle=hwnd).wrapper_object()
                controls = [wrapper] + wrapper.descendants(depth=7)
                nodes = []
                left, top, _, _ = self.rect(hwnd)
                for item in controls[:limit]:
                    info = item.element_info
                    rect = info.rectangle
                    nodes.append({"index":len(nodes), "name":str(info.name)[:2000],
                                  "control_type":str(getattr(info, "control_type", "")),
                                  "class_name":str(info.class_name),
                                  "automation_id":str(getattr(info, "automation_id", "")),
                                  "enabled":bool(info.enabled), "visible":bool(info.visible),
                                  "rect":[rect.left-left, rect.top-top, rect.right-left, rect.bottom-top]})
                return {"backend":backend, "nodes":nodes, "truncated":len(controls)>limit, "warnings":failures}
            except Exception as error:
                failures.append(f"{backend}: {type(error).__name__}: {error}")
        raise RuntimeError("Unable to inspect the interface: " + "; ".join(failures))

    def screenshot(self, hwnd):
        """Render only the target window, never capture an arbitrary desktop area."""
        import win32ui
        from PIL import Image
        self._responding(hwnd)
        left, top, right, bottom = self.rect(hwnd)
        width, height = right-left, bottom-top
        if not (0 < width <= 16384 and 0 < height <= 16384 and width*height <= 40000000):
            raise ValueError("Invalid Windows capture dimensions.")
        window_dc = self.gui.GetWindowDC(hwnd)
        source_dc = win32ui.CreateDCFromHandle(window_dc)
        memory_dc = source_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        old_bitmap = None
        try:
            bitmap.CreateCompatibleBitmap(source_dc, width, height)
            old_bitmap = memory_dc.SelectObject(bitmap)
            # PrintWindow renders the chosen HWND, including nonclient borders,
            # rather than accidentally capturing another program in front of it.
            user32 = self.ctypes.windll.user32
            user32.PrintWindow.argtypes = [self.ctypes.c_void_p, self.ctypes.c_void_p, self.ctypes.c_uint]
            user32.PrintWindow.restype = self.ctypes.c_int
            ok = user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 2)
            if not ok:
                raise RuntimeError("Windows could not render this window; use screenshot(view='logical') for the topology.")
            image = Image.frombuffer("RGB", (width, height), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
            if all(lo == hi == 0 for lo, hi in image.getextrema()):
                raise RuntimeError("The capture is black; restore the window or use the logical IPC screenshot.")
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
        finally:
            if old_bitmap is not None:
                memory_dc.SelectObject(old_bitmap)
            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            self.gui.ReleaseDC(hwnd, window_dc)
            self.gui.DeleteObject(bitmap.GetHandle())

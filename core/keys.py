"""Keypresses for the game: SendInput with scan codes (Windows, standard library only).

Racing games read the keyboard through DirectInput / raw input, which sees scan codes, not
virtual keys, so every key is sent with KEYEVENTF_SCANCODE. Input goes to the foreground
window: before a key the game window is brought to the front if it is not there already.

On other systems (development with the demo game) the module loads, but `available` is False
and nothing is sent.
"""
import sys
import time

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# name: (scan code, extended)
SCAN = {
    "LCtrl": (0x1D, False), "RCtrl": (0x1D, True),
    "LShift": (0x2A, False), "RShift": (0x36, False),
    "LAlt": (0x38, False), "RAlt": (0x38, True),
    "Esc": (0x01, False), "Tab": (0x0F, False), "Backspace": (0x0E, False),
    "Space": (0x39, False), "Enter": (0x1C, False),
    "Home": (0x47, True), "End": (0x4F, True), "PageUp": (0x49, True), "PageDown": (0x51, True),
    "Insert": (0x52, True), "Delete": (0x53, True),
    "Up": (0x48, True), "Down": (0x50, True), "Left": (0x4B, True), "Right": (0x4D, True),
    "Minus": (0x0C, False), "Equals": (0x0D, False), "LBracket": (0x1A, False), "RBracket": (0x1B, False),
    "Semicolon": (0x27, False), "Apostrophe": (0x28, False), "Grave": (0x29, False), "Backslash": (0x2B, False),
    "Comma": (0x33, False), "Period": (0x34, False), "Slash": (0x35, False),
    "Num0": (0x52, False), "Num1": (0x4F, False), "Num2": (0x50, False), "Num3": (0x51, False),
    "Num4": (0x4B, False), "Num5": (0x4C, False), "Num6": (0x4D, False), "Num7": (0x47, False),
    "Num8": (0x48, False), "Num9": (0x49, False), "NumPlus": (0x4E, False), "NumMinus": (0x4A, False),
    "NumMultiply": (0x37, False), "NumDivide": (0x35, True), "NumEnter": (0x1C, True), "NumDecimal": (0x53, False),
}
for _name, _code in zip("QWERTYUIOP", range(0x10, 0x1A)):
    SCAN[_name] = (_code, False)
for _name, _code in zip("ASDFGHJKL", range(0x1E, 0x27)):
    SCAN[_name] = (_code, False)
for _name, _code in zip("ZXCVBNM", range(0x2C, 0x33)):
    SCAN[_name] = (_code, False)
for _name, _code in zip("1234567890", range(0x02, 0x0C)):
    SCAN[_name] = (_code, False)
for _number, _code in zip(range(1, 13), list(range(0x3B, 0x45)) + [0x57, 0x58]):
    SCAN[f"F{_number}"] = (_code, False)


def parse(combo: str) -> list[str]:
    """'LCtrl+T' -> ['LCtrl', 'T']; raises ValueError for an unknown key name."""
    names = [part.strip() for part in combo.split("+") if part.strip()]
    if not names:
        raise ValueError("empty key")
    for name in names:
        if name not in SCAN:
            raise ValueError(f"unknown key: {name}")
    return names


available = sys.platform == "win32"

if available:
    import ctypes
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def send_key(name: str, up: bool) -> None:
        code, extended = SCAN[name]
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
        event = INPUT(type=INPUT_KEYBOARD)
        event.ki = KEYBDINPUT(0, code, flags, 0, 0)
        user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))

    def window_title(hwnd) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buffer, 256)
        return buffer.value

    def process_name(hwnd) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(520)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value.replace("/", "\\").rsplit("\\", 1)[-1]
            return ""
        finally:
            kernel32.CloseHandle(handle)

    def matches(hwnd, process: str, title: str) -> bool:
        if not hwnd:
            return False
        if process and process_name(hwnd).lower() == process.lower():
            return True
        return bool(title) and title.lower() in window_title(hwnd).lower()

    def find_window(process: str, title: str):
        found = []

        def check(hwnd, _):
            if user32.IsWindowVisible(hwnd) and window_title(hwnd) and matches(hwnd, process, title):
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(ENUM_PROC(check), 0)
        return found[0] if found else None

    def focus(process: str, title: str) -> bool:
        """Make sure the game window is in front. True if it is (or no window is configured)."""
        if not process and not title:
            return True
        if matches(user32.GetForegroundWindow(), process, title):
            return True
        hwnd = find_window(process, title)
        if hwnd is None:
            return False
        # Windows lets a background program change the active window only right after it sent input.
        send_key("LShift", False)
        send_key("LShift", True)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
        return user32.GetForegroundWindow() == hwnd

else:
    def send_key(name: str, up: bool) -> None:
        pass

    def focus(process: str, title: str) -> bool:
        return False


def down(combo: str) -> None:
    for name in parse(combo):
        send_key(name, False)


def up(combo: str) -> None:
    for name in reversed(parse(combo)):
        send_key(name, True)


def tap(combo: str, hold: float) -> None:
    down(combo)
    time.sleep(hold)
    up(combo)

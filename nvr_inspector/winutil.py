"""Windows 전용 기능(ctypes). 다른 OS에서는 안전한 기본값을 돌려준다."""
import ctypes
import os
import sys
from typing import List, NamedTuple, Tuple

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _user32.WindowFromPoint.argtypes = [wintypes.POINT]
    _user32.WindowFromPoint.restype = wintypes.HWND
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _GetWindowLongPtr = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _SetWindowLongPtr = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLongPtr.restype = ctypes.c_ssize_t
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _SetWindowLongPtr.restype = ctypes.c_ssize_t
    _user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    _user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowDisplayAffinity.restype = wintypes.BOOL
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    try:
        _dwmapi = ctypes.windll.dwmapi
        _dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    except Exception:  # pragma: no cover
        _dwmapi = None
    _user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _user32.OpenInputDesktop.restype = wintypes.HANDLE
    _user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    _user32.CloseDesktop.restype = wintypes.BOOL
    _kernel32_err = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32_err.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32_err.CreateMutexW.restype = wintypes.HANDLE

_GA_ROOT = 2
_GW_HWNDNEXT = 2
_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_LAYERED = 0x00080000
_WS_EX_NOACTIVATE = 0x08000000
_WDA_EXCLUDEFROMCAPTURE = 0x00000011
_DWMWA_EXTENDED_FRAME_BOUNDS = 9
_DWMWA_CLOAKED = 14
_passthrough_hwnds = set()   # 판정 시 무시할 우리 창(화면 표시 오버레이)
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ALREADY_EXISTS = 183
_mutex_handle = None


def enable_dpi_awareness() -> None:
    """화면 배율(125%, 150% 등)에서도 캡처 좌표와 화면 좌표가 일치하도록 한다.
    Tk 창을 만들기 전에 호출해야 한다."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def acquire_single_instance(name: str = "Local\\NVR_Inspector_SingleInstance") -> bool:
    """이미 실행 중이면 False. 중복 실행으로 알림이 두 번 가는 것을 막는다."""
    global _mutex_handle
    if not IS_WINDOWS:
        return True
    _mutex_handle = _kernel32_err.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS


def _process_name(pid: int):
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return None
    finally:
        _kernel32.CloseHandle(handle)


def _pid_of(hwnd) -> int:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _window_below(hwnd, x: int, y: int):
    """z-순서상 hwnd 아래에서 (x, y)를 포함하는 첫 번째 보이는 최상위 창."""
    rect = wintypes.RECT()
    h = _user32.GetWindow(hwnd, _GW_HWNDNEXT)
    while h:
        if (h not in _passthrough_hwnds and _user32.IsWindowVisible(h) and not _user32.IsIconic(h)
                and _user32.GetWindowRect(h, ctypes.byref(rect))
                and rect.left <= x < rect.right and rect.top <= y < rect.bottom):
            return h
        h = _user32.GetWindow(h, _GW_HWNDNEXT)
    return None


def window_at(x: int, y: int):
    """화면 좌표 (x, y)에 보이는 최상위 창 핸들. 화면 표시 오버레이는 건너뛴다."""
    if not IS_WINDOWS:
        return None
    hwnd = _user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if not hwnd:
        return None
    root = _user32.GetAncestor(hwnd, _GA_ROOT) or hwnd
    if root in _passthrough_hwnds:
        root = _window_below(root, int(x), int(y))
    return root or None


class WindowInfo(NamedTuple):
    process: str                       # 실행 파일명 (알 수 없으면 "?")
    rect: Tuple[int, int, int, int]    # 화면에 실제로 보이는 영역 (left, top, right, bottom)
    own: bool = False                  # 이 프로그램(FMVS)의 창


def _cloaked(hwnd) -> bool:
    """다른 가상 데스크톱의 창, 일시 중단된 UWP 앱 등 '보이는 것으로 표시되지만 화면에 없는' 창."""
    if _dwmapi is None:
        return False
    val = wintypes.DWORD(0)
    hr = _dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
    return hr == 0 and val.value != 0


def _frame_rect(hwnd):
    """창이 화면에 실제로 그려지는 영역. GetWindowRect는 Windows 10/11에서 보이지 않는
    크기 조절 테두리(약 7px)까지 포함해 옆에 붙은 ROI를 가린 것으로 오판하므로 DWM 값을 우선 쓴다."""
    rect = wintypes.RECT()
    if _dwmapi is not None and _dwmapi.DwmGetWindowAttribute(
            hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) == 0:
        return rect.left, rect.top, rect.right, rect.bottom
    if _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return rect.left, rect.top, rect.right, rect.bottom
    return None


def _excluded_from_capture(hwnd) -> bool:
    val = wintypes.DWORD(0)
    return bool(_user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(val))) \
        and val.value == _WDA_EXCLUDEFROMCAPTURE


def session_locked() -> bool:
    """화면 잠금(Ctrl+Alt+Del, Win+L)·로그인 화면이면 True. 이때 캡처는 검은 화면이다."""
    if not IS_WINDOWS:
        return False
    desk = _user32.OpenInputDesktop(0, False, 0x0100)      # DESKTOP_SWITCHDESKTOP
    if not desk:
        return True
    _user32.CloseDesktop(desk)
    return False


def visible_windows() -> List[WindowInfo]:
    """화면 캡처에 실제로 찍히는 최상위 창 목록 (위에 있는 창부터 = z-순서).

    제외: 숨김·최소화 창, 다른 가상 데스크톱/일시 중단(cloaked) 창, 클릭 통과 투명 오버레이,
    화면 캡처에서 제외된 창(FMVS 화면 표시 오버레이·미니 모니터 등)."""
    if not IS_WINDOWS:
        return []
    hwnds = []

    def _collect(h, _lparam):
        hwnds.append(h)
        return True

    _user32.EnumWindows(_WNDENUMPROC(_collect), 0)
    me = os.getpid()
    names = {}
    out = []
    for h in hwnds:
        if not h or h in _passthrough_hwnds or not _user32.IsWindowVisible(h) or _user32.IsIconic(h):
            continue
        ex = _GetWindowLongPtr(h, _GWL_EXSTYLE)
        if ex & _WS_EX_TRANSPARENT and ex & _WS_EX_LAYERED:
            continue
        if _cloaked(h) or _excluded_from_capture(h):
            continue
        rect = _frame_rect(h)
        if rect is None or rect[2] <= rect[0] or rect[3] <= rect[1]:
            continue
        pid = _pid_of(h)
        if pid not in names:
            names[pid] = (_process_name(pid) if pid else None) or "?"
        out.append(WindowInfo(names[pid], rect, pid == me))
    return out


def is_passthrough(hwnd) -> bool:
    return hwnd in _passthrough_hwnds


def process_name_at(x: int, y: int):
    """화면 좌표 (x, y)에 보이는 창의 실행 파일명(예: NVR_VIEWER.exe).

    창 핸들(HWND)은 FMVS 프로그램이 내부적으로 창을 다시 만들면 바뀌므로
    프로세스 단위로 비교해야 오탐이 없다. 화면 표시 오버레이는 건너뛴다. 알 수 없으면 None."""
    try:
        for win in visible_windows():
            left, top, right, bottom = win.rect
            if left <= x < right and top <= y < bottom:
                return None if win.process == "?" else win.process
        return None
    except Exception:
        pass
    root = window_at(x, y)
    if not root:
        return None
    pid = _pid_of(root)
    if not pid:
        return None
    return _process_name(pid)


def make_overlay_window(widget_id: int) -> bool:
    """Tk 창을 '클릭 통과 + 작업 표시줄 미표시 + 화면 캡처 제외' 오버레이로 만든다.
    반환: 화면 캡처 제외 성공 여부 (Windows 10 2004 이상에서 지원)."""
    if not IS_WINDOWS:
        return False
    hwnd = _user32.GetAncestor(widget_id, _GA_ROOT) or widget_id
    style = _GetWindowLongPtr(hwnd, _GWL_EXSTYLE)
    _SetWindowLongPtr(hwnd, _GWL_EXSTYLE, style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT
                      | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE)
    _passthrough_hwnds.add(hwnd)
    return bool(_user32.SetWindowDisplayAffinity(hwnd, _WDA_EXCLUDEFROMCAPTURE))


def make_capture_excluded(widget_id: int) -> bool:
    """클릭은 되지만 화면 캡처에는 찍히지 않는 창 (미니 모니터용).
    ROI 위에 놓여도 캡처에서 제외되고, 대상 프로그램 확인에서도 건너뛰므로 판정에 영향이 없다."""
    if not IS_WINDOWS:
        return False
    hwnd = _user32.GetAncestor(widget_id, _GA_ROOT) or widget_id
    style = _GetWindowLongPtr(hwnd, _GWL_EXSTYLE)
    _SetWindowLongPtr(hwnd, _GWL_EXSTYLE, style | _WS_EX_TOOLWINDOW)
    _passthrough_hwnds.add(hwnd)
    return bool(_user32.SetWindowDisplayAffinity(hwnd, _WDA_EXCLUDEFROMCAPTURE))


def set_capture_visible(widget_id: int, visible: bool) -> bool:
    """화면 캡처 제외를 켜고 끈다 (미리보기 캡처용)."""
    if not IS_WINDOWS:
        return False
    hwnd = _user32.GetAncestor(widget_id, _GA_ROOT) or widget_id
    return bool(_user32.SetWindowDisplayAffinity(hwnd, 0 if visible else _WDA_EXCLUDEFROMCAPTURE))


def overlay_style_ok(widget_id: int) -> bool:
    """오버레이가 클릭 통과 상태인지 (테스트/진단용)."""
    if not IS_WINDOWS:
        return False
    hwnd = _user32.GetAncestor(widget_id, _GA_ROOT) or widget_id
    return bool(_GetWindowLongPtr(hwnd, _GWL_EXSTYLE) & _WS_EX_TRANSPARENT)


def virtual_screen_rect():
    """가상 화면 (left, top, width, height). Windows가 아니면 None."""
    if not IS_WINDOWS:
        return None
    return tuple(_user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))


def virtual_screen_origin():
    """모든 모니터를 합친 가상 화면의 좌상단 좌표 (보조 모니터가 왼쪽이면 음수)."""
    if not IS_WINDOWS:
        return 0, 0
    return _user32.GetSystemMetrics(76), _user32.GetSystemMetrics(77)


def beep() -> None:
    if not IS_WINDOWS:
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONHAND)
    except Exception:
        pass

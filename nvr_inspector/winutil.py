"""Windows 전용 기능(ctypes). 다른 OS에서는 안전한 기본값을 돌려준다."""
import ctypes
import os
import sys

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


def process_name_at(x: int, y: int):
    """화면 좌표 (x, y)에 보이는 창의 실행 파일명(예: NVR_VIEWER.exe).

    창 핸들(HWND)은 NVR 프로그램이 내부적으로 창을 다시 만들면 바뀌므로
    프로세스 단위로 비교해야 오탐이 없다. 화면 표시 오버레이는 건너뛴다. 알 수 없으면 None."""
    if not IS_WINDOWS:
        return None
    hwnd = _user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if not hwnd:
        return None
    root = _user32.GetAncestor(hwnd, _GA_ROOT) or hwnd
    if root in _passthrough_hwnds:
        root = _window_below(root, int(x), int(y))
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

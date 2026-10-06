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
    _kernel32_err = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32_err.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32_err.CreateMutexW.restype = wintypes.HANDLE

_GA_ROOT = 2
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


def process_name_at(x: int, y: int):
    """화면 좌표 (x, y)에 보이는 창의 실행 파일명(예: NVR_VIEWER.exe).

    창 핸들(HWND)은 NVR 프로그램이 내부적으로 창을 다시 만들면 바뀌므로
    프로세스 단위로 비교해야 오탐이 없다. 알 수 없으면 None."""
    if not IS_WINDOWS:
        return None
    hwnd = _user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if not hwnd:
        return None
    root = _user32.GetAncestor(hwnd, _GA_ROOT) or hwnd
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
    if not pid.value:
        return None
    return _process_name(pid.value)


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

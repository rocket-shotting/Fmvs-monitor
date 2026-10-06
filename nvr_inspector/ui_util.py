"""여러 창에서 같이 쓰는 Tk 보조 함수."""
import time
import tkinter as tk
from contextlib import contextmanager


@contextmanager
def hidden_windows(*windows: tk.Wm, delay: float = 0.35):
    """캡처 전에 우리 프로그램 창을 잠깐 숨긴다 (창이 ROI를 가리면 우리 창이 캡처되므로)."""
    states = []
    for w in windows:
        try:
            states.append((w, w.state()))
            w.withdraw()
        except tk.TclError:
            pass
    try:
        if windows:
            windows[0].update()
        time.sleep(delay)
        yield
    finally:
        for w, prev in reversed(states):
            try:
                if prev == "iconic":
                    w.iconify()
                elif prev == "zoomed":
                    w.deiconify()
                    w.state("zoomed")
                elif prev != "withdrawn":
                    w.deiconify()
            except tk.TclError:
                pass


def center_on(win: tk.Toplevel, master: tk.Misc) -> None:
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    if master.winfo_viewable():
        x = master.winfo_rootx() + (master.winfo_width() - w) // 2
        y = master.winfo_rooty() + (master.winfo_height() - h) // 2
    else:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


def modal(win: tk.Toplevel, master: tk.Misc) -> None:
    if master.winfo_viewable():
        win.transient(master)
    center_on(win, master)
    win.wait_visibility()
    win.grab_set()
    win.focus_force()
    master.wait_window(win)

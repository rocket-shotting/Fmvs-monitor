"""라이브 화면 위에서 ROI를 드래그로 지정하는 전체 화면 오버레이.

현재 화면을 캡처해 모든 모니터를 덮는 창에 띄우고, 그 위에 사각형을 그린다.
반환 좌표는 실제 화면(가상 화면) 좌표다."""
import tkinter as tk
from typing import List, Optional, Sequence, Tuple

from PIL import ImageTk

Rect = Tuple[int, int, int, int]
_MIN_SIZE = 8
_HELP = "드래그: ROI 지정  |  우클릭·Ctrl+Z: 마지막 취소  |  Enter: 완료  |  Esc: 취소"


class RegionSelector:
    def __init__(self, master: tk.Misc, image, left: int, top: int,
                 existing: Sequence = (), single: bool = False):
        self.master = master
        self.left, self.top = left, top
        self.single = single
        self.result: Optional[List[Rect]] = None
        self.rects: List[Tuple[Rect, int, int]] = []   # (캔버스 좌표 사각형, 사각형 item, 글자 item)
        self._start = None
        self._live = None

        w, h = image.size
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.geometry(f"{w}x{h}+{left}+{top}")
        self.win.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.win, width=w, height=h, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self._photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

        for roi in existing:
            x0, y0 = roi.x - left, roi.y - top
            self.canvas.create_rectangle(x0, y0, x0 + roi.w, y0 + roi.h,
                                         outline="#29b6f6", width=2, dash=(6, 4))
            self.canvas.create_text(x0 + 4, y0 + 4, text=roi.name, anchor="nw",
                                    fill="#29b6f6", font=("맑은 고딕", 10, "bold"))

        self._build_banner()
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", lambda _e: self._undo())
        self.win.bind("<Control-z>", lambda _e: self._undo())
        self.win.bind("<Return>", lambda _e: self._finish())
        self.win.bind("<Escape>", lambda _e: self._cancel())
        self.win.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build_banner(self):
        # 주 모니터는 가상 화면 좌표 (0,0)에서 시작 → 캔버스 좌표 (-left, -top)
        primary_w = self.master.winfo_screenwidth()
        cx = -self.left + primary_w // 2
        title = "ROI 1개 지정 (그리면 바로 적용)" if self.single else "여러 개 지정 가능"
        frame = tk.Frame(self.canvas, bg="#212121", padx=10, pady=6)
        tk.Label(frame, text=f"[ROI 지정] {title}", bg="#212121", fg="#ffeb3b",
                 font=("맑은 고딕", 11, "bold")).pack(side="left")
        tk.Label(frame, text="   " + _HELP, bg="#212121", fg="white",
                 font=("맑은 고딕", 10)).pack(side="left")
        tk.Button(frame, text="완료", width=8, command=self._finish).pack(side="left", padx=(12, 4))
        tk.Button(frame, text="취소", width=8, command=self._cancel).pack(side="left")
        self.canvas.create_window(cx, -self.top + 12, window=frame, anchor="n")

    def _on_press(self, e):
        self._start = (e.x, e.y)
        self._live = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#ff1744", width=2)

    def _on_drag(self, e):
        if self._start and self._live:
            self.canvas.coords(self._live, self._start[0], self._start[1], e.x, e.y)

    def _on_release(self, e):
        if not self._start or not self._live:
            return
        x0, y0 = self._start
        x, y, w, h = min(x0, e.x), min(y0, e.y), abs(e.x - x0), abs(e.y - y0)
        self._start = None
        if w < _MIN_SIZE or h < _MIN_SIZE:
            self.canvas.delete(self._live)
            self._live = None
            return
        self.canvas.coords(self._live, x, y, x + w, y + h)
        label = self.canvas.create_text(x + 4, y + 4, anchor="nw", fill="#ff1744",
                                        font=("맑은 고딕", 11, "bold"),
                                        text=f"새 ROI {len(self.rects) + 1}  ({w}×{h})")
        self.rects.append(((x, y, w, h), self._live, label))
        self._live = None
        if self.single:
            self._finish()

    def _undo(self):
        if self.rects:
            _rect, item, label = self.rects.pop()
            self.canvas.delete(item)
            self.canvas.delete(label)

    def _finish(self):
        self.result = [(x + self.left, y + self.top, w, h) for (x, y, w, h), _i, _t in self.rects]
        self.win.destroy()

    def _cancel(self):
        self.result = None
        self.win.destroy()

    def run(self) -> Optional[List[Rect]]:
        self.win.after(50, lambda: (self.win.focus_force(), self.canvas.focus_set()))
        self.win.wait_visibility()
        self.win.grab_set()
        self.master.wait_window(self.win)
        return self.result


def select_regions(master: tk.Misc, image, left: int, top: int,
                   existing: Sequence = (), single: bool = False) -> Optional[List[Rect]]:
    """취소하면 None, 완료하면 화면 좌표 사각형 목록."""
    return RegionSelector(master, image, left, top, existing, single).run()

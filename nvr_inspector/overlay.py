"""검출 중 화면 표시 오버레이.

- 각 ROI 위치에 상태 색상 테두리 + 이름/상태 표시 (경보는 깜빡임)
- 화면 모서리에 '검출 중' 배지 (동작 시각·ROI 수·경보 수, 검출이 멈추면 빨간 경고)

오버레이는 클릭이 통과하고, 화면 캡처에서 제외된다(Windows 10 2004+).
캡처 제외를 지원하지 않는 Windows에서도 판정에 영향이 없도록 테두리와 글자는 ROI 바깥에만 그린다."""
import tkinter as tk
from datetime import datetime
from typing import Dict, Optional

import geometry
import ui_util
import winutil
from i18n import tr

_KEY = "#010203"          # 투명 처리할 색
_GAP = 3                  # ROI와 테두리 사이 간격(px) – ROI 픽셀을 덮지 않음
_BORDER = 3
_FONT = ("맑은 고딕", 9, "bold")  # i18n: skip
_BADGE_FONT = ("맑은 고딕", 10, "bold")  # i18n: skip

STATE_STYLE = {          # 상태: (테두리 색, 표시 글자)
    "ok": ("#2e7d32", "정상"),
    "pending": ("#ef6c00", "확인 중"),
    "alarm": ("#d50000", "경보"),
    "skip": ("#757575", "건너뜀"),
    "wait": ("#1565c0", "대기"),
    "moving": ("#5c6bc0", "움직임"),
    "off": ("#9e9e9e", "꺼짐"),
    "error": ("#ad1457", "오류"),
    "idle": ("#1565c0", "시작 중"),
}


class ScreenOverlay:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.win: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None
        self.origin = (0, 0)
        self.capture_excluded = False
        self.show_rois = self.show_badge = True
        self.items: Dict[str, dict] = {}
        self.rects = []
        self.badge_bg = self.badge_text = None
        self._blink = False

    # ---------- 생성/표시 ----------
    def _ensure(self):
        if self.win is not None:
            return
        rect = winutil.virtual_screen_rect()
        if rect is None:
            rect = (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        left, top, width, height = rect
        self.origin = (left, top)
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.geometry(f"{width}x{height}+{left}+{top}")
        win.configure(bg=_KEY)
        try:
            win.attributes("-transparentcolor", _KEY)
        except tk.TclError:              # Windows 외 환경: 반투명으로 대체
            win.attributes("-alpha", 0.4)
        win.attributes("-topmost", True)
        self.canvas = tk.Canvas(win, bg=_KEY, highlightthickness=0, width=width, height=height)
        self.canvas.pack(fill="both", expand=True)
        win.update_idletasks()
        self.capture_excluded = winutil.make_overlay_window(win.winfo_id())
        self.win = win
        ui_util.register_capture_hidden(win)

    def show(self, rois, states: dict, show_rois: bool, show_badge: bool):
        if not (show_rois or show_badge):
            self.hide()
            return
        self._ensure()
        self.show_rois, self.show_badge = show_rois, show_badge
        self.redraw(rois, states)
        self.win.deiconify()
        self.win.attributes("-topmost", True)

    def hide(self):
        if self.win is not None:
            self.win.withdraw()

    def destroy(self):
        if self.win is not None:
            ui_util.unregister_capture_hidden(self.win)
            self.win.destroy()
            self.win = None
            self.canvas = None

    def visible(self) -> bool:
        return self.win is not None and self.win.state() == "normal"

    # ---------- 그리기 ----------
    def redraw(self, rois, states: dict):
        if self.canvas is None:
            return
        self.canvas.delete("all")
        self.items.clear()
        self.rects = [geometry.capture_rect(r) for r in rois if r.enabled]
        if self.show_rois:
            for roi in rois:
                if roi.enabled:
                    self._draw_roi(roi, states.get(roi.id, ("idle", ""))[0])
        self.badge_bg = self.badge_text = None
        if self.show_badge:
            self._draw_badge()

    def _draw_roi(self, roi, state: str):
        ox, oy = self.origin
        # 실제 모양(회전 사각형·타원)을 바깥으로 넓혀 그린다 – ROI 픽셀을 덮지 않음
        pts = [(px - ox, py - oy) for px, py in geometry.shape_polygon(roi, pad=_GAP + _BORDER / 2)]
        rect = self.canvas.create_polygon(*[v for p in pts for v in p], fill="", width=_BORDER)
        bx, by, bw, bh = geometry.capture_rect(roi)
        x0, y0 = bx - ox - _GAP, by - oy - _GAP
        y1 = by - oy + bh + _GAP - 1
        # 이름표는 ROI 위쪽 바깥 (화면 위 끝이면 아래쪽 바깥)
        above = y0 - 20 >= 0
        text = self.canvas.create_text(x0 + 4, y0 - 2 if above else y1 + 2, anchor="sw" if above else "nw",
                                       text="", fill="white", font=_FONT)
        bg = self.canvas.create_rectangle(0, 0, 0, 0)
        self.canvas.tag_lower(bg, text)
        self.items[roi.id] = {"rect": rect, "text": text, "bg": bg, "name": roi.name, "state": None}
        self._set_label(roi.id, state)

    def _set_label(self, roi_id: str, state: str):
        it = self.items[roi_id]
        color, label = STATE_STYLE.get(state, STATE_STYLE["idle"])
        self.canvas.itemconfigure(it["text"], text=f" {it['name']} · {tr(label)} ")
        x0, y0, x1, y1 = self.canvas.bbox(it["text"])
        self.canvas.coords(it["bg"], x0 - 2, y0, x1 + 2, y1)
        self.canvas.itemconfigure(it["bg"], fill=color, outline=color)
        self.canvas.itemconfigure(it["rect"], outline=color, width=_BORDER + (2 if state == "alarm" else 0))
        it["state"] = state

    def set_state(self, roi_id: str, state: str):
        it = self.items.get(roi_id)
        if it is not None and it["state"] != state:
            self._set_label(roi_id, state)

    def _badge_position(self, w: int, h: int):
        """주 모니터 네 모서리 중 ROI와 겹치지 않는 곳 (화면 좌표)."""
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        margin = 12
        for x, y in ((sw - w - margin, margin), (margin, margin),
                     (sw - w - margin, sh - h - 60), (margin, sh - h - 60)):
            if not any(x < rx + rw and rx < x + w and y < ry + rh and ry < y + h
                       for rx, ry, rw, rh in self.rects):
                return x, y
        return sw - w - margin, margin

    def _draw_badge(self):
        ox, oy = self.origin
        w, h = 340, 28
        x, y = self._badge_position(w, h)
        self.badge_bg = self.canvas.create_rectangle(x - ox, y - oy, x - ox + w, y - oy + h,
                                                     fill="#1b5e20", outline="#ffffff", width=1)
        self.badge_text = self.canvas.create_text(x - ox + 10, y - oy + h // 2, anchor="w",
                                                  fill="white", font=_BADGE_FONT, text=tr("FMVS 검출 시작 중…"))

    def heartbeat(self, ok: bool, roi_count: int, alarm_count: int):
        """0.5초마다 호출: 배지 갱신 + 경보 ROI 깜빡임."""
        if self.canvas is None or not self.visible():
            return
        self._blink = not self._blink
        for it in self.items.values():
            if it["state"] == "alarm":
                self.canvas.itemconfigure(it["rect"], outline=STATE_STYLE["alarm"][0] if self._blink else "#ffeb3b")
        if self.badge_text is None:
            return
        dot = "●" if self._blink else "○"
        now = f"{datetime.now():%H:%M:%S}"
        if not ok:
            text, fill = tr("⚠ FMVS 검출기 응답 없음 · {time}", time=now), "#b71c1c"
        elif alarm_count:
            text, fill = tr("{dot} FMVS 검출 중 · 경보 {n}건 · {time}", dot=dot, n=alarm_count, time=now), "#c62828"
        else:
            text, fill = tr("{dot} FMVS 검출 중 · ROI {n}개 · {time}", dot=dot, n=roi_count, time=now), "#1b5e20"
        self.canvas.itemconfigure(self.badge_text, text=text)
        self.canvas.itemconfigure(self.badge_bg, fill=fill)

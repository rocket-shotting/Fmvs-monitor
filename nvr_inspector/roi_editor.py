"""라이브 화면 위에서 ROI를 지정하는 전체 화면 편집기.

현재 화면을 캡처해 모든 모니터를 덮는 창에 띄우고, 그 위에서 감시 영역을 그린다.
- 모양: 사각형 / 타원 (Shift를 누른 채 그리면 정사각형 / 원)
- 각도: 선택한 영역 위쪽의 ⟳ 핸들을 끌어 회전 (Shift: 15° 단위), 또는 마우스 휠·←→ 키 (1°, Shift 5°)
- 선택한 영역 안을 끌면 이동, 빈 곳을 끌면 새 영역
반환 좌표는 실제 화면(가상 화면) 좌표다."""
import math
import tkinter as tk
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Optional, Sequence

import numpy as np
from PIL import ImageTk

import geometry
from i18n import tr

_MIN_SIZE = 8
_HANDLE_GAP = 26          # 회전 핸들이 영역 위쪽 가장자리에서 떨어진 거리(px)
_HANDLE_R = 8
_COLOR = "#ff1744"
_SELECTED = "#ffd600"
_FONT = ("맑은 고딕", 11, "bold")  # i18n: skip
_SMALL = ("맑은 고딕", 9)  # i18n: skip
_SHIFT = 0x0001


@dataclass
class Region:
    """지정한 감시 영역 (화면 좌표). x, y, w, h = 회전 전 상자, angle = 시계 방향 각도(도)."""
    x: int
    y: int
    w: int
    h: int
    shape: str = "rect"
    angle: float = 0.0

    @property
    def rect(self):
        return self.x, self.y, self.w, self.h


def _help() -> str:
    return tr("드래그: 영역 그리기 (Shift: 정사각형·원)  |  ⟳ 핸들·휠·←→: 회전 (Shift: 15°·5°)  |  "
              "영역 안 드래그: 이동  |  우클릭·Ctrl+Z: 마지막 취소  |  Enter: 완료  |  Esc: 취소\n"
              "이 안내 막대: ✥ 끌어서 이동 · [▼ 아래로] · H: 숨기기/표시")


class RegionSelector:
    def __init__(self, master: tk.Misc, image, left: int, top: int,
                 existing: Sequence = (), single: bool = False, initial: Optional[Region] = None):
        self.master = master
        self.left, self.top = left, top
        self.single = single
        self.result: Optional[List[Region]] = None
        self.regions: List[dict] = []        # 캔버스 좌표 {x, y, w, h, shape, angle, items}
        self.selected: Optional[int] = None
        self.mode = initial.shape if initial is not None else "rect"
        self._drag: Optional[dict] = None

        w, h = image.size
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.geometry(f"{w}x{h}+{left}+{top}")
        self.win.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.win, width=w, height=h, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self._photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

        for roi in existing:              # 다른 ROI는 파란 점선으로 (실제 모양·각도 그대로)
            pts = [(px - left, py - top) for px, py in geometry.shape_polygon(roi)]
            self.canvas.create_polygon(*[c for p in pts for c in p], outline="#29b6f6", fill="", width=2,
                                       dash=(6, 4))
            bx, by, _bw, _bh = geometry.capture_rect(roi)
            self.canvas.create_text(bx - left + 4, by - top - 2, text=roi.name, anchor="sw",
                                    fill="#29b6f6", font=_SMALL)

        self._build_banner()
        if initial is not None:
            self._add(initial.x - left, initial.y - top, initial.w, initial.h, initial.shape, initial.angle)
        c = self.canvas
        c.bind("<ButtonPress-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Button-3>", lambda _e: self._undo())
        c.bind("<MouseWheel>", self._on_wheel)
        self.win.bind("<Control-z>", lambda _e: self._undo())
        self.win.bind("<Return>", lambda _e: self._finish())
        self.win.bind("<Escape>", lambda _e: self._cancel())
        self.win.bind("<Key-r>", lambda _e: self.set_mode("rect"))
        self.win.bind("<Key-e>", lambda _e: self.set_mode("ellipse"))
        self.win.bind("<Left>", lambda e: self.rotate_by(-5 if e.state & _SHIFT else -1))
        self.win.bind("<Right>", lambda e: self.rotate_by(5 if e.state & _SHIFT else 1))
        self.win.protocol("WM_DELETE_WINDOW", self._cancel)

    # ---------- 안내 막대 (끌어서 이동 · 위/아래 전환 · H: 숨기기) ----------
    def _build_banner(self):
        primary_w = self.master.winfo_screenwidth()
        cx = -self.left + primary_w // 2
        title = tr("ROI 1개 지정 – 그린 뒤 회전·이동하고 Enter") if self.single else tr("여러 개 지정 가능")
        frame = tk.Frame(self.canvas, bg="#212121", padx=10, pady=6, cursor="fleur")
        row1 = tk.Frame(frame, bg="#212121", cursor="fleur")
        row1.pack(fill="x")
        grip = tk.Label(row1, text="✥", bg="#212121", fg="#9e9e9e", font=_FONT, cursor="fleur")
        grip.pack(side="left", padx=(0, 6))
        title_label = tk.Label(row1, text=tr("[ROI 지정] {title}", title=title), bg="#212121", fg="#ffeb3b",
                               font=_FONT, cursor="fleur")
        title_label.pack(side="left")
        self.mode_buttons = {}
        for mode, text in (("rect", tr("□ 사각형 (R)")), ("ellipse", tr("◯ 타원·원 (E)"))):
            btn = tk.Button(row1, text=text, width=12, relief="sunken" if mode == self.mode else "raised",
                            command=lambda m=mode: self.set_mode(m))
            btn.pack(side="left", padx=(10 if mode == "rect" else 2, 0))
            self.mode_buttons[mode] = btn
        self.angle_label = tk.Label(row1, text="", bg="#212121", fg="white", font=_FONT, width=12, cursor="fleur")
        self.angle_label.pack(side="left", padx=10)
        tk.Button(row1, text=tr("0°로"), width=5, command=lambda: self.set_angle(0.0)).pack(side="left")
        tk.Button(row1, text=tr("완료"), width=8, command=self._finish).pack(side="left", padx=(12, 4))
        tk.Button(row1, text=tr("취소"), width=8, command=self._cancel).pack(side="left")
        self.flip_btn = tk.Button(row1, text=tr("▼ 아래로"), width=8, command=self.flip_banner)
        self.flip_btn.pack(side="left", padx=(12, 2))
        tk.Button(row1, text=tr("숨기기 (H)"), width=9, command=self.toggle_banner).pack(side="left")
        help_label = tk.Label(frame, text=_help(), bg="#212121", fg="white", font=_SMALL, cursor="fleur")
        help_label.pack(anchor="w", pady=(4, 0))
        self.banner_frame = frame
        self.banner = self.canvas.create_window(cx, -self.top + 12, window=frame, anchor="n")
        self.banner_at_bottom = False
        self.banner_hidden = False
        self._banner_drag = None
        # 숨겼을 때 되살리는 안내 (캔버스 글자라 클릭을 막지 않음 – 그 위에도 ROI를 그릴 수 있다)
        self.banner_hint = self.canvas.create_text(
            cx, -self.top + 6, anchor="n", state="hidden", fill="#ffeb3b", font=_SMALL,
            text=tr("H: 안내 막대 다시 표시  ·  Enter: 완료  ·  Esc: 취소"))
        for widget in (frame, row1, grip, title_label, self.angle_label, help_label):
            widget.bind("<ButtonPress-1>", self._banner_press)
            widget.bind("<B1-Motion>", self._banner_move)
            widget.bind("<ButtonRelease-1>", self._banner_release)
        self.win.bind("<Key-h>", lambda _e: self.toggle_banner())
        self.win.bind("<Key-H>", lambda _e: self.toggle_banner())

    def _banner_press(self, e):
        x, y = self.canvas.coords(self.banner)
        self._banner_drag = (e.x_root, e.y_root, x, y)

    def _banner_move(self, e):
        if self._banner_drag is None:
            return
        x0, y0, bx, by = self._banner_drag
        self.move_banner(bx + e.x_root - x0, by + e.y_root - y0)

    def _banner_release(self, _e):
        self._banner_drag = None

    def move_banner(self, x: float, y: float):
        """안내 막대를 캔버스 좌표 (x: 가운데, y: 위쪽)로 옮긴다 (화면 밖으로 나가지 않게)."""
        self.banner_frame.update_idletasks()
        fw, fh = self.banner_frame.winfo_reqwidth(), self.banner_frame.winfo_reqheight()
        cw = max(self.canvas.winfo_width(), int(self.canvas.cget("width")))
        ch = max(self.canvas.winfo_height(), int(self.canvas.cget("height")))
        x = min(max(x, fw / 2), max(fw / 2, cw - fw / 2))
        y = min(max(y, 0), max(0, ch - fh))
        self.canvas.coords(self.banner, x, y)

    def flip_banner(self):
        """주 모니터 위쪽 ↔ 아래쪽 전환."""
        self.banner_frame.update_idletasks()
        fh = self.banner_frame.winfo_reqheight()
        x, _y = self.canvas.coords(self.banner)
        self.banner_at_bottom = not self.banner_at_bottom
        if self.banner_at_bottom:
            y = -self.top + self.master.winfo_screenheight() - fh - 60     # 작업 표시줄 위
        else:
            y = -self.top + 12
        self.move_banner(x, y)
        self.flip_btn.configure(text=tr("▲ 위로") if self.banner_at_bottom else tr("▼ 아래로"))

    def toggle_banner(self):
        """안내 막대 숨기기/보이기 (H). 숨긴 동안 그 자리에도 ROI를 그릴 수 있다."""
        self.banner_hidden = not self.banner_hidden
        self.canvas.itemconfigure(self.banner, state="hidden" if self.banner_hidden else "normal")
        if self.banner_hidden:
            x, y = self.canvas.coords(self.banner)
            self.canvas.coords(self.banner_hint, x, y)
        self.canvas.itemconfigure(self.banner_hint, state="normal" if self.banner_hidden else "hidden")

    def set_mode(self, mode: str):
        """그릴 모양 선택. 1개 모드(위치 재지정)에서는 지금 영역의 모양도 바꾼다.
        여러 개 모드에서는 다음에 그릴 모양만 바뀐다 (이미 그린 영역은 그대로)."""
        self.mode = mode
        for m, btn in self.mode_buttons.items():
            btn.configure(relief="sunken" if m == mode else "raised")
        if self.single and self.selected is not None:
            self.regions[self.selected]["shape"] = mode
            self._redraw(self.selected)

    # ---------- 그리기 ----------
    @staticmethod
    def _ns(r):
        return SimpleNamespace(x=r["x"], y=r["y"], w=r["w"], h=r["h"], shape=r["shape"], angle=r["angle"])

    @staticmethod
    def _handle_pos(r):
        """회전 핸들 위치: 영역 위쪽 가장자리 가운데에서 바깥으로 _HANDLE_GAP (영역과 함께 회전)."""
        cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
        rad = math.radians(r["angle"])
        d = r["h"] / 2 + _HANDLE_GAP
        return cx + math.sin(rad) * d, cy - math.cos(rad) * d

    def _add(self, x, y, w, h, shape, angle=0.0):
        self.regions.append({"x": x, "y": y, "w": w, "h": h, "shape": shape, "angle": float(angle) % 360,
                             "items": []})
        self._select(len(self.regions) - 1)

    def _redraw(self, idx: int):
        r = self.regions[idx]
        c = self.canvas
        for item in r["items"]:
            c.delete(item)
        sel = idx == self.selected
        color = _SELECTED if sel else _COLOR
        pts = geometry.shape_polygon(self._ns(r))
        items = [c.create_polygon(*[v for p in pts for v in p], outline=color, fill="", width=3 if sel else 2)]
        bx, by, _bw, _bh = geometry.capture_rect(self._ns(r))
        label = tr("새 ROI {n}  ({w}×{h}{angle})", n=idx + 1, w=r["w"], h=r["h"],
                   angle=f" · {r['angle']:g}°" if r["angle"] else "")
        items.append(c.create_text(bx + 4, by - 4, anchor="sw", fill=color, font=_FONT, text=label))
        if sel:
            hx, hy = self._handle_pos(r)
            cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
            rad = math.radians(r["angle"])
            ex, ey = cx + math.sin(rad) * r["h"] / 2, cy - math.cos(rad) * r["h"] / 2
            items.append(c.create_line(ex, ey, hx, hy, fill=_SELECTED, width=2))
            items.append(c.create_oval(hx - _HANDLE_R, hy - _HANDLE_R, hx + _HANDLE_R, hy + _HANDLE_R,
                                       fill=_SELECTED, outline="#000000"))
            items.append(c.create_text(hx, hy, text="⟳", font=("Segoe UI", 8, "bold"), fill="#000000"))
            items.append(c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=_SELECTED, outline=""))
            self.angle_label.configure(text=tr("각도 {angle}°", angle=f"{r['angle']:g}"))
        r["items"] = items

    def _select(self, idx: Optional[int]):
        prev, self.selected = self.selected, idx
        if prev is not None and prev < len(self.regions):
            self._redraw(prev)
        if idx is not None:
            self._redraw(idx)
        else:
            self.angle_label.configure(text="")

    def _hit(self, x, y) -> Optional[int]:
        """(x, y)를 포함하는 영역 (나중에 그린 것 우선)."""
        for idx in range(len(self.regions) - 1, -1, -1):
            if geometry.contains(self._ns(self.regions[idx]), np.array([x]), np.array([y]))[0]:
                return idx
        return None

    # ---------- 마우스 ----------
    def _on_press(self, e):
        if self.selected is not None:
            hx, hy = self._handle_pos(self.regions[self.selected])
            if math.hypot(e.x - hx, e.y - hy) <= _HANDLE_R + 4:
                self._drag = {"kind": "rotate"}
                return
        hit = self._hit(e.x, e.y)
        if hit is not None:
            self._select(hit)
            r = self.regions[hit]
            self._drag = {"kind": "move", "start": (e.x, e.y), "pos": (r["x"], r["y"])}
            return
        self._drag = {"kind": "draw", "start": (e.x, e.y),
                      "live": self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline=_COLOR, width=2)}

    @staticmethod
    def _box(start, e):
        """드래그 시작점과 현재 마우스로 상자 (Shift: 정사각형·원)."""
        return geometry.drag_box(start, (e.x, e.y), bool(e.state & _SHIFT))

    def _on_drag(self, e):
        d = self._drag
        if d is None:
            return
        if d["kind"] == "draw":
            x, y, w, h = self._box(d["start"], e)
            self.canvas.delete(d["live"])
            make = self.canvas.create_oval if self.mode == "ellipse" else self.canvas.create_rectangle
            d["live"] = make(x, y, x + w, y + h, outline=_COLOR, width=2)
        elif d["kind"] == "move":
            r = self.regions[self.selected]
            r["x"] = int(d["pos"][0] + e.x - d["start"][0])
            r["y"] = int(d["pos"][1] + e.y - d["start"][1])
            self._redraw(self.selected)
        elif d["kind"] == "rotate":
            self.rotate_to_point(e.x, e.y, snap=15 if e.state & _SHIFT else 1)

    def _on_release(self, e):
        d, self._drag = self._drag, None
        if d is None or d["kind"] != "draw":
            return
        self.canvas.delete(d["live"])
        x, y, w, h = self._box(d["start"], e)        # 드래그 정보는 위에서 비웠으므로 d를 쓴다
        if w < _MIN_SIZE or h < _MIN_SIZE:
            self._select(None)
            return
        self.add_region(x, y, w, h)

    def _on_wheel(self, e):
        step = 5 if e.state & _SHIFT else 1
        self.rotate_by(-step if e.delta > 0 else step)

    # ---------- 조작 (테스트에서도 사용) ----------
    def add_region(self, x: int, y: int, w: int, h: int):
        """캔버스 좌표 상자로 현재 모양의 영역 추가 (1개 모드면 기존 것을 대신하고 각도는 유지)."""
        if self.single and self.regions:
            angle = self.regions[0]["angle"]
            self._clear()
            self._add(x, y, w, h, self.mode, angle)
        else:
            self._add(x, y, w, h, self.mode)

    def rotate_to_point(self, x: float, y: float, snap: float = 1):
        """선택한 영역의 중심에서 (x, y) 방향이 '위쪽'이 되도록 회전."""
        if self.selected is None:
            return
        r = self.regions[self.selected]
        cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
        angle = math.degrees(math.atan2(x - cx, -(y - cy)))
        self.set_angle(round(angle / snap) * snap)

    def rotate_by(self, delta: float):
        if self.selected is not None:
            self.set_angle(self.regions[self.selected]["angle"] + delta)

    def set_angle(self, angle: float):
        if self.selected is None:
            return
        a = round(float(angle) % 360.0, 1)
        self.regions[self.selected]["angle"] = 0.0 if a >= 360.0 else a
        self._redraw(self.selected)

    # ---------- 취소/완료 ----------
    def _clear(self):
        for r in self.regions:
            for item in r["items"]:
                self.canvas.delete(item)
        self.regions.clear()
        self.selected = None

    def _undo(self):
        if self.regions:
            r = self.regions.pop()
            for item in r["items"]:
                self.canvas.delete(item)
            self.selected = None
            if self.regions:
                self._select(len(self.regions) - 1)
            else:
                self.angle_label.configure(text="")

    def _finish(self):
        self.result = [Region(int(r["x"] + self.left), int(r["y"] + self.top), int(r["w"]), int(r["h"]),
                              r["shape"], float(r["angle"])) for r in self.regions]
        self.win.destroy()

    def _cancel(self):
        self.result = None
        self.win.destroy()

    def run(self) -> Optional[List[Region]]:
        self.win.after(50, lambda: (self.win.focus_force(), self.canvas.focus_set()))
        self.win.wait_visibility()
        self.win.grab_set()
        self.master.wait_window(self.win)
        return self.result


def select_regions(master: tk.Misc, image, left: int, top: int, existing: Sequence = (),
                   single: bool = False, initial: Optional[Region] = None) -> Optional[List[Region]]:
    """취소하면 None, 완료하면 Region 목록 (화면 좌표, 모양·각도 포함)."""
    return RegionSelector(master, image, left, top, existing, single, initial).run()

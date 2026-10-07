"""관제센터 대시보드 구성요소 (다크 테마): KPI 타일, 카메라 월, 에이전트 활동 피드, NG 추이 차트."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageTk

from agent import FEED_KINDS, FeedItem

F = "맑은 고딕"
NUM_FONT = ("Segoe UI", 20, "bold")

T = {
    "bg": "#0b1220", "panel": "#111a2e", "card": "#16213a", "card_hi": "#1c2a48", "border": "#23304d",
    "text": "#e6edf7", "muted": "#8aa0c0", "dim": "#4b5d7d",
    "accent": "#22d3ee", "green": "#22c55e", "red": "#ef4444", "amber": "#f59e0b",
    "indigo": "#818cf8", "sky": "#38bdf8", "pink": "#ec4899", "slate": "#64748b",
}

STATE_COLORS = {
    "ok": T["green"], "pending": T["amber"], "alarm": T["red"], "skip": T["slate"], "wait": T["sky"],
    "moving": T["indigo"], "off": "#475569", "error": T["pink"], "idle": T["sky"],
}
STATE_SHORT = {
    "ok": "OK", "pending": "확인 중", "alarm": "NG", "skip": "가려짐", "wait": "대기",
    "moving": "움직임", "off": "꺼짐", "error": "오류", "idle": "대기",
}


def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.configure(bg=T["bg"])
    style.configure("Dark.Treeview", background=T["panel"], fieldbackground=T["panel"], foreground=T["text"],
                    rowheight=28, borderwidth=0, font=(F, 9))
    style.configure("Dark.Treeview.Heading", background=T["card"], foreground=T["muted"], relief="flat",
                    font=(F, 9, "bold"), borderwidth=0)
    style.map("Dark.Treeview", background=[("selected", "#1e3a5f")], foreground=[("selected", "#ffffff")])
    style.map("Dark.Treeview.Heading", background=[("active", T["card_hi"])])
    style.configure("Dark.TNotebook", background=T["bg"], borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure("Dark.TNotebook.Tab", background=T["card"], foreground=T["muted"], padding=(16, 6),
                    font=(F, 9, "bold"), borderwidth=0)
    style.map("Dark.TNotebook.Tab", background=[("selected", T["panel"])], foreground=[("selected", T["accent"])])
    style.configure("Dark.Vertical.TScrollbar", troughcolor=T["bg"], background=T["card"], bordercolor=T["bg"],
                    arrowcolor=T["muted"], lightcolor=T["card"], darkcolor=T["card"])
    style.configure("Dark.TPanedwindow", background=T["bg"])


class FlatButton(tk.Label):
    STYLES = {   # 종류: (배경, 글자, 마우스 올림 배경)
        "primary": (T["accent"], "#06202a", "#67e8f9"),
        "danger": (T["red"], "#ffffff", "#f87171"),
        "ghost": (T["card"], T["text"], T["card_hi"]),
    }

    def __init__(self, master, text: str, command: Callable, kind: str = "ghost", **kw):
        bg, fg, hover = self.STYLES[kind]
        super().__init__(master, text=text, bg=bg, fg=fg, cursor="hand2", padx=kw.pop("padx", 12),
                         pady=kw.pop("pady", 6), font=kw.pop("font", (F, 9, "bold")), **kw)
        self._colors = (bg, fg, hover)
        self._command = command
        self.enabled = True
        self.bind("<Enter>", lambda _e: self.enabled and self.configure(bg=hover))
        self.bind("<Leave>", lambda _e: self.configure(bg=bg if self.enabled else T["panel"]))
        self.bind("<Button-1>", lambda _e: self.enabled and self._command())

    def set_enabled(self, flag: bool):
        bg, fg, _h = self._colors
        self.enabled = flag
        self.configure(bg=bg if flag else T["panel"], fg=fg if flag else T["dim"],
                       cursor="hand2" if flag else "arrow")


class KpiTile(tk.Frame):
    def __init__(self, master, title: str, accent: str):
        super().__init__(master, bg=T["card"], highlightthickness=1, highlightbackground=T["border"])
        tk.Frame(self, bg=accent, width=4).pack(side="left", fill="y")
        body = tk.Frame(self, bg=T["card"], padx=14, pady=8)
        body.pack(side="left", fill="both", expand=True)
        tk.Label(body, text=title, bg=T["card"], fg=T["muted"], font=(F, 9)).pack(anchor="w")
        self.value = tk.Label(body, text="—", bg=T["card"], fg=T["text"], font=NUM_FONT)
        self.value.pack(anchor="w")
        self.sub = tk.Label(body, text="", bg=T["card"], fg=T["dim"], font=(F, 8))
        self.sub.pack(anchor="w")

    def set(self, value: str, sub: str = "", color: Optional[str] = None):
        self.value.configure(text=value, fg=color or T["text"])
        self.sub.configure(text=sub)


class CameraCard(tk.Frame):
    W, H = 256, 144

    def __init__(self, master, roi_id: str, on_select: Callable, on_open: Callable):
        super().__init__(master, bg=T["card"], highlightthickness=2, highlightbackground=T["border"])
        self.roi_id = roi_id
        self.state = "idle"
        self.color = STATE_COLORS["idle"]
        self.meta = ""
        self.has_frame = False
        self._photo = None
        self.view = tk.Canvas(self, width=self.W, height=self.H, bg="#05080f", highlightthickness=0)
        self.view.pack(padx=6, pady=(6, 4))
        row = tk.Frame(self, bg=T["card"])
        row.pack(fill="x", padx=8)
        self.name = tk.Label(row, text="", bg=T["card"], fg=T["text"], font=(F, 10, "bold"), anchor="w")
        self.name.pack(side="left", fill="x", expand=True)
        self.pill = tk.Label(row, text="대기", bg=self.color, fg="#06101f", font=(F, 8, "bold"), padx=8)
        self.pill.pack(side="right")
        self.detail = tk.Label(self, text="", bg=T["card"], fg=T["muted"], font=(F, 8), anchor="w",
                               justify="left", wraplength=self.W)
        self.detail.pack(fill="x", padx=8, pady=(2, 8))
        self._row = row
        for w in (self, self.view, row, self.name, self.pill, self.detail):
            w.bind("<Button-1>", lambda _e: on_select(roi_id))
            w.bind("<Double-1>", lambda _e: on_open(roi_id))
        self._placeholder()

    def set_meta(self, roi):
        self.name.configure(text=roi.name)
        self.meta = f"{roi.detector_label().split(' (')[0]} · {roi.w}×{roi.h}"
        if not self.has_frame:
            self._placeholder()

    def set_state(self, state: str, detail: str):
        self.state = state
        self.color = STATE_COLORS.get(state, T["sky"])
        active = state not in ("idle", "off")
        self.configure(highlightbackground=self.color if active else T["border"])
        self.pill.configure(text=STATE_SHORT.get(state, state), bg=self.color)
        self.detail.configure(text=(detail[:110] + "…") if len(detail) > 110 else detail)
        self._hud()

    def set_frame(self, rgb):
        img = Image.fromarray(rgb)
        img.thumbnail((self.W, self.H))
        canvas = Image.new("RGB", (self.W, self.H), (5, 8, 15))
        canvas.paste(img, ((self.W - img.width) // 2, (self.H - img.height) // 2))
        self._photo = ImageTk.PhotoImage(canvas)
        self.view.delete("all")
        self.view.create_image(0, 0, anchor="nw", image=self._photo)
        self.has_frame = True
        self._hud()

    def clear_frame(self):
        self.has_frame = False
        self._photo = None
        self._placeholder()

    def highlight(self, selected: bool):
        bg = T["card_hi"] if selected else T["card"]
        for w in (self, self._row, self.name, self.detail):
            w.configure(bg=bg)

    def blink(self, on: bool):
        if self.state == "alarm":
            self.configure(highlightbackground=T["red"] if on else "#7f1d1d")

    def _placeholder(self):
        v = self.view
        v.delete("all")
        for x in range(0, self.W, 16):
            v.create_line(x, 0, x, self.H, fill="#0c1426")
        for y in range(0, self.H, 16):
            v.create_line(0, y, self.W, y, fill="#0c1426")
        v.create_text(self.W // 2, self.H // 2 - 8, text="STANDBY", fill=T["dim"], font=("Segoe UI", 14, "bold"))
        v.create_text(self.W // 2, self.H // 2 + 14, text=self.meta, fill=T["dim"], font=(F, 8))
        self._hud()

    def _hud(self):
        """HUD 스타일 모서리 표시 + LIVE 표시."""
        v, c, n, w, h = self.view, self.color, 16, self.W - 2, self.H - 2
        v.delete("hud")
        for x, y, dx, dy in ((2, 2, 1, 1), (w, 2, -1, 1), (2, h, 1, -1), (w, h, -1, -1)):
            v.create_line(x, y, x + dx * n, y, fill=c, width=2, tags="hud")
            v.create_line(x, y, x, y + dy * n, fill=c, width=2, tags="hud")
        if self.has_frame:
            v.create_rectangle(8, 8, 48, 24, fill="#000000", outline="", tags="hud")
            v.create_oval(13, 13, 19, 19, fill=T["red"] if self.state != "off" else T["slate"], outline="", tags="hud")
            v.create_text(34, 16, text="LIVE", fill="#ffffff", font=("Segoe UI", 7, "bold"), tags="hud")


class CameraWall(tk.Frame):
    GAP = 8

    def __init__(self, master, on_select: Callable, on_open: Callable):
        super().__init__(master, bg=T["bg"])
        self.on_select, self.on_open = on_select, on_open
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="n")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))
        self.cards: Dict[str, CameraCard] = {}
        self.order: List[str] = []
        self._cols = 0
        self.empty = tk.Label(self.inner, text="등록된 ROI가 없습니다\n상단의 [＋ ROI 추가]로 감시할 카메라 영역을 지정하세요",
                              bg=T["bg"], fg=T["muted"], font=(F, 11), justify="center")

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_resize(self, e):
        self.canvas.coords(self._win, e.width // 2, 0)       # 카드 묶음을 가운데 정렬
        cols = max(1, e.width // (CameraCard.W + 16 + self.GAP * 2))
        if cols != self._cols:
            self._cols = cols
            self._layout()

    def _layout(self):
        cols = max(1, self._cols)
        for w in self.inner.grid_slaves():
            w.grid_forget()
        if not self.order:
            self.empty.grid(row=0, column=0, padx=40, pady=80)
            return
        for i, rid in enumerate(self.order):
            self.cards[rid].grid(row=i // cols, column=i % cols, padx=self.GAP, pady=self.GAP, sticky="n")

    def set_rois(self, rois, states: Dict[str, Tuple[str, str]], running: bool):
        ids = [r.id for r in rois]
        for rid in list(self.cards):
            if rid not in ids:
                self.cards.pop(rid).destroy()
        for r in rois:
            card = self.cards.get(r.id)
            if card is None:
                card = self.cards[r.id] = CameraCard(self.inner, r.id, self.on_select, self.on_open)
            card.set_meta(r)
            if not r.enabled:
                card.set_state("off", "사용 안 함")
            elif running:
                card.set_state(*states.get(r.id, ("idle", "검사 준비 중")))
            else:
                card.set_state("idle", "검출 대기 – ▶ 시작을 누르면 실시간 판정")
            if not running and card.has_frame:
                card.clear_frame()
        self.order = ids
        self._layout()

    def update_state(self, roi_id: str, state: str, detail: str):
        card = self.cards.get(roi_id)
        if card is not None:
            card.set_state(state, detail)

    def update_frame(self, roi_id: str, rgb):
        card = self.cards.get(roi_id)
        if card is not None:
            card.set_frame(rgb)

    def select(self, roi_ids):
        for rid, card in self.cards.items():
            card.highlight(rid in roi_ids)

    def blink(self, on: bool):
        for card in self.cards.values():
            card.blink(on)


class FeedPanel(tk.Frame):
    """에이전트 활동 + 시스템 로그 통합 스트림."""
    COLORS = {"boot": T["accent"], "observe": "#93c5fd", "think": "#c4b5fd", "act": T["amber"],
              "learn": T["green"], "warn": T["red"], "sys": T["muted"], "error": T["red"]}
    MAX_LINES = 400

    def __init__(self, master):
        super().__init__(master, bg=T["panel"], highlightthickness=1, highlightbackground=T["border"])
        head = tk.Frame(self, bg=T["panel"])
        head.pack(fill="x", padx=12, pady=(10, 4))
        self.dot = tk.Label(head, text="●", bg=T["panel"], fg=T["dim"], font=(F, 10))
        self.dot.pack(side="left")
        tk.Label(head, text=" AGENT ACTIVITY · SYSTEM LOG", bg=T["panel"], fg=T["text"],
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(head, text="에이전트 관찰·판단·실행·학습 + 시스템 기록", bg=T["panel"], fg=T["muted"],
                 font=(F, 8)).pack(side="right")
        body = tk.Frame(self, bg=T["panel"])
        body.pack(fill="both", expand=True, padx=(12, 4), pady=(0, 10))
        self.text = tk.Text(body, height=6, bg=T["panel"], fg=T["text"], font=(F, 9), wrap="word", relief="flat",
                            borderwidth=0, highlightthickness=0, state="disabled", spacing1=2, spacing3=3)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.text.yview, style="Dark.Vertical.TScrollbar")
        self.text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("time", foreground=T["dim"], font=("Consolas", 8))
        for kind, color in self.COLORS.items():
            self.text.tag_configure(kind, foreground=color, font=(F, 9, "bold"))
        self.text.tag_configure("body", foreground=T["text"])

    def add(self, item: FeedItem):
        icon, name = FEED_KINDS.get(item.kind, SYS_KINDS.get(item.kind, ("•", item.kind)))
        t = self.text
        t.configure(state="normal")
        t.insert("end", datetime.fromtimestamp(item.when).strftime("%H:%M:%S "), "time")
        t.insert("end", f"{icon} {name}  ", item.kind)
        t.insert("end", item.text + "\n", "body")
        excess = int(t.index("end-1c").split(".")[0]) - self.MAX_LINES
        if excess > 0:
            t.delete("1.0", f"{excess + 1}.0")
        t.see("end")
        t.configure(state="disabled")

    def pulse(self, running: bool, on: bool):
        self.dot.configure(fg=(T["green"] if on else "#14532d") if running else T["dim"])


SYS_KINDS = {"sys": ("·", "로그"), "error": ("✖", "오류")}


def draw_roi_rows(canvas: tk.Canvas, trends, x0: int, y0: int, width: int, row_h: int, max_rows: int,
                  compact: bool = False):
    """ROI별 한 줄: 상태 점 · 이름 · 최근 NG 수 · 시간대별 NG 막대. 그린 줄 수를 반환."""
    shown = trends[:max_rows]
    name_w = 120 if compact else 150
    count_w = 46
    for i, t in enumerate(shown):
        y = y0 + i * row_h
        cy = y + row_h // 2
        if i % 2 == 0:
            canvas.create_rectangle(x0, y, x0 + width, y + row_h, fill="#0f1830", outline="")
        state = t["state"] if t["enabled"] else "off"
        canvas.create_oval(x0 + 6, cy - 4, x0 + 14, cy + 4, fill=STATE_COLORS.get(state, T["sky"]), outline="")
        name = t["name"] if len(t["name"]) <= 14 else t["name"][:13] + "…"
        canvas.create_text(x0 + 20, cy, anchor="w", text=name, fill=T["text"], font=(F, 9 if not compact else 8))
        canvas.create_text(x0 + name_w + count_w - 6, cy, anchor="e", text=str(t["recent"]),
                           fill=T["red"] if t["recent"] else T["dim"], font=("Segoe UI", 10, "bold"))
        bx0, bx1 = x0 + name_w + count_w, x0 + width - 6
        series = t["series"]
        peak = max([c for _h, c in series] + [1])
        slot = (bx1 - bx0) / max(1, len(series))
        for j, (_hour, c) in enumerate(series):
            bx = bx0 + slot * j
            bh = (row_h - 8) * c / peak if c else 2
            canvas.create_rectangle(bx + 1, y + row_h - 4 - bh, bx + slot - 1, y + row_h - 4,
                                    fill=T["red"] if c else T["border"], outline="")
    return len(shown)


class RoiTrendPanel(tk.Canvas):
    """ROI별 NG 추이 (최근 12시간, 시간대별) – 메인 화면 오른쪽."""
    ROW_H = 30

    def __init__(self, master, on_select: Optional[Callable] = None):
        super().__init__(master, bg=T["panel"], highlightthickness=1, highlightbackground=T["border"])
        self.trends: List[dict] = []
        self.on_select = on_select
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Button-1>", self._click)

    def draw(self, trends):
        self.trends = trends
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 120 or h < 80:
            return
        self.create_text(14, 16, anchor="w", text="ROI MONITORING", fill=T["text"], font=("Segoe UI", 11, "bold"))
        self.create_text(w - 14, 16, anchor="e", text="ROI별 NG 추이 · 최근 12시간", fill=T["muted"], font=(F, 8))
        self.create_text(14 + 150 + 40, 38, anchor="e", text="NG", fill=T["muted"], font=(F, 8))
        if self.trends:
            hours = self.trends[0]["series"]
            bx0, bx1 = 14 + 150 + 46, w - 20
            slot = (bx1 - bx0) / max(1, len(hours))
            for j, (hour, _c) in enumerate(hours):
                if j % 3 == 0:
                    self.create_text(bx0 + slot * (j + 0.5), 38, text=f"{hour}시", fill=T["dim"], font=("Segoe UI", 7))
        else:
            self.create_text(w // 2, h // 2, text="ROI를 추가하면 여기서 ROI별 NG 추이를 볼 수 있습니다",
                             fill=T["muted"], font=(F, 9))
            return
        max_rows = max(1, (h - 48 - 18) // self.ROW_H)
        if len(self.trends) <= (h - 48 - 4) // self.ROW_H:
            max_rows = len(self.trends)             # 다 들어가면 안내 문구 자리 없이 모두 표시
        n = draw_roi_rows(self, self.trends, 8, 48, w - 16, self.ROW_H, max_rows)
        if len(self.trends) > n:
            self.create_text(w // 2, h - 8, text=f"외 {len(self.trends) - n}개 ROI (창을 키우면 더 보입니다)",
                             fill=T["dim"], font=(F, 8))

    def _click(self, e):
        idx = (e.y - 48) // self.ROW_H
        if self.on_select and 0 <= idx < len(self.trends) and e.y >= 48:
            self.on_select(self.trends[idx]["id"])


class MiniMonitor:
    """검출 중 화면 하단(오른쪽/왼쪽)에 떠 있는 ROI 트렌드 미니 모니터.
    화면 캡처에서 제외되고 대상 프로그램 확인에서도 건너뛰므로 ROI 위에 있어도 판정에 영향이 없다."""
    WIDTH = 420
    ROW_H = 24
    MAX_ROWS = 14

    def rect(self):
        """화면 위 미니 모니터 영역 (팝업 배치 시 피하기 위함). 안 보이면 None."""
        if not self.visible():
            return None
        return (self.win.winfo_x(), self.win.winfo_y(), self.win.winfo_width(), self.win.winfo_height())

    def __init__(self, root: tk.Tk, on_open: Callable, on_stop: Callable):
        self.root = root
        self.on_open, self.on_stop = on_open, on_stop
        self.win: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None
        self.capture_excluded = False
        self._drag = (0, 0)
        self.user_moved = False
        self.trends: List[dict] = []
        self.status = ("", T["green"])

    def _ensure(self):
        if self.win is not None:
            return
        import winutil
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=T["accent"], padx=1, pady=1)
        head = tk.Frame(win, bg=T["panel"])
        head.pack(fill="x")
        self.title = tk.Label(head, text="◆ FMVS VISION AGENT", bg=T["panel"], fg=T["accent"],
                              font=("Segoe UI", 10, "bold"), padx=8, pady=4)
        self.title.pack(side="left")
        FlatButton(head, "■", self.on_stop, kind="danger", padx=8, pady=2).pack(side="right", padx=(2, 4), pady=3)
        FlatButton(head, "대시보드 열기", self.on_open, padx=8, pady=2, font=(F, 8, "bold")).pack(side="right", pady=3)
        self.clock = tk.Label(head, text="", bg=T["panel"], fg=T["text"], font=("Segoe UI", 9, "bold"))
        self.clock.pack(side="right", padx=6)
        for w in (head, self.title, self.clock):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
        self.canvas = tk.Canvas(win, bg=T["bg"], highlightthickness=0, width=self.WIDTH, height=60)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Double-1>", lambda _e: self.on_open())
        win.update_idletasks()
        self.capture_excluded = winutil.make_capture_excluded(win.winfo_id())
        self.win = win

    def _drag_start(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag_move(self, e):
        self.user_moved = True
        self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def show(self, trends, position: str, avoid_rects):
        self._ensure()
        self.trends = trends
        self._redraw()
        if not self.user_moved:
            self.win.geometry(f"+{self._x(position, avoid_rects)}+{self._y()}")
        self.win.deiconify()
        self.win.attributes("-topmost", True)

    def _height(self):
        rows = min(len(self.trends), self.MAX_ROWS)
        return 34 + max(1, rows) * self.ROW_H + (16 if len(self.trends) > self.MAX_ROWS else 0) + 8

    def _y(self):
        self.win.update_idletasks()
        return max(0, self.root.winfo_screenheight() - self.win.winfo_reqheight() - 56)

    def _x(self, position: str, avoid_rects):
        sw = self.root.winfo_screenwidth()
        right, left = sw - self.WIDTH - 16, 12
        if position == "right":
            return right
        if position == "left":
            return left
        h = self._height() + 34
        y = self.root.winfo_screenheight() - h - 56

        def overlap(x):
            total = 0
            for rx, ry, rw, rh in avoid_rects:
                ow = min(x + self.WIDTH, rx + rw) - max(x, rx)
                oh = min(y + h, ry + rh) - max(y, ry)
                total += ow * oh if ow > 0 and oh > 0 else 0
            return total
        return right if overlap(right) <= overlap(left) else left

    def hide(self):
        if self.win is not None:
            self.win.withdraw()

    def visible(self) -> bool:
        return self.win is not None and self.win.state() == "normal"

    def update(self, trends, status_text: str, ok: bool):
        if not self.visible():
            return
        self.trends = trends
        self.status = (status_text, T["green"] if ok else T["red"])
        self.clock.configure(text=datetime.now().strftime("%H:%M:%S"))
        self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        h = self._height()
        c.configure(height=h)
        text, color = self.status
        c.create_text(10, 14, anchor="w", text=text or "● 실시간 감시 중", fill=color, font=(F, 9, "bold"))
        c.create_text(self.WIDTH - 10, 14, anchor="e", text="NG · 최근 12시간", fill=T["muted"], font=(F, 8))
        if not self.trends:
            c.create_text(self.WIDTH // 2, 48, text="감시 중인 ROI 없음", fill=T["muted"], font=(F, 9))
            return
        n = draw_roi_rows(c, self.trends, 4, 30, self.WIDTH - 8, self.ROW_H, self.MAX_ROWS, compact=True)
        if len(self.trends) > n:
            c.create_text(self.WIDTH // 2, 30 + n * self.ROW_H + 8, text=f"외 {len(self.trends) - n}개 ROI",
                          fill=T["dim"], font=(F, 8))

    def destroy(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


class TrendChart(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, bg=T["panel"], highlightthickness=1, highlightbackground=T["border"], height=180)
        self.series: List[Tuple[str, int]] = []
        self.bind("<Configure>", lambda _e: self._redraw())

    def draw(self, series):
        self.series = series
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50 or h < 60:
            return
        total = sum(c for _h, c in self.series)
        self.create_text(14, 14, anchor="w", text="NG TREND", fill=T["text"], font=("Segoe UI", 11, "bold"))
        self.create_text(100, 14, anchor="w", text="시간대별 NG (최근 12시간)", fill=T["muted"], font=(F, 8))
        self.create_text(w - 14, 14, anchor="e", text=f"합계 {total}건", fill=T["red"] if total else T["muted"],
                         font=(F, 9, "bold"))
        x0, y0, x1, y1 = 16, 36, w - 16, h - 22
        n = max(1, len(self.series))
        peak = max([c for _h, c in self.series] + [1])
        for i in range(1, 4):
            y = y1 - (y1 - y0) * i / 4
            self.create_line(x0, y, x1, y, fill="#18233b", dash=(2, 4))
        slot = (x1 - x0) / n
        for i, (hour, count) in enumerate(self.series):
            cx = x0 + slot * (i + 0.5)
            bw = max(4, slot * 0.55)
            bh = (y1 - y0) * count / peak if count else 2
            self.create_rectangle(cx - bw / 2, y1 - bh, cx + bw / 2, y1,
                                  fill=T["red"] if count else T["border"], outline="")
            if count:
                self.create_text(cx, y1 - bh - 8, text=str(count), fill=T["text"], font=("Segoe UI", 8, "bold"))
            self.create_text(cx, y1 + 10, text=hour, fill=T["dim"], font=("Segoe UI", 7))
        self.create_line(x0, y1, x1, y1, fill=T["border"])

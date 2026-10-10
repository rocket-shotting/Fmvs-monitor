"""관제센터 대시보드 구성요소 (다크 테마): KPI 타일, 카메라 월(자유 배치), 에이전트 활동 피드, NG 추이 차트."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageTk

import llm
from agent import FEED_KINDS, FeedItem
from config import WALL_MAX, WALL_MIN
from i18n import tr

F = "맑은 고딕"  # i18n: skip
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
    style.configure("Dark.Horizontal.TScrollbar", troughcolor=T["bg"], background=T["card"], bordercolor=T["bg"],
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
    W, H = 256, 144          # 기본(자동 배치) 화면 크기

    def __init__(self, master, roi_id: str):
        super().__init__(master, bg=T["card"], highlightthickness=2, highlightbackground=T["border"])
        self.roi_id = roi_id
        self.state = "idle"
        self.color = STATE_COLORS["idle"]
        self.meta = ""
        self.has_frame = False
        self.vw, self.vh = self.W, self.H
        self._photo = None
        self._rgb = None
        self._bg = T["card"]
        self.view = tk.Canvas(self, width=self.vw, height=self.vh, bg="#05080f", highlightthickness=0)
        self.view.pack(padx=6, pady=(6, 4))
        row = tk.Frame(self, bg=T["card"])
        row.pack(fill="x", padx=8)
        self.name = tk.Label(row, text="", bg=T["card"], fg=T["text"], font=(F, 10, "bold"), anchor="w")
        self.name.pack(side="left", fill="x", expand=True)
        self.pill = tk.Label(row, text=tr("대기"), bg=self.color, fg="#06101f", font=(F, 8, "bold"), padx=8)
        self.pill.pack(side="right")
        # 상세는 2줄 고정 – 상태 문구 길이에 따라 카드 높이가 바뀌어 옆 카드와 겹치지 않도록
        self.detail = tk.Label(self, text="", bg=T["card"], fg=T["muted"], font=(F, 8), anchor="nw",
                               justify="left", wraplength=self.vw, height=2)
        self.detail.pack(fill="x", padx=8, pady=(2, 10))
        self._row = row
        # 오른쪽 아래 모서리: 끌어서 크기 조절
        self.grip = tk.Label(self, text="◢", bg=T["card"], fg=T["dim"], font=("Segoe UI", 9),
                             cursor="size_nw_se", padx=1, pady=0)
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.drag_widgets = (self, self.view, row, self.name, self.pill, self.detail)
        self._placeholder()

    def set_meta(self, roi):
        self.name.configure(text=roi.name)
        self.meta = f"{roi.detector_label().split(' (')[0]} · {roi.w}×{roi.h}"
        if not self.has_frame:
            self._placeholder()

    def set_view_size(self, vw: int, vh: int):
        if (vw, vh) == (self.vw, self.vh):
            return
        self.vw, self.vh = vw, vh
        self.view.configure(width=vw, height=vh)
        self.detail.configure(wraplength=vw)
        if self.has_frame and self._rgb is not None:
            self.set_frame(self._rgb)
        else:
            self._placeholder()

    def set_state(self, state: str, detail: str):
        self.state = state
        self.color = STATE_COLORS.get(state, T["sky"])
        active = state not in ("idle", "off")
        self.configure(highlightbackground=self.color if active else T["border"])
        self.pill.configure(text=tr(STATE_SHORT.get(state, state)), bg=self.color)
        self.detail.configure(text=(detail[:110] + "…") if len(detail) > 110 else detail)
        self._hud()

    def set_frame(self, rgb):
        self._rgb = rgb
        img = Image.fromarray(rgb)
        scale = min(self.vw / img.width, self.vh / img.height)
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        if size != img.size:
            img = img.resize(size, Image.BILINEAR)
        canvas = Image.new("RGB", (self.vw, self.vh), (5, 8, 15))
        canvas.paste(img, ((self.vw - img.width) // 2, (self.vh - img.height) // 2))
        self._photo = ImageTk.PhotoImage(canvas)
        self.view.delete("all")
        self.view.create_image(0, 0, anchor="nw", image=self._photo)
        self.has_frame = True
        self._hud()

    def clear_frame(self):
        self.has_frame = False
        self._photo = self._rgb = None
        self._placeholder()

    def highlight(self, selected: bool):
        self._bg = T["card_hi"] if selected else T["card"]
        for w in (self, self._row, self.name, self.detail, self.grip):
            w.configure(bg=self._bg)

    def blink(self, on: bool):
        if self.state == "alarm":
            self.configure(highlightbackground=T["red"] if on else "#7f1d1d")

    def _placeholder(self):
        v, w, h = self.view, self.vw, self.vh
        v.delete("all")
        for x in range(0, w, 16):
            v.create_line(x, 0, x, h, fill="#0c1426")
        for y in range(0, h, 16):
            v.create_line(0, y, w, y, fill="#0c1426")
        v.create_text(w // 2, h // 2 - 8, text="STANDBY", fill=T["dim"], font=("Segoe UI", 14, "bold"))
        v.create_text(w // 2, h // 2 + 14, text=self.meta, fill=T["dim"], font=(F, 8))
        self._hud()

    def _hud(self):
        """HUD 스타일 모서리 표시 + LIVE 표시."""
        v, c, n, w, h = self.view, self.color, 16, self.vw - 2, self.vh - 2
        v.delete("hud")
        for x, y, dx, dy in ((2, 2, 1, 1), (w, 2, -1, 1), (2, h, 1, -1), (w, h, -1, -1)):
            v.create_line(x, y, x + dx * n, y, fill=c, width=2, tags="hud")
            v.create_line(x, y, x, y + dy * n, fill=c, width=2, tags="hud")
        if self.has_frame:
            v.create_rectangle(8, 8, 48, 24, fill="#000000", outline="", tags="hud")
            v.create_oval(13, 13, 19, 19, fill=T["red"] if self.state != "off" else T["slate"], outline="", tags="hud")
            v.create_text(34, 16, text="LIVE", fill="#ffffff", font=("Segoe UI", 7, "bold"), tags="hud")


class CameraWall(tk.Frame):
    """ROI 카드를 자유롭게 배치하는 카메라 월.

    - 카드를 끌면 이동, 오른쪽 아래 ◢를 끌면 화면 크기 조절 (8px 격자에 맞춤)
    - 직접 배치한 카드는 on_layout(roi_id, [x, y, 폭, 높이])로 저장되고, 나머지는 빈 자리에 자동 배치
    - 클릭: 선택, 더블클릭: 편집"""
    GAP = 12
    SNAP = 8
    DRAG_START = 5            # 이 거리(px) 이상 움직여야 끌기로 본다 (클릭과 구분)

    def __init__(self, master, on_select: Callable, on_open: Callable,
                 on_layout: Optional[Callable] = None):
        super().__init__(master, bg=T["bg"])
        self.on_select, self.on_open, self.on_layout = on_select, on_open, on_layout
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar")
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview,
                            style="Dark.Horizontal.TScrollbar")
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))
        self.cards: Dict[str, CameraCard] = {}
        self.items: Dict[str, int] = {}
        self.manual: Dict[str, list] = {}     # roi_id -> [x, y, 폭, 높이] (직접 배치)
        self.order: List[str] = []
        self._cols = 0
        self._width = 0
        self._drag: Optional[dict] = None
        self.empty = self.canvas.create_text(
            0, 0, text=tr("등록된 ROI가 없습니다\n상단의 [＋ ROI 추가]로 감시할 카메라 영역을 지정하세요"),
            fill=T["muted"], font=(F, 11), justify="center", state="hidden")

    # ---------- 배치 ----------
    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_resize(self, e):
        if e.width != self._width:
            self._width = e.width
            self._layout()

    def _card_size(self, card: CameraCard) -> Tuple[int, int]:
        return card.winfo_reqwidth(), card.winfo_reqheight()

    def _layout(self):
        """직접 배치한 카드는 저장된 위치에, 나머지는 겹치지 않는 빈 칸에 왼쪽 위부터 채운다."""
        self.canvas.itemconfigure(self.empty, state="hidden" if self.order else "normal")
        if not self.order:
            self.canvas.coords(self.empty, max(200, self._width // 2), 100)
            self._update_scroll()
            return
        self.update_idletasks()
        taken = []
        for rid in self.order:
            if rid in self.manual:
                x, y, _w, _h = self.manual[rid]
                card = self.cards[rid]
                cw, ch = self._card_size(card)
                self.canvas.coords(self.items[rid], x, y)
                taken.append((x, y, cw, ch))
        auto = [rid for rid in self.order if rid not in self.manual]
        if auto:
            cw, ch = self._card_size(self.cards[auto[0]])
            cell_w = cw + self.GAP
            width = max(self._width, cell_w + self.GAP)
            self._cols = max(1, (width - self.GAP) // cell_w)
            if not taken:
                # 직접 배치한 카드가 없으면 격자로 채우고 카드 묶음을 가운데 정렬
                used = min(self._cols, len(auto))
                x0 = max(self.GAP, (width - used * cell_w + self.GAP) // 2)
                for i, rid in enumerate(auto):
                    x = x0 + (i % self._cols) * cell_w
                    y = self.GAP + (i // self._cols) * (ch + self.GAP)
                    self.canvas.coords(self.items[rid], x, y)
                    taken.append((x, y, cw, ch))
            else:
                for rid in auto:
                    x, y = _free_spot(cw, ch, taken, width, self.GAP)
                    self.canvas.coords(self.items[rid], x, y)
                    taken.append((x, y, cw, ch))
        self._update_scroll()

    def _update_scroll(self):
        box = self.canvas.bbox("all") or (0, 0, 1, 1)
        self.canvas.configure(scrollregion=(0, 0, box[2] + self.GAP, box[3] + self.GAP))

    def set_rois(self, rois, states: Dict[str, Tuple[str, str]], running: bool):
        ids = [r.id for r in rois]
        for rid in list(self.cards):
            if rid not in ids:
                self.cards.pop(rid).destroy()
                self.canvas.delete(self.items.pop(rid))
        self.manual = {}
        for r in rois:
            card = self.cards.get(r.id)
            if card is None:
                card = self.cards[r.id] = CameraCard(self.canvas, r.id)
                self.items[r.id] = self.canvas.create_window(0, 0, window=card, anchor="nw")
                self._bind_card(card)
            wall = list(getattr(r, "wall", None) or [])
            if len(wall) == 4:
                self.manual[r.id] = wall
                card.set_view_size(wall[2], wall[3])
            else:
                card.set_view_size(CameraCard.W, CameraCard.H)
            card.set_meta(r)
            if not r.enabled:
                card.set_state("off", tr("사용 안 함"))
            elif running:
                card.set_state(*states.get(r.id, ("idle", tr("검사 준비 중"))))
            else:
                card.set_state("idle", tr("검출 대기 – ▶ 시작을 누르면 실시간 판정"))
            if not running and card.has_frame:
                card.clear_frame()
        self.order = ids
        self._layout()

    def view_sizes(self) -> Dict[str, int]:
        """ROI별 카드 화면의 긴 변 (썸네일 해상도 결정용)."""
        return {rid: max(card.vw, card.vh) for rid, card in self.cards.items()}

    # ---------- 끌어서 이동 / 크기 조절 ----------
    def _bind_card(self, card: CameraCard):
        rid = card.roi_id
        for w in card.drag_widgets:
            w.bind("<ButtonPress-1>", lambda e, r=rid: self._press(r, e, "move"))
            w.bind("<B1-Motion>", self._motion)
            w.bind("<ButtonRelease-1>", self._release)
            w.bind("<Double-1>", lambda _e, r=rid: self.on_open(r))
        card.grip.bind("<ButtonPress-1>", lambda e, r=rid: self._press(r, e, "resize"))
        card.grip.bind("<B1-Motion>", self._motion)
        card.grip.bind("<ButtonRelease-1>", self._release)

    def _press(self, rid: str, e, mode: str):
        card = self.cards[rid]
        x, y = self.canvas.coords(self.items[rid])
        self._drag = {"rid": rid, "mode": mode, "x0": e.x_root, "y0": e.y_root, "pos": (x, y),
                      "size": (card.vw, card.vh), "moved": False}
        card.lift()

    def _motion(self, e):
        d = self._drag
        if d is None:
            return
        dx, dy = e.x_root - d["x0"], e.y_root - d["y0"]
        if not d["moved"] and abs(dx) < self.DRAG_START and abs(dy) < self.DRAG_START:
            return
        d["moved"] = True
        card = self.cards[d["rid"]]
        if d["mode"] == "move":
            x = max(0, _snap(d["pos"][0] + dx, self.SNAP))
            y = max(0, _snap(d["pos"][1] + dy, self.SNAP))
            self.canvas.coords(self.items[d["rid"]], x, y)
        else:
            vw = min(WALL_MAX[0], max(WALL_MIN[0], _snap(d["size"][0] + dx, self.SNAP)))
            vh = min(WALL_MAX[1], max(WALL_MIN[1], _snap(d["size"][1] + dy, self.SNAP)))
            card.set_view_size(vw, vh)

    def _release(self, _e):
        d, self._drag = self._drag, None
        if d is None:
            return
        rid = d["rid"]
        if not d["moved"]:
            if d["mode"] == "move":
                self.on_select(rid)
            return
        card = self.cards[rid]
        x, y = (int(v) for v in self.canvas.coords(self.items[rid]))
        self.manual[rid] = [x, y, card.vw, card.vh]
        self._layout()                       # 자동 배치 카드가 새 자리를 피하도록
        if self.on_layout:
            self.on_layout(rid, list(self.manual[rid]))

    # ---------- 상태 ----------
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


def _free_spot(w: int, h: int, taken, width: int, gap: int) -> Tuple[int, int]:
    """이미 놓인 카드와 겹치지 않는 가장 위·왼쪽 자리 (bottom-left packing).
    후보 = 왼쪽 끝·위쪽 끝 + 기존 카드의 오른쪽·아래쪽 바로 옆."""
    xs = sorted({gap} | {x + cw + gap for x, _y, cw, _ch in taken})
    ys = sorted({gap} | {y + ch + gap for _x, y, _cw, ch in taken})
    grown = [(x - gap + 1, y - gap + 1, cw + 2 * gap - 2, ch + 2 * gap - 2) for x, y, cw, ch in taken]
    for y in ys:
        for x in xs:
            if x + w + gap > width and x != gap:
                continue
            if not any(_overlap((x, y, w, h), r) for r in grown):
                return x, y
    return gap, max(y + ch for _x, y, _cw, ch in taken) + gap


def _snap(v: float, step: int) -> int:
    return int(round(v / step)) * step


def _overlap(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


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
        tk.Label(head, text=tr("에이전트 관찰·판단·실행·학습 + 시스템 기록"), bg=T["panel"], fg=T["muted"],
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
        t.insert("end", f"{icon} {tr(name)}  ", item.kind)
        t.insert("end", item.text + "\n", "body")
        excess = int(t.index("end-1c").split(".")[0]) - self.MAX_LINES
        if excess > 0:
            t.delete("1.0", f"{excess + 1}.0")
        t.see("end")
        t.configure(state="disabled")

    def pulse(self, running: bool, on: bool):
        self.dot.configure(fg=(T["green"] if on else "#14532d") if running else T["dim"])


SYS_KINDS = {"sys": ("·", "로그"), "error": ("✖", "오류")}


class AdvisorPanel(tk.Frame):
    """의견 에이전트 패널: 운영 개선 의견 카드 + (LLM 연결 시) 종합 의견·질문 답변."""
    LEVEL_COLORS = {"critical": T["red"], "warn": T["amber"], "info": T["sky"], "llm": T["indigo"],
                    "example": T["dim"]}
    ACTION_TEXT = {"samples": "샘플 열기", "edit": "ROI 편집", "settings": "설정 열기"}

    def __init__(self, master, hidden: set, on_action: Callable, on_refresh: Callable,
                 on_ask: Callable, on_summary: Callable):
        super().__init__(master, bg=T["panel"], highlightthickness=1, highlightbackground=T["border"])
        self.hidden = hidden
        self.on_action, self.on_ask = on_action, on_ask
        self.items: list = []
        self.answers: List[Tuple[str, str, bool]] = []     # (질문, 답, 오류)
        self.llm_label: Optional[str] = None
        self._bodies: List[tk.Label] = []
        head = tk.Frame(self, bg=T["panel"])
        head.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(head, text="💡 AGENT ADVISOR", bg=T["panel"], fg=T["text"],
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        self.mode = tk.Label(head, text="", bg=T["panel"], fg=T["muted"], font=(F, 8))
        self.mode.pack(side="left", padx=8)
        FlatButton(head, tr("⟳ 다시 분석"), on_refresh, padx=8, pady=2).pack(side="right")
        self.btn_summary = FlatButton(head, tr("✦ LLM 종합 의견"), on_summary, padx=8, pady=2)
        self.btn_summary.pack(side="right", padx=(0, 6))
        self.when = tk.Label(self, text="", bg=T["panel"], fg=T["dim"], font=(F, 8), anchor="w")
        self.when.pack(fill="x", padx=12)

        ask = tk.Frame(self, bg=T["panel"])
        ask.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
        self.question = tk.Entry(ask, bg=T["card"], fg=T["text"], insertbackground=T["text"], relief="flat",
                                 font=(F, 9), highlightthickness=1, highlightbackground=T["border"])
        self.question.pack(side="left", fill="x", expand=True, ipady=4)
        self.question.bind("<Return>", lambda _e: self._ask())
        self.btn_ask = FlatButton(ask, tr("묻기"), self._ask, kind="primary", padx=12, pady=3)
        self.btn_ask.pack(side="left", padx=(6, 0))

        body = tk.Frame(self, bg=T["panel"])
        body.pack(fill="both", expand=True, padx=(12, 4), pady=4)
        self.canvas = tk.Canvas(body, bg=T["panel"], highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T["panel"])
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_resize(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        for lbl in self._bodies:
            lbl.configure(wraplength=max(200, e.width - 40))

    def _ask(self):
        q = self.question.get().strip()
        if q:
            self.question.delete(0, "end")
            self.on_ask(q)

    # ---------- 표시 ----------
    def show(self, items, llm_label: Optional[str], when: str):
        self.items, self.llm_label = list(items), llm_label
        self.when.configure(text=tr("마지막 분석 {when} · 검출 기록·샘플·설정 기반", when=when))
        self._render()

    def show_answer(self, question: str, text: str, error: bool = False):
        self.answers.insert(0, (question, text, error))
        del self.answers[10:]
        self._render()

    def set_busy(self, busy: bool):
        self.btn_ask.set_enabled(not busy)
        self.btn_summary.set_enabled(not busy and self.llm_label is not None)

    def visible_count(self) -> Tuple[int, int]:
        """(표시 중인 의견 수, 그중 주의·긴급 수)."""
        shown = [a for a in self.items if a.key not in self.hidden]
        return len(shown), sum(1 for a in shown if a.level in ("critical", "warn"))

    def _render(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self._bodies = []
        if self.llm_label:
            self.mode.configure(text=tr("규칙 분석 + LLM ({model})", model=self.llm_label), fg=T["green"])
        else:
            self.mode.configure(text=tr("규칙 분석 · LLM 미연결"), fg=T["muted"])
        self.btn_summary.set_enabled(self.llm_label is not None)
        for q, text, error in self.answers:
            self._card("llm", ("⚠ " if error else "✦ ") + (q if len(q) <= 60 else q[:60] + "…"), text)
        shown = [a for a in self.items if a.key not in self.hidden]
        for a in shown:
            self._card(a.level, a.title, a.body, a)
        if not shown:
            self._card("info", tr("✔ 지금은 개선 의견이 없습니다"),
                       tr("검출 기록·샘플·설정에서 문제를 찾지 못했습니다. 5분마다 다시 분석합니다."))
        if self.llm_label is None and not self.answers:
            self._card("example", tr("✦ LLM 연결 시 (예시)"),
                       llm.example_answer() + "\n\n" +
                       tr("설정 → LLM 연결에서 이 PC 또는 사내 서버의 LLM(Ollama·LM Studio 등)을 켜면 "
                          "위 같은 종합 의견과 질문 답변을 받을 수 있습니다. 화면·이미지는 보내지 않습니다."))
        if self.hidden:
            row = tk.Frame(self.inner, bg=T["panel"])
            row.pack(fill="x", pady=(2, 6))
            tk.Label(row, text=tr("숨긴 의견 {n}개", n=len(self.hidden)), bg=T["panel"], fg=T["dim"],
                     font=(F, 8)).pack(side="left")
            FlatButton(row, tr("다시 보기"), self._unhide, padx=6, pady=1, font=(F, 8)).pack(side="left", padx=6)
        width = self.canvas.winfo_width()
        if width > 50:
            for lbl in self._bodies:
                lbl.configure(wraplength=max(200, width - 40))

    def _card(self, level: str, title: str, body: str, advice=None):
        color = self.LEVEL_COLORS.get(level, T["sky"])
        card = tk.Frame(self.inner, bg=T["card"])
        card.pack(fill="x", pady=(0, 6))
        tk.Frame(card, bg=color, width=4).pack(side="left", fill="y")
        box = tk.Frame(card, bg=T["card"])
        box.pack(side="left", fill="both", expand=True, padx=10, pady=6)
        tk.Label(box, text=title, bg=T["card"], fg=T["text"] if level != "example" else T["muted"],
                 font=(F, 9, "bold"), anchor="w", justify="left").pack(fill="x")
        lbl = tk.Label(box, text=body, bg=T["card"], fg=T["muted"], font=(F, 8), anchor="w", justify="left",
                       wraplength=360)
        lbl.pack(fill="x", pady=(2, 0))
        self._bodies.append(lbl)
        if advice is not None:
            row = tk.Frame(box, bg=T["card"])
            row.pack(fill="x", pady=(4, 0))
            if advice.action:
                FlatButton(row, tr(self.ACTION_TEXT[advice.action]),
                           lambda a=advice: self.on_action(a), padx=8, pady=1, font=(F, 8, "bold")).pack(side="left")
            FlatButton(row, tr("숨기기"), lambda k=advice.key: self._hide(k), padx=8, pady=1,
                       font=(F, 8)).pack(side="left", padx=4)

    def _hide(self, key: str):
        self.hidden.add(key)
        self._render()

    def _unhide(self):
        self.hidden.clear()
        self._render()


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
    """ROI별 NG 추이 (최근 12시간, 시간대별) – 메인 화면 오른쪽 아래."""
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
        self.create_text(w - 14, 16, anchor="e", text=tr("ROI별 NG 추이 · 최근 12시간"), fill=T["muted"], font=(F, 8))
        self.create_text(14 + 150 + 40, 38, anchor="e", text="NG", fill=T["muted"], font=(F, 8))
        if self.trends:
            hours = self.trends[0]["series"]
            bx0, bx1 = 14 + 150 + 46, w - 20
            slot = (bx1 - bx0) / max(1, len(hours))
            for j, (hour, _c) in enumerate(hours):
                if j % 3 == 0:
                    self.create_text(bx0 + slot * (j + 0.5), 38, text=tr("{h}시", h=hour), fill=T["dim"], font=("Segoe UI", 7))
        else:
            self.create_text(w // 2, h // 2, text=tr("ROI를 추가하면 여기서 ROI별 NG 추이를 볼 수 있습니다"),
                             fill=T["muted"], font=(F, 9))
            return
        max_rows = max(1, (h - 48 - 18) // self.ROW_H)
        if len(self.trends) <= (h - 48 - 4) // self.ROW_H:
            max_rows = len(self.trends)             # 다 들어가면 안내 문구 자리 없이 모두 표시
        n = draw_roi_rows(self, self.trends, 8, 48, w - 16, self.ROW_H, max_rows)
        if len(self.trends) > n:
            self.create_text(w // 2, h - 8, text=tr("외 {n}개 ROI (창을 키우면 더 보입니다)", n=len(self.trends) - n),
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
        FlatButton(head, tr("대시보드 열기"), self.on_open, padx=8, pady=2, font=(F, 8, "bold")).pack(side="right", pady=3)
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
        c.create_text(10, 14, anchor="w", text=text or tr("● 실시간 감시 중"), fill=color, font=(F, 9, "bold"))
        c.create_text(self.WIDTH - 10, 14, anchor="e", text=tr("NG · 최근 12시간"), fill=T["muted"], font=(F, 8))
        if not self.trends:
            c.create_text(self.WIDTH // 2, 48, text=tr("감시 중인 ROI 없음"), fill=T["muted"], font=(F, 9))
            return
        n = draw_roi_rows(c, self.trends, 4, 30, self.WIDTH - 8, self.ROW_H, self.MAX_ROWS, compact=True)
        if len(self.trends) > n:
            c.create_text(self.WIDTH // 2, 30 + n * self.ROW_H + 8, text=tr("외 {n}개 ROI", n=len(self.trends) - n),
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
        self.create_text(100, 14, anchor="w", text=tr("시간대별 NG (최근 12시간)"), fill=T["muted"], font=(F, 8))
        self.create_text(w - 14, 14, anchor="e", text=tr("합계 {n}건", n=total), fill=T["red"] if total else T["muted"],
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

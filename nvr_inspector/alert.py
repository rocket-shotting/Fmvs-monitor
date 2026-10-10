"""검출 팝업. ROI당 하나만 띄우고, 오른쪽 위 X 또는 [확인]으로 닫는다.

- 탐지 시각(이 PC의 로컬 시간)을 크게 표시하고, 같은 ROI의 최근 탐지 기록을 함께 보여준다.
- 팝업은 감시 중인 ROI 좌표와 다른 팝업을 피해서 배치한다 (ROI를 가리면 판정이 막히므로).
- 복구되면 같은 팝업이 초록색 '복구됨'으로 바뀐다."""
import os
import tkinter as tk
from collections import deque
from typing import Callable, Dict, List, Optional, Tuple

import detectors
import notifier
import winutil
from i18n import tr

_RED = "#c62828"
_GREEN = "#2e7d32"
_WIDTH = 480
_MARGIN = 14              # ROI와 팝업 사이 최소 간격(px)
_HISTORY = 6
F = "맑은 고딕"  # i18n: skip

Rect = Tuple[int, int, int, int]


def _overlap(a: Rect, b: Rect) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    return w * h if w > 0 and h > 0 else 0


def find_free_spot(w: int, h: int, screen: Rect, blocked: List[Rect]) -> Tuple[int, int]:
    """screen 안에서 blocked 사각형들과 겹치지 않는 위치 (오른쪽 아래 우선).
    빈 곳이 없으면 겹치는 면적이 가장 작은 위치."""
    sx, sy, sw, sh = screen
    grown = [(x - _MARGIN, y - _MARGIN, bw + 2 * _MARGIN, bh + 2 * _MARGIN) for x, y, bw, bh in blocked]
    best, best_cost = None, None
    for y in range(sy + sh - h - 50, sy + 9, -24):
        for x in range(sx + sw - w - 16, sx + 9, -32):
            cost = sum(_overlap((x, y, w, h), r) for r in grown)
            if cost == 0:
                return x, y
            if best_cost is None or cost < best_cost:
                best, best_cost = (x, y), cost
    return best or (max(sx, sx + sw - w - 16), sy + 10)


class AlertPopup:
    placed = False

    def __init__(self, manager: "AlertManager", roi_id: str):
        self.manager = manager
        self.roi_id = roi_id
        self.history: deque = deque(maxlen=_HISTORY)
        self.count = 0
        self.win = tk.Toplevel(manager.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=_RED, padx=2, pady=2)

        inner = tk.Frame(self.win, bg="white")
        inner.pack(fill="both", expand=True)

        self.header = tk.Frame(inner, bg=_RED)
        self.header.pack(fill="x")
        self.title_label = tk.Label(self.header, text="", bg=_RED, fg="white",
                                    font=(F, 12, "bold"), anchor="w", padx=10, pady=6)
        self.title_label.pack(side="left", fill="x", expand=True)
        self.close_label = tk.Label(self.header, text="✕", bg=_RED, fg="white", cursor="hand2",
                                    font=(F, 12, "bold"), padx=10, pady=6)
        self.close_label.pack(side="right")
        self.close_label.bind("<Button-1>", lambda _e: self.close())
        self.close_label.bind("<Enter>", lambda _e: self.close_label.configure(bg="#000000"))
        self.close_label.bind("<Leave>", lambda _e: self.close_label.configure(bg=self.header["bg"]))
        for w in (self.header, self.title_label):          # 헤더를 잡고 끌어서 이동
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # 탐지 시각 (PC 로컬 시간) – 크게
        self._when_box = tk.Frame(inner, bg="#fff5f5", padx=12, pady=8)
        self._when_box.pack(fill="x")
        self.when_caption = tk.Label(self._when_box, text=tr("탐지 시각 (이 PC 시간)"), bg="#fff5f5", fg="#7f1d1d",
                                     font=(F, 9, "bold"), anchor="w")
        self.when_caption.pack(anchor="w")
        self.when_label = tk.Label(self._when_box, text="", bg="#fff5f5", fg="#111111",
                                   font=("Segoe UI", 22, "bold"), anchor="w")
        self.when_label.pack(anchor="w")

        self.body = tk.Label(inner, text="", bg="white", justify="left", anchor="w",
                             font=(F, 10), padx=12, pady=8, wraplength=_WIDTH - 30)
        self.body.pack(fill="both", expand=True)
        self.history_label = tk.Label(inner, text="", bg="white", fg="#555555", justify="left", anchor="w",
                                      font=(F, 9), padx=12, wraplength=_WIDTH - 30)
        self.history_label.pack(fill="x")

        buttons = tk.Frame(inner, bg="white", pady=8)
        buttons.pack(fill="x")
        tk.Button(buttons, text=tr("확인"), width=8, command=self.close).pack(side="right", padx=10)
        self.snapshot_btn = tk.Button(buttons, text=tr("스냅샷"), width=7, command=self._open_snapshot)
        # 경보 화면을 바로 샘플로 등록 (실제 불량이면 NG, 오탐이면 OK, 셀 없음/이동 중이면 무시)
        self.reg_labels = {"ng": tr("NG로 등록"), "ok": tr("OK로 등록(오탐)"), "skip": tr("무시로 등록(셀 없음)")}
        self.reg_buttons = {cls: tk.Button(buttons, text=text, command=lambda c=cls: self._register(c))
                            for cls, text in self.reg_labels.items()}
        self._raw = None
        self._snapshot = None
        self._drag = (0, 0)
        self.user_moved = False

    def _drag_start(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag_move(self, e):
        self.user_moved = True
        self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _set_color(self, color, tint, caption_fg, caption):
        self.win.configure(bg=color)
        for w in (self.header, self.title_label, self.close_label):
            w.configure(bg=color)
        for w in (self._when_box, self.when_caption, self.when_label):
            w.configure(bg=tint)
        self.when_caption.configure(text=caption, fg=caption_fg)

    def show(self, info: dict, recovered: bool):
        if recovered:
            self._set_color(_GREEN, "#f0fdf4", "#14532d", tr("복구 시각 (이 PC 시간)"))
            self.title_label.configure(text=tr("✅ 복구됨 – {name}", name=info["roi_name"]))
            lines = [tr("화면이 정상으로 돌아왔습니다."),
                     tr("현재 값: {value}", value=info["detail"])]
            if info.get("elapsed"):
                lines.append(tr("이상 지속 시간: {duration}", duration=notifier.fmt_duration(info.get("elapsed"))))
        else:
            self.count += 1
            self.history.appendleft(info["time"])
            self._set_color(_RED, "#fff5f5", "#7f1d1d", tr("탐지 시각 (이 PC 시간)"))
            title = tr("🚨 이상 지속 (재알림)") if info["kind"] == "repeat" else tr("🚨 이상 탐지")
            self.title_label.configure(text=f"{title} – {info['roi_name']}")
            lines = [tr("검출 유형: {detector}", detector=info["detector"]),
                     tr("측정값: {value}", value=info["detail"]),
                     tr("담당자: {assignee}", assignee=info.get("assignee") or tr("미지정"))]
            if info.get("elapsed"):
                lines.insert(2, tr("지속 시간: {duration}", duration=notifier.fmt_duration(info.get("elapsed"))))
            if info.get("consecutive", 1) > 1:
                lines.insert(0, tr("연속 NG {n}회", n=info["consecutive"]))
            snap = info.get("snapshot")
            if snap and os.path.exists(snap) and hasattr(os, "startfile"):
                self._snapshot = snap
                self.snapshot_btn.pack(side="right")
            raw = info.get("raw_snapshot")
            if raw and os.path.exists(raw) and info.get("roi_detector") in detectors.REFERENCE_KINDS \
                    and self.manager.on_register is not None:
                self._raw = raw
                for i, (cls, btn) in enumerate(self.reg_buttons.items()):
                    btn.configure(state="normal", text=self.reg_labels[cls])
                    btn.pack(side="left", padx=(10 if i == 0 else 2, 2))
        self.when_label.configure(text=info["time"])
        if not recovered and info.get("nvr_time"):        # NVR 화면 시간을 읽었으면 그것을 크게, PC 시간은 작게
            self.when_caption.configure(text=tr("NVR 화면 시간 ({source}) · PC {pc}", source=info.get("nvr_source", ""),
                                                pc=info["time"][-8:]))
            self.when_label.configure(text=info["nvr_time"])
        older = list(self.history)[1:]
        if not recovered:
            self.total = info.get("total_ng", self.count)
        if self.count:
            head = tr("이 ROI 누적 탐지 {n}회", n=getattr(self, "total", self.count))
            self.history_label.configure(text=head + (tr(" · 이전 탐지: {times}", times=", ".join(t[-8:] for t in older))
                                                      if older else ""))
        if not recovered and info.get("ai"):
            lines.append("")
            lines.append(tr("✦ AI 분석: {text}", text=info["ai"]))
        self.body.configure(text="\n".join(lines))
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)

    def update_nvr(self, nvr_time: str, source: str, renamed: dict):
        """NVR 화면 시간을 다 읽은 뒤(1~5초 후): 팝업 시간을 NVR 시간으로, 바뀐 스냅샷 파일 경로 반영."""
        pc = self.when_label.cget("text")
        self.when_caption.configure(text=tr("NVR 화면 시간 ({source}) · PC {pc}", source=source, pc=pc[-8:]))
        self.when_label.configure(text=nvr_time)
        if self._snapshot in renamed:
            self._snapshot = renamed[self._snapshot]
        if self._raw in renamed:
            self._raw = renamed[self._raw]

    def show_analysis(self, text: str):
        """LLM 자동 NG 분석 결과를 팝업 아래쪽에 덧붙인다."""
        self.body.configure(text=self.body.cget("text") + "\n\n" + tr("✦ AI 분석: {text}", text=text))
        self.place()

    def _register(self, cls: str):
        if not self._raw:
            return
        error = self.manager.on_register(self.roi_id, cls, self._raw)
        btn = self.reg_buttons[cls]
        if error:
            btn.configure(text=tr("등록 실패"))
            self.body.configure(text=self.body.cget("text") + f"\n⚠ {error}")
        else:
            btn.configure(text=tr("등록됨 ✔"), state="disabled")

    def _open_snapshot(self):
        if self._snapshot and os.path.exists(self._snapshot):
            os.startfile(self._snapshot)  # type: ignore[attr-defined]

    def rect(self) -> Rect:
        return (self.win.winfo_x(), self.win.winfo_y(), self.win.winfo_width(), self.win.winfo_height())

    def place(self):
        """ROI 좌표와 다른 팝업을 피해 배치 (사용자가 직접 옮긴 팝업은 그대로 둔다)."""
        if self.user_moved:
            return
        self.win.update_idletasks()
        h = self.win.winfo_reqheight()
        screen = (0, 0, self.win.winfo_screenwidth(), self.win.winfo_screenheight())   # 주 모니터
        blocked = list(self.manager.avoid_rects())
        blocked += [p.rect() for rid, p in self.manager.popups.items() if rid != self.roi_id and p.placed]
        x, y = find_free_spot(_WIDTH, h, screen, blocked)
        self.win.geometry(f"{_WIDTH}x{h}+{x}+{y}")
        self.win.update_idletasks()
        self.placed = True

    def close(self):
        self.manager.remove(self.roi_id)
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class AlertManager:
    def __init__(self, root: tk.Tk, on_register=None, avoid_rects: Optional[Callable[[], List[Rect]]] = None):
        """on_register(roi_id, cls, raw_path) -> 오류 메시지('' = 성공).
        avoid_rects() -> 팝업이 가리면 안 되는 화면 영역 (감시 중인 ROI 좌표)."""
        self.root = root
        self.on_register = on_register
        self.avoid_rects = avoid_rects or (lambda: [])
        self.popups: Dict[str, AlertPopup] = {}
        self.sound_enabled = True

    def alert(self, info: dict):
        popup = self.popups.get(info["roi_id"])
        if popup is None:
            popup = AlertPopup(self, info["roi_id"])
            self.popups[info["roi_id"]] = popup
        popup.show(info, recovered=False)
        popup.place()          # 내용 높이가 바뀔 수 있으므로 매번 다시 배치
        if self.sound_enabled:
            winutil.beep()

    def recover(self, info: dict):
        popup = self.popups.get(info["roi_id"])
        if popup is not None:
            popup.show(info, recovered=True)
            popup.place()

    def remove(self, roi_id: str):
        self.popups.pop(roi_id, None)

    def close_all(self):
        for popup in list(self.popups.values()):
            popup.close()

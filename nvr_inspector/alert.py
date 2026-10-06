"""검출 팝업. ROI당 하나만 띄우고, 오른쪽 위 X 또는 [확인]으로 닫는다.
복구되면 같은 팝업이 초록색 '복구됨'으로 바뀐다."""
import os
import tkinter as tk
from typing import Dict

import detectors
import notifier
import winutil

_RED = "#c62828"
_GREEN = "#2e7d32"
_WIDTH = 460


class AlertPopup:
    def __init__(self, manager: "AlertManager", roi_id: str):
        self.manager = manager
        self.roi_id = roi_id
        self.win = tk.Toplevel(manager.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=_RED, padx=2, pady=2)

        inner = tk.Frame(self.win, bg="white")
        inner.pack(fill="both", expand=True)

        self.header = tk.Frame(inner, bg=_RED)
        self.header.pack(fill="x")
        self.title_label = tk.Label(self.header, text="", bg=_RED, fg="white",
                                    font=("맑은 고딕", 12, "bold"), anchor="w", padx=10, pady=6)
        self.title_label.pack(side="left", fill="x", expand=True)
        self.close_label = tk.Label(self.header, text="✕", bg=_RED, fg="white", cursor="hand2",
                                    font=("맑은 고딕", 12, "bold"), padx=10, pady=6)
        self.close_label.pack(side="right")
        self.close_label.bind("<Button-1>", lambda _e: self.close())
        self.close_label.bind("<Enter>", lambda _e: self.close_label.configure(bg="#000000"))
        self.close_label.bind("<Leave>", lambda _e: self.close_label.configure(bg=self.header["bg"]))

        # 헤더를 잡고 끌어서 팝업 이동
        for w in (self.header, self.title_label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        self.body = tk.Label(inner, text="", bg="white", justify="left", anchor="w",
                             font=("맑은 고딕", 10), padx=12, pady=10, wraplength=_WIDTH - 30)
        self.body.pack(fill="both", expand=True)

        buttons = tk.Frame(inner, bg="white", pady=6)
        buttons.pack(fill="x")
        tk.Button(buttons, text="확인", width=10, command=self.close).pack(side="right", padx=10)
        self.snapshot_btn = tk.Button(buttons, text="스냅샷 보기", width=10, command=self._open_snapshot)
        # 경보 화면을 바로 샘플로 등록 (오탐이면 OK, 실제 불량이면 NG)
        self.ok_btn = tk.Button(buttons, text="OK로 등록(오탐)", command=lambda: self._register("ok"))
        self.ng_btn = tk.Button(buttons, text="NG로 등록", command=lambda: self._register("ng"))
        self._raw = None
        self._snapshot = None
        self._drag = (0, 0)

    def _drag_start(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag_move(self, e):
        self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _set_color(self, color):
        self.win.configure(bg=color)
        for w in (self.header, self.title_label, self.close_label):
            w.configure(bg=color)

    def show(self, info: dict, recovered: bool):
        if recovered:
            self._set_color(_GREEN)
            self.title_label.configure(text=f"✅ 복구됨 – {info['roi_name']}")
            lines = [f"화면이 정상으로 돌아왔습니다. ({info['time']})",
                     f"이상 지속 시간: {notifier.fmt_duration(info.get('elapsed'))}",
                     f"현재 값: {info['detail']}"]
        else:
            self._set_color(_RED)
            title = "🚨 이상 지속 (재알림)" if info["kind"] == "repeat" else "🚨 화면 이상 감지"
            self.title_label.configure(text=f"{title} – {info['roi_name']}")
            lines = [f"검출 유형: {info['detector']}",
                     f"측정값: {info['detail']}",
                     f"지속 시간: {notifier.fmt_duration(info.get('elapsed'))}",
                     f"담당자: {info.get('assignee') or '미지정'}",
                     f"시각: {info['time']}"]
            snap = info.get("snapshot")
            if snap and os.path.exists(snap) and hasattr(os, "startfile"):
                self._snapshot = snap
                self.snapshot_btn.pack(side="right")
            raw = info.get("raw_snapshot")
            detector = info.get("roi_detector")
            if raw and os.path.exists(raw) and detector in detectors.REFERENCE_KINDS \
                    and self.manager.on_register is not None:
                self._raw = raw
                for btn in (self.ok_btn, self.ng_btn):
                    btn.configure(state="normal")
                self.ng_btn.configure(text="NG로 등록")
                self.ok_btn.configure(text="OK로 등록(오탐)")
                if detector == "match":
                    self.ng_btn.pack(side="left", padx=(10, 2))
                self.ok_btn.pack(side="left", padx=(10 if detector != "match" else 2, 2))
        self.body.configure(text="\n".join(lines))
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)

    def _register(self, cls: str):
        if not self._raw:
            return
        error = self.manager.on_register(self.roi_id, cls, self._raw)
        btn = self.ok_btn if cls == "ok" else self.ng_btn
        if error:
            btn.configure(text="등록 실패")
            self.body.configure(text=self.body.cget("text") + f"\n⚠ {error}")
        else:
            btn.configure(text="등록됨 ✔", state="disabled")

    def _open_snapshot(self):
        if self._snapshot and os.path.exists(self._snapshot):
            os.startfile(self._snapshot)  # type: ignore[attr-defined]

    def place(self, index: int):
        self.win.update_idletasks()
        h = self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = sw - _WIDTH - 20
        y = max(10, sh - 60 - (h + 10) * (index + 1))
        self.win.geometry(f"{_WIDTH}x{h}+{x}+{y}")

    def close(self):
        self.manager.remove(self.roi_id)
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class AlertManager:
    def __init__(self, root: tk.Tk, on_register=None):
        """on_register(roi_id, cls, raw_path) -> 오류 메시지('' = 성공)."""
        self.root = root
        self.on_register = on_register
        self.popups: Dict[str, AlertPopup] = {}
        self.sound_enabled = True

    def alert(self, info: dict):
        popup = self.popups.get(info["roi_id"])
        is_new = popup is None
        if is_new:
            popup = AlertPopup(self, info["roi_id"])
            self.popups[info["roi_id"]] = popup
        popup.show(info, recovered=False)
        if is_new:
            popup.place(len(self.popups) - 1)
        if self.sound_enabled:
            winutil.beep()

    def recover(self, info: dict):
        popup = self.popups.get(info["roi_id"])
        if popup is not None:
            popup.show(info, recovered=True)

    def remove(self, roi_id: str):
        self.popups.pop(roi_id, None)

    def close_all(self):
        for popup in list(self.popups.values()):
            popup.close()

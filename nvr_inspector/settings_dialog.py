"""공통 설정 창 (검사 주기, Teams 공통 Webhook, 팝업/소리, 자동 시작)."""
import copy
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

import notifier
from config import AppConfig
from ui_util import modal


class SettingsDialog:
    def __init__(self, master: tk.Misc, cfg: AppConfig):
        self.master = master
        self.cfg = copy.deepcopy(cfg)
        self.result: Optional[AppConfig] = None
        top = self.top = tk.Toplevel(master)
        top.title("설정")
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self._cancel)
        body = ttk.Frame(top, padding=12)
        body.pack(fill="both", expand=True)

        general = ttk.LabelFrame(body, text="검출", padding=8)
        general.pack(fill="x", pady=(0, 8))
        self.v_interval = tk.StringVar(value=f"{cfg.interval_sec:g}")
        self.v_pc = tk.StringVar(value=cfg.pc_label)
        self.v_popup = tk.BooleanVar(value=cfg.popup_enabled)
        self.v_sound = tk.BooleanVar(value=cfg.sound_enabled)
        self.v_auto = tk.BooleanVar(value=cfg.auto_start)
        self.v_minimize = tk.BooleanVar(value=cfg.minimize_on_start)
        self.v_overlay = tk.BooleanVar(value=cfg.show_overlay)
        self.v_badge = tk.BooleanVar(value=cfg.show_badge)
        ttk.Label(general, text="검사 주기(초, 0.2~60)").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(general, textvariable=self.v_interval, width=8).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(general, text="PC 표시 이름(알림에 표시)").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(general, textvariable=self.v_pc, width=24).grid(row=1, column=1, sticky="w", padx=6)
        checks = (("검출 시 팝업 표시", self.v_popup),
                  ("검출 시 경고음", self.v_sound),
                  ("프로그램 시작 시 검출 자동 시작", self.v_auto),
                  ("검출 시작 시 이 창 최소화 (창이 ROI를 가리지 않도록)", self.v_minimize),
                  ("검출 중 화면에 ROI 위치·상태 테두리 표시 (클릭 통과, 캡처에 안 찍힘)", self.v_overlay),
                  ("검출 중 화면 모서리에 '동작 중' 배지 표시", self.v_badge))
        for i, (text, var) in enumerate(checks, start=2):
            ttk.Checkbutton(general, text=text, variable=var).grid(row=i, column=0, columnspan=2, sticky="w")

        teams = ttk.LabelFrame(body, text="Teams 알림 (Power Automate Workflows 웹훅)", padding=8)
        teams.pack(fill="x")
        self.v_teams = tk.BooleanVar(value=cfg.teams_enabled)
        self.v_webhook = tk.StringVar(value=cfg.webhook_url)
        ttk.Checkbutton(teams, text="Teams 알림 사용", variable=self.v_teams).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(teams, text="공통 Webhook URL").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(teams, textvariable=self.v_webhook, width=60).grid(row=1, column=1, sticky="we", padx=6)
        ttk.Label(teams, text="Teams → 워크플로 → 'Webhook 요청 수신 시 채팅/채널에 게시' 흐름을 만들고\n"
                              "생성된 URL을 붙여넣으세요. 자세한 방법은 README 참고.\n"
                              "※ URL에 인증 서명이 들어 있으니 외부에 공유하지 마세요.",
                  foreground="#555555", justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="저장", width=12, command=self._save).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="취소", width=12, command=self._cancel).pack(side="right")
        top.bind("<Escape>", lambda _e: self._cancel())

    def _save(self):
        try:
            interval = float(self.v_interval.get())
        except ValueError:
            messagebox.showerror("입력 오류", "검사 주기는 숫자로 입력하세요.", parent=self.top)
            return
        if not 0.2 <= interval <= 60:
            messagebox.showerror("입력 오류", "검사 주기는 0.2~60초 사이여야 합니다.", parent=self.top)
            return
        url = self.v_webhook.get().strip()
        if url:
            err = notifier.validate_url(url)
            if err:
                messagebox.showerror("입력 오류", err, parent=self.top)
                return
        elif self.v_teams.get():
            if not messagebox.askyesno(
                    "확인", "공통 Webhook URL이 비어 있습니다.\n"
                            "개별 Webhook이 없는 ROI는 Teams 알림이 가지 않습니다.\n저장할까요?",
                    parent=self.top):
                return
        c = self.cfg
        c.interval_sec = interval
        c.pc_label = self.v_pc.get().strip() or c.pc_label
        c.popup_enabled = self.v_popup.get()
        c.sound_enabled = self.v_sound.get()
        c.auto_start = self.v_auto.get()
        c.minimize_on_start = self.v_minimize.get()
        c.show_overlay = self.v_overlay.get()
        c.show_badge = self.v_badge.get()
        c.teams_enabled = self.v_teams.get()
        c.webhook_url = url
        self.result = c
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()

    def run(self) -> Optional[AppConfig]:
        modal(self.top, self.master)
        return self.result


def edit_settings(master: tk.Misc, cfg: AppConfig) -> Optional[AppConfig]:
    return SettingsDialog(master, cfg).run()

"""공통 설정 창 (검사 주기, Teams 공통 Webhook, 팝업/소리, 자동 시작)."""
import copy
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Optional

import notifier
import config as cfgmod
from config import AppConfig
from i18n import tr
from ui_util import hidden_windows, modal

_MINI_POSITIONS = {"auto": "자동 (ROI와 덜 겹치는 쪽)", "right": "오른쪽 하단", "left": "왼쪽 하단"}


class SettingsDialog:
    def __init__(self, master: tk.Misc, cfg: AppConfig):
        self.master = master
        self.cfg = copy.deepcopy(cfg)
        self.result: Optional[AppConfig] = None
        top = self.top = tk.Toplevel(master)
        top.title(tr("설정"))
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self._cancel)
        body = ttk.Frame(top, padding=12)
        body.pack(fill="both", expand=True)
        tabs = ttk.Notebook(body)            # 항목이 많아 탭으로 나눔 (작은 화면에서도 창이 넘치지 않도록)
        tabs.pack(fill="both", expand=True)
        left = ttk.Frame(tabs, padding=8)
        right = ttk.Frame(tabs, padding=8)
        time_tab = ttk.Frame(tabs, padding=8)
        tabs.add(left, text=tr("  일반 · 알림  "))
        tabs.add(right, text=tr("  에이전트 · AI  "))
        tabs.add(time_tab, text=tr("  NVR 화면 시간  "))
        self.tabs = tabs

        general = ttk.LabelFrame(left, text=tr("검출"), padding=8)
        general.pack(fill="x", pady=(0, 8))
        self.v_interval = tk.StringVar(value=f"{cfg.interval_sec:g}")
        self.v_pc = tk.StringVar(value=cfg.pc_label)
        self.v_popup = tk.BooleanVar(value=cfg.popup_enabled)
        self.v_sound = tk.BooleanVar(value=cfg.sound_enabled)
        self.v_auto = tk.BooleanVar(value=cfg.auto_start)
        self.v_minimize = tk.BooleanVar(value=cfg.minimize_on_start)
        self.v_overlay = tk.BooleanVar(value=cfg.show_overlay)
        self.v_badge = tk.BooleanVar(value=cfg.show_badge)
        ttk.Label(general, text=tr("검사 주기(초, 0.2~60)")).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(general, textvariable=self.v_interval, width=8).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(general, text=tr("PC 표시 이름(알림에 표시)")).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(general, textvariable=self.v_pc, width=24).grid(row=1, column=1, sticky="w", padx=6)
        checks = ((tr("검출 시 팝업 표시"), self.v_popup),
                  (tr("검출 시 경고음"), self.v_sound),
                  (tr("프로그램 시작 시 검출 자동 시작"), self.v_auto),
                  (tr("검출 시작 시 이 창 최소화 (창이 ROI를 가리지 않도록)"), self.v_minimize),
                  (tr("검출 중 화면에 ROI 위치·상태 테두리 표시 (클릭 통과, 캡처에 안 찍힘)"), self.v_overlay),
                  (tr("검출 중 화면 모서리에 '동작 중' 배지 표시"), self.v_badge))
        for i, (text, var) in enumerate(checks, start=2):
            ttk.Checkbutton(general, text=text, variable=var).grid(row=i, column=0, columnspan=2, sticky="w")

        teams = ttk.LabelFrame(left, text=tr("Teams 알림 (Power Automate Workflows 웹훅)"), padding=8)
        teams.pack(fill="x")
        self.v_teams = tk.BooleanVar(value=cfg.teams_enabled)
        self.v_webhook = tk.StringVar(value=cfg.webhook_url)
        ttk.Checkbutton(teams, text=tr("Teams 알림 사용"), variable=self.v_teams).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(teams, text=tr("공통 Webhook URL")).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(teams, textvariable=self.v_webhook, width=60).grid(row=1, column=1, sticky="we", padx=6)
        ttk.Label(teams, text=tr("Teams → 워크플로 → 'Webhook 요청 수신 시 채팅/채널에 게시' 흐름을 만들고\n"
                                 "생성된 URL을 붙여넣으세요. 자세한 방법은 README 참고.\n"
                                 "※ URL에 인증 서명이 들어 있으니 외부에 공유하지 마세요."),
                  foreground="#555555", justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        agent_box = ttk.LabelFrame(right, text=tr("비전 에이전트 (PC 내부에서만 동작)"), padding=8)
        agent_box.pack(fill="x")
        self.v_restart = tk.BooleanVar(value=cfg.agent_auto_restart)
        self.v_escalation = tk.BooleanVar(value=cfg.agent_escalation)
        self.v_shift = tk.StringVar(value=cfg.shift_times)
        self.v_report_teams = tk.BooleanVar(value=cfg.report_to_teams)
        ttk.Checkbutton(agent_box, text=tr("검출 엔진이 오류로 멈추면 자동 재시작 (시간당 최대 3회)"),
                        variable=self.v_restart).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(agent_box, text=tr("동시다발 이상(화면 전체 문제)·연속 불량(설비 점검) 판단을 Teams로 전송"),
                        variable=self.v_escalation).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(agent_box, text=tr("교대 시각 (근무 리포트 자동 작성, 쉼표 구분)")).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(agent_box, textvariable=self.v_shift, width=24).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Checkbutton(agent_box, text=tr("근무 리포트 요약을 Teams로 전송"), variable=self.v_report_teams).grid(
            row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(agent_box, text=tr("예: 08:00,20:00 · 비우면 자동 리포트 안 함 · 리포트는 reports 폴더에 HTML로 저장"),
                  foreground="#555555").grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ops = ttk.LabelFrame(left, text=tr("팝업 · 미니 모니터 · 보관"), padding=8)
        ops.pack(fill="x", pady=(8, 0))
        self.v_consec = tk.StringVar(value=str(cfg.popup_consecutive))
        self.v_retention = tk.StringVar(value=str(cfg.retention_days))
        self.v_snap_scale = tk.StringVar(value=str(cfg.snapshot_scale))
        self.v_mini = tk.BooleanVar(value=cfg.mini_monitor)
        self.v_mini_pos = tk.StringVar(value=tr(_MINI_POSITIONS[cfg.mini_position]))
        ttk.Label(ops, text=tr("연속 이상 발생 시 팝업 – 같은 ROI에서 연속 몇 회 NG면 팝업 (1~99)")).grid(
            row=0, column=0, sticky="w", pady=2)
        ttk.Spinbox(ops, from_=1, to=99, textvariable=self.v_consec, width=6).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Checkbutton(ops, text=tr("검출 시작 시 화면 하단에 ROI 트렌드 미니 모니터 표시"), variable=self.v_mini).grid(
            row=1, column=0, sticky="w")
        ttk.Combobox(ops, textvariable=self.v_mini_pos, state="readonly", width=24,
                     values=[tr(v) for v in _MINI_POSITIONS.values()]).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(ops, text=tr("로그·스냅샷·리포트 보관 기간 (일, 최대 {days}일)", days=cfgmod.MAX_RETENTION_DAYS)).grid(
            row=2, column=0, sticky="w", pady=2)
        ttk.Spinbox(ops, from_=1, to=cfgmod.MAX_RETENTION_DAYS, textvariable=self.v_retention, width=6).grid(
            row=2, column=1, sticky="w", padx=6)
        ttk.Label(ops, text=tr("NG 스냅샷 확대 배율 (1~4배, 원본은 ROI 크기로 따로 저장)")).grid(
            row=3, column=0, sticky="w", pady=2)
        ttk.Spinbox(ops, from_=1, to=4, textvariable=self.v_snap_scale, width=6).grid(
            row=3, column=1, sticky="w", padx=6)
        ttk.Label(ops, text=tr("연속 횟수는 NG 판정마다 1씩 오르고, OK 판정이 나오면 0으로 돌아갑니다. "
                               "Teams 알림은 이 설정과 무관하게 판정마다 전송됩니다."),
                  foreground="#555555", wraplength=560, justify="left").grid(row=4, column=0, columnspan=2, sticky="w")

        self._build_llm(right)
        self._build_time(time_tab)

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text=tr("저장"), width=12, command=self._save).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text=tr("취소"), width=12, command=self._cancel).pack(side="right")
        top.bind("<Escape>", lambda _e: self._cancel())

    def _build_llm(self, parent):
        box = ttk.LabelFrame(parent, text=tr("LLM 연결 (선택 · 의견 에이전트 자연어 답변)"), padding=8)
        box.pack(fill="x", pady=(8, 0))
        c = self.cfg
        self.v_llm = tk.BooleanVar(value=c.llm_enabled)
        self.v_llm_url = tk.StringVar(value=c.llm_url)
        self.v_llm_model = tk.StringVar(value=c.llm_model)
        self.v_llm_key = tk.StringVar(value=c.llm_api_key)
        ttk.Checkbutton(box, text=tr("LLM 사용 (이 PC 또는 사내 서버만)"), variable=self.v_llm).grid(
            row=0, column=0, columnspan=2, sticky="w")
        for i, (label, var, width, show) in enumerate(
                ((tr("서버 주소 (OpenAI 호환)"), self.v_llm_url, 34, ""), (tr("모델 이름"), self.v_llm_model, 24, ""),
                 (tr("API 키 (필요할 때만)"), self.v_llm_key, 24, "•")), start=1):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(box, textvariable=var, width=width, show=show).grid(row=i, column=1, sticky="w", padx=6)
        self.v_llm_auto = tk.BooleanVar(value=c.llm_auto_ng)
        self.v_llm_image = tk.BooleanVar(value=c.llm_send_image)
        ttk.Checkbutton(box, text=tr("NG가 나면 자동으로 원인 분석 (ROI당 5분에 1번 · 팝업·AI 의견 탭에 표시)"),
                        variable=self.v_llm_auto).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(box, text=tr("NG 스냅샷 이미지도 함께 보내기 (비전 모델 필요 · 예: qwen2.5vl)"),
                        variable=self.v_llm_image).grid(row=7, column=0, columnspan=2, sticky="w")
        test = ttk.Frame(box)
        test.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(test, text=tr("연결 테스트"), command=self._test_llm).pack(side="left")
        self.llm_status = ttk.Label(test, text="", foreground="#555555", wraplength=300, justify="left")
        self.llm_status.pack(side="left", padx=8)
        ttk.Label(box, text=tr("예: Ollama → http://127.0.0.1:11434/v1 · 모델 qwen3:4b-instruct\n"
                               "LM Studio → http://127.0.0.1:1234/v1\n"
                               "보내는 내용: ROI별 판정 통계·의견 목록(텍스트). 아래에서 켜면 NG 스냅샷도 (이 PC/사내 서버로만).\n"
                               "외부 인터넷 주소는 보안상 사용할 수 없습니다."),
                  foreground="#555555", justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_time(self, parent):
        """NVR 화면의 시간 글자 위치 등록 – NG 스냅샷 파일 이름과 팝업에 NVR 시간을 쓴다."""
        self.sources = [dict(src) for src in self.cfg.time_sources]
        ttk.Label(parent, text=tr("NG 스냅샷 시간을 PC 시간 대신 NVR 화면에 표시된 시간으로 저장합니다.\n"
                                  "· 라이브(LIVE): 화면 오른쪽 위 흰 글씨 (예: 2026-10-10 10:56:49)\n"
                                  "· 재생(SEARCH): 화면 왼쪽 아래 노란 글씨 (예: 08:46:36) – 날짜는 아래 '재생 날짜'\n"
                                  "시간 글자만 딱 맞게 사각형으로 지정하세요. ROI마다 가장 가까운 시간 위치를 자동으로 씁니다\n"
                                  "(ROI 설정에서 직접 고를 수도 있음). 읽지 못하면 PC 시간으로 저장합니다 (파일 이름 끝 _PC)."),
                  foreground="#555555", justify="left").pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="both", expand=True, pady=(8, 0))
        self.src_list = tk.Listbox(row, height=6, width=56, exportselection=False)
        self.src_list.pack(side="left", fill="both", expand=True)
        btns = ttk.Frame(row)
        btns.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(btns, text=tr("＋ 라이브 시간 위치"), command=lambda: self._add_source("live")).pack(fill="x")
        ttk.Button(btns, text=tr("＋ 재생 시간 위치"), command=lambda: self._add_source("search")).pack(fill="x", pady=4)
        ttk.Button(btns, text=tr("읽기 테스트"), command=self._test_source).pack(fill="x")
        ttk.Button(btns, text=tr("삭제"), command=self._delete_source).pack(fill="x", pady=4)
        self.src_status = ttk.Label(parent, text="", foreground="#555555", wraplength=520, justify="left")
        self.src_status.pack(anchor="w", pady=(6, 0))
        date_row = ttk.Frame(parent)
        date_row.pack(anchor="w", pady=(8, 0))
        self.v_playback = tk.StringVar(value=self.cfg.playback_date)
        ttk.Label(date_row, text=tr("재생 날짜 (YYYY-MM-DD, 비우면 오늘)")).pack(side="left")
        ttk.Entry(date_row, textvariable=self.v_playback, width=12).pack(side="left", padx=6)
        self._refresh_sources()

    def _refresh_sources(self):
        self.src_list.delete(0, "end")
        for src in self.sources:
            kind = tr("라이브") if src["kind"] == "live" else tr("재생")
            self.src_list.insert("end", f"{src['name']}  [{kind}]  {src['x']},{src['y']}  {src['w']}×{src['h']}")

    def _add_source(self, kind: str):
        import roi_editor
        from capture import Grabber
        try:
            with hidden_windows(self.top, self.master, delay=0.4):
                with Grabber() as g:
                    image, left, top = g.grab_virtual_screen()
            regions = roi_editor.select_regions(self.master, image, left, top, single=True)
        except Exception as e:
            messagebox.showerror(tr("오류"), str(e), parent=self.top)
            regions = None
        self._regrab()
        if not regions:
            return
        r = regions[0]
        base = tr("라이브") if kind == "live" else tr("재생")
        n = 1
        while any(s["name"] == f"{base} {n}" for s in self.sources):
            n += 1
        self.sources.append({"name": f"{base} {n}", "kind": kind, "x": r.x, "y": r.y, "w": r.w, "h": r.h})
        self._refresh_sources()
        self.src_list.selection_clear(0, "end")
        self.src_list.selection_set("end")
        self._test_source()

    def _selected_source(self):
        sel = self.src_list.curselection()
        return self.sources[sel[0]] if sel else None

    def _delete_source(self):
        src = self._selected_source()
        if src is not None:
            self.sources.remove(src)
            self._refresh_sources()

    def _test_source(self):
        import nvr_time
        from capture import Grabber
        src = self._selected_source()
        if src is None:
            return
        self.src_status.configure(text=tr("읽는 중…"), foreground="#555555")
        self.top.config(cursor="watch")
        self.top.update()
        try:
            with hidden_windows(self.top, self.master, delay=0.3):
                with Grabber() as g:
                    rgb = g.grab(src["x"], src["y"], src["w"], src["h"])
            when, text = nvr_time.read(src, rgb, self.v_playback.get())
        except Exception as e:
            when, text = None, str(e)
        finally:
            self.top.config(cursor="")
            self._regrab()
        if when:
            self.src_status.configure(text=tr("✔ {name}: {when}  (읽은 글자: {text})", name=src["name"],
                                              when=when.strftime("%Y-%m-%d %H:%M:%S"), text=text[:40]),
                                      foreground="#1b5e20")
        else:
            self.src_status.configure(text=tr("⚠ {name}: 시간을 읽지 못했습니다 (읽은 글자: '{text}'). 시간 글자만 "
                                              "딱 맞게 다시 지정해 보세요.", name=src["name"], text=text[:40]),
                                      foreground="#b71c1c")

    def _regrab(self):
        try:
            self.top.lift()
            self.top.grab_set()
            self.top.focus_force()
        except tk.TclError:
            pass

    def _test_llm(self):
        import llm
        client = llm.LocalLLM(self.v_llm_url.get(), self.v_llm_model.get(), self.v_llm_key.get(), timeout=90)
        self.llm_status.configure(text=tr("연결 중…"), foreground="#555555")
        self.top.config(cursor="watch")
        self.top.update()
        try:
            answer = client.chat(tr("연결 테스트입니다. 'OK' 한 단어로만 답하세요."))
            self.llm_status.configure(text=tr("✔ 연결됨 – 응답: {answer}", answer=answer[:60]), foreground="#1b5e20")
        except llm.LLMError as e:
            self.llm_status.configure(text=f"⚠ {e}", foreground="#b71c1c")
        finally:
            self.top.config(cursor="")

    def _save(self):
        try:
            interval = float(self.v_interval.get())
        except ValueError:
            messagebox.showerror(tr("입력 오류"), tr("검사 주기는 숫자로 입력하세요."), parent=self.top)
            return
        if not 0.2 <= interval <= 60:
            messagebox.showerror(tr("입력 오류"), tr("검사 주기는 0.2~60초 사이여야 합니다."), parent=self.top)
            return
        url = self.v_webhook.get().strip()
        if url:
            err = notifier.validate_url(url)
            if err:
                messagebox.showerror(tr("입력 오류"), err, parent=self.top)
                return
        elif self.v_teams.get():
            if not messagebox.askyesno(
                    tr("확인"), tr("공통 Webhook URL이 비어 있습니다.\n"
                                     "개별 Webhook이 없는 ROI는 Teams 알림이 가지 않습니다.\n저장할까요?"),
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
        shifts = [t.strip() for t in self.v_shift.get().split(",") if t.strip()]
        for t in shifts:
            hh, _sep, mm = t.partition(":")
            if not (hh.isdigit() and mm.isdigit() and int(hh) < 24 and int(mm) < 60):
                messagebox.showerror(tr("입력 오류"), tr("교대 시각 형식이 올바르지 않습니다: {value} (예: 08:00)", value=t), parent=self.top)
                return
        c.agent_auto_restart = self.v_restart.get()
        c.agent_escalation = self.v_escalation.get()
        c.shift_times = ",".join(shifts)
        c.report_to_teams = self.v_report_teams.get()
        try:
            consec = int(self.v_consec.get())
            retention = int(self.v_retention.get())
            snap_scale = int(self.v_snap_scale.get())
        except ValueError:
            messagebox.showerror(tr("입력 오류"), tr("연속 횟수·보관 기간·확대 배율은 숫자로 입력하세요."), parent=self.top)
            return
        if not 1 <= consec <= 99 or not 1 <= retention <= cfgmod.MAX_RETENTION_DAYS or not 1 <= snap_scale <= 4:
            messagebox.showerror(tr("입력 오류"), tr("연속 횟수는 1~99, 보관 기간은 1~{days}일, 확대 배율은 1~4배여야 합니다.",
                                                days=cfgmod.MAX_RETENTION_DAYS),
                                 parent=self.top)
            return
        c.popup_consecutive = consec
        c.retention_days = retention
        c.snapshot_scale = snap_scale
        c.mini_monitor = self.v_mini.get()
        selected_pos = self.v_mini_pos.get()
        c.mini_position = next((k for k, v in _MINI_POSITIONS.items() if tr(v) == selected_pos), "auto")
        c.teams_enabled = self.v_teams.get()
        c.webhook_url = url
        c.llm_enabled = self.v_llm.get()
        c.llm_url = self.v_llm_url.get().strip()
        c.llm_model = self.v_llm_model.get().strip()
        c.llm_api_key = self.v_llm_key.get().strip()
        c.llm_auto_ng = self.v_llm_auto.get()
        c.llm_send_image = self.v_llm_image.get()
        c.time_sources = [dict(src) for src in self.sources]
        playback = self.v_playback.get().strip()
        if playback:
            try:
                datetime.strptime(playback, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror(tr("입력 오류"), tr("재생 날짜는 2026-10-09 형식으로 입력하세요."), parent=self.top)
                return
        c.playback_date = playback
        if c.llm_enabled:
            import llm
            error = llm.LocalLLM(c.llm_url, c.llm_model, c.llm_api_key).check()
            if error:
                messagebox.showerror(tr("입력 오류"), error, parent=self.top)
                return
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

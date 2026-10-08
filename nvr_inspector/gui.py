"""메인 창 (관제센터 대시보드): KPI·카메라 월·에이전트 활동 피드·NG 추이 + ROI 관리/설정."""
import copy
import json
import logging
import os
import queue
import shutil
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

import advisor as advisormod
import agent as agentmod
import alert
import config as cfgmod
import dashboard as db
import detectors
import housekeeping
import llm
import notifier
import overlay
import paths
import roi_dialog
import roi_editor
import samples_dialog
import settings_dialog
import winutil
import worker
from capture import Grabber
from config import ROI, AppConfig
import i18n
from i18n import tr
from ui_util import hidden_windows

log = logging.getLogger(__name__)

APP_TITLE = "FMVS Vision Agent"

STATE_TEXT = {
    "idle": "-", "ok": "정상", "pending": "이상 감지(확인 중)", "alarm": "🚨 경보",
    "skip": "건너뜀(다른 화면)", "wait": "대기", "off": "꺼짐", "error": "오류",
    "moving": "움직임(대기)",
}
STATE_COLOR = dict(db.STATE_COLORS, idle=db.T["muted"])
COLUMNS = (("enabled", "사용", 50), ("name", "이름", 150), ("detector", "검출 유형 · 샘플", 260),
           ("rect", "위치 (X,Y 폭×높이)", 170), ("assignee", "담당자", 120),
           ("state", "상태", 130), ("detail", "측정값 / 상세", 330))


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1560x940")
        self.root.minsize(1100, 680)
        db.apply_theme(self.root)
        self.root.report_callback_exception = self._on_tk_error

        self.cfg: AppConfig = cfgmod.load()
        i18n.set_language(self.cfg.language)
        self.events: "queue.Queue" = queue.Queue()
        self.teams = notifier.TeamsNotifier(self._report_threadsafe)
        self.monitor: Optional[worker.Monitor] = None
        self.alerts = alert.AlertManager(self.root, on_register=self.register_sample,
                                         avoid_rects=self._popup_avoid_rects)
        self.states: Dict[str, tuple] = {}
        self.overlay = overlay.ScreenOverlay(self.root)
        self._last_status = 0.0      # 검출 스레드가 마지막으로 상태를 보낸 시각 (응답 없음 감지)
        self.agent = agentmod.VisionAgent()
        self._beat = 0
        self.consecutive: Dict[str, int] = {}     # ROI별 연속 NG 횟수 (팝업 조건)
        self.latest_frames: Dict[str, object] = {}  # ROI별 최신 화면 (리포트 이미지)
        self.mini = db.MiniMonitor(self.root, on_open=self._open_dashboard, on_stop=self.stop)
        self.advice_hidden: set = set()              # 사용자가 숨긴 의견
        self._advice: Optional[tuple] = None         # (의견 목록, 분석 시각)
        self._advice_known: set = set()              # 이미 알린 의견 (새 의견만 활동 로그에 알림)
        self._advisor_busy = False
        self._llm_busy = False
        self._selfcheck_cache: Dict[str, tuple] = {}

        self._build()
        self.agent.listeners.append(self.feed.add)
        self.agent.configure(self.cfg.rois)
        self.agent.say("boot", tr("FMVS Vision Agent 준비 완료 – ROI {n}개 로드 · 외부 전송 없이 PC 내부에서 동작",
                                   n=len(self.cfg.rois)))
        self._update_running_ui()
        self._refresh_kpis()
        self._purge_old_files()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(200, self._poll_events)
        self.root.after(500, self._heartbeat)
        self.root.after(3000, self._run_advisor)
        if self.cfg.auto_start and self.cfg.rois:
            self.root.after(800, self.start)

    # ================= 화면 구성 =================
    def _build(self):
        T = db.T
        # ---- 헤더 ----
        header = tk.Frame(self.root, bg=T["panel"], height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        brand = tk.Frame(header, bg=T["panel"])
        brand.pack(side="left", padx=18)
        tk.Label(brand, text="◆ FMVS VISION AGENT", bg=T["panel"], fg=T["accent"],
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(8, 0))
        tk.Label(brand, text=tr("자율 영상 품질 관제 에이전트"), bg=T["panel"], fg=T["muted"],
                 font=(db.F, 9)).pack(anchor="w")
        right = tk.Frame(header, bg=T["panel"])
        right.pack(side="right", padx=18)
        self.btn_stop = db.FlatButton(right, tr("■  정지"), self.stop, kind="danger", padx=16, pady=8)
        self.btn_stop.pack(side="right", padx=(8, 0))
        self.btn_start = db.FlatButton(right, tr("▶  에이전트 시작"), self.start, kind="primary", padx=16, pady=8)
        self.btn_start.pack(side="right")
        self.clock_label = tk.Label(right, text="", bg=T["panel"], fg=T["text"], font=("Segoe UI", 15, "bold"))
        self.clock_label.pack(side="right", padx=18)
        # 화면 언어 전환 (한국어 / English) – 누르면 즉시 화면을 다시 만든다
        lang_box = tk.Frame(right, bg=T["border"], padx=1, pady=1)
        lang_box.pack(side="right", padx=(0, 4))
        self.lang_buttons = {}
        for code, text in (("ko", "한국어"), ("en", "English")):          # i18n: skip
            active = i18n.language() == code
            btn = tk.Label(lang_box, text=text, cursor="hand2", padx=10, pady=4, font=(db.F, 9, "bold"),
                           bg=T["accent"] if active else T["card"], fg="#06101f" if active else T["muted"])
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda _e, c=code: self.set_language(c))
            self.lang_buttons[code] = btn
        self.status_pill = tk.Label(header, text="", bg=T["card"], fg=T["muted"], font=(db.F, 10, "bold"),
                                    padx=14, pady=4)
        self.status_pill.pack(side="right", padx=8)
        tk.Frame(self.root, bg=T["accent"], height=2).pack(fill="x")

        # ---- 도구 모음 ----
        bar = tk.Frame(self.root, bg=T["bg"])
        bar.pack(fill="x", padx=14, pady=(10, 4))
        for text, cmd in ((tr("＋ ROI 추가"), self.add_rois), (tr("✎ 편집"), self.edit_selected),
                          (tr("⌖ 위치 재지정"), self.reposition_selected), (tr("⧉ 복제"), self.duplicate_selected),
                          (tr("◐ 사용/해제"), self.toggle_selected), (tr("🖼 샘플/기준 이미지"), self.open_samples),
                          (tr("🗑 삭제"), self.delete_selected)):
            db.FlatButton(bar, text, cmd).pack(side="left", padx=(0, 6))
        for text, cmd in ((tr("📁 폴더"), self.open_folder), (tr("💬 Teams 테스트"), self.test_teams),
                          (tr("📄 리포트 생성"), lambda: self.generate_report(auto=False)), (tr("⚙ 설정"), self.open_settings)):
            db.FlatButton(bar, text, cmd).pack(side="right", padx=(6, 0))

        # ---- KPI ----
        kpi = tk.Frame(self.root, bg=T["bg"])
        kpi.pack(fill="x", padx=14, pady=6)
        self.kpi = {}
        for key, title, color in (("uptime", tr("가동 시간"), T["accent"]), ("inspections", tr("판정 수"), T["sky"]),
                                  ("ng", tr("NG 감지"), T["red"]), ("ok_rate", tr("정상률"), T["green"]),
                                  ("rois", tr("감시 ROI"), T["indigo"]), ("alarms", tr("현재 경보"), T["amber"])):
            tile = db.KpiTile(kpi, title, color)
            tile.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.kpi[key] = tile

        # ---- 본문 위: 카메라 월 | 에이전트 활동·시스템 로그 + NG 추이 ----
        vpaned = ttk.PanedWindow(self.root, orient="vertical", style="Dark.TPanedwindow")
        vpaned.pack(fill="both", expand=True, padx=14, pady=(4, 0))
        hpaned = ttk.PanedWindow(vpaned, orient="horizontal", style="Dark.TPanedwindow")
        wall_box = tk.Frame(hpaned, bg=T["bg"])
        wall_head = tk.Frame(wall_box, bg=T["bg"])
        wall_head.pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(wall_head, text="LIVE CAMERA WALL", bg=T["bg"], fg=T["text"],
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(wall_head, text=tr("카드 끌기: 이동 · ◢ 끌기: 크기 조절"), bg=T["bg"], fg=T["muted"],
                 font=(db.F, 8)).pack(side="left", padx=12)
        db.FlatButton(wall_head, tr("⟲ 자동 정렬"), self.reset_wall_layout, padx=10, pady=3).pack(side="right")
        self.wall = db.CameraWall(wall_box, on_select=self._select_roi, on_open=self._open_roi,
                                  on_layout=self._wall_layout_changed)
        self.wall.pack(fill="both", expand=True)
        hpaned.add(wall_box, weight=3)
        side = tk.Frame(hpaned, bg=T["bg"], width=430)
        tabs = ttk.Notebook(side, style="Dark.TNotebook")
        tabs.pack(fill="both", expand=True, pady=(0, 8))
        self.feed = db.FeedPanel(tabs)          # 에이전트 활동 + 시스템 로그 통합
        tabs.add(self.feed, text=tr("  활동 · 로그  "))
        self.advisor_panel = db.AdvisorPanel(tabs, self.advice_hidden, on_action=self._advice_action,
                                             on_refresh=lambda: self._run_advisor(force=True),
                                             on_ask=self._ask_llm, on_summary=self._llm_summary)
        tabs.add(self.advisor_panel, text=tr("  💡 의견  "))
        self.side_tabs = tabs
        if self._advice is not None:
            self._show_advice()
        self.trend = db.TrendChart(side)
        self.trend.pack(fill="x")
        hpaned.add(side, weight=2)
        vpaned.add(hpaned, weight=4)
        self._hpaned = hpaned

        # ---- 본문 아래: ROI 목록 | ROI 모니터링 (ROI별 NG 추이) ----
        bottom = ttk.PanedWindow(vpaned, orient="horizontal", style="Dark.TPanedwindow")
        tree_box = tk.Frame(bottom, bg=T["panel"], highlightthickness=1, highlightbackground=T["border"])
        tk.Label(tree_box, text="ROI LIST", bg=T["panel"], fg=T["text"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        tree_frame = tk.Frame(tree_box, bg=T["panel"])
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=[c[0] for c in COLUMNS], show="headings",
                                 selectmode="extended", style="Dark.Treeview", height=6)
        for key, text, width in COLUMNS:
            self.tree.heading(key, text=tr(text))
            self.tree.column(key, width=width, anchor="center" if key in ("enabled", "state") else "w",
                             stretch=key == "detail")
        for state, color in STATE_COLOR.items():
            self.tree.tag_configure(state, foreground=color)
        self.tree.tag_configure("alarm", foreground="#fecaca", background="#3b1219")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.wall.select(set(self.tree.selection())))
        bottom.add(tree_box, weight=3)
        self.roi_trend = db.RoiTrendPanel(bottom, on_select=self._select_roi)
        bottom.add(self.roi_trend, weight=2)
        vpaned.add(bottom, weight=1)
        self._bottom = bottom
        self._vpaned = vpaned
        self.root.after(150, self._place_sash)

        self.status_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.status_var, anchor="w", bg=T["panel"], fg=T["muted"],
                 font=(db.F, 8), padx=14, pady=4).pack(fill="x", side="bottom")

    def set_language(self, lang: str):
        """화면 언어 전환: 설정 저장 후 메인 창을 다시 만든다 (검출은 멈추지 않음)."""
        if lang == i18n.language() or lang not in i18n.LANGUAGES:
            return
        self.cfg.language = lang
        i18n.set_language(lang)
        self._save_quietly()
        selected = set(self.tree.selection())
        if self.feed.add in self.agent.listeners:
            self.agent.listeners.remove(self.feed.add)
        for child in self.root.winfo_children():
            if not isinstance(child, tk.Toplevel):          # 오버레이·미니 모니터·팝업 창은 유지
                child.destroy()
        self.mini.destroy()                                   # 다음 표시 때 새 언어로 다시 만든다
        self._build()
        self.agent.listeners.append(self.feed.add)
        for item in list(self.agent.feed):
            self.feed.add(item)
        self._update_running_ui()
        keep = [rid for rid in selected if self.tree.exists(rid)]
        if keep:
            self.tree.selection_set(keep)
        if self.monitor is not None:
            for roi_id, rgb in self.latest_frames.items():
                self.wall.update_frame(roi_id, rgb)
        self._refresh_kpis()
        self._refresh_trends()
        self.trend.draw(self.agent.hourly_series(12))
        self._sync_mini()
        self._update_status_bar()
        self.log("info", tr("화면 언어를 한국어로 바꿨습니다"))

    def _place_sash(self, tries: int = 0):
        """처음 표시될 때 위:아래 = 약 66:34, 좌우 경계는 위(카메라 월|로그)와 아래(ROI 목록|모니터링)를 맞춘다."""
        h, w = self._vpaned.winfo_height(), self._hpaned.winfo_width()
        if (h < 200 or w < 400) and tries < 20:
            self.root.after(100, lambda: self._place_sash(tries + 1))
            return
        try:
            self._vpaned.sashpos(0, max(320, int(h * 0.66)))
            x = max(300, w - max(380, int(w * 0.36)))
            self._hpaned.sashpos(0, x)
            self._bottom.sashpos(0, x)
        except tk.TclError:
            pass

    def reset_wall_layout(self):
        """카메라 월 카드 배치를 모두 자동 배치로 되돌린다."""
        if not any(r.wall for r in self.cfg.rois):
            return
        for r in self.cfg.rois:
            r.wall = []
        self._save_quietly()
        self.wall.set_rois(self.cfg.rois, self.states, self.monitor is not None)
        self.wall.select(set(self.tree.selection()))
        self._sync_thumb_sizes()
        self.log("info", tr("카메라 월 배치를 자동 정렬로 되돌렸습니다"))

    def _wall_layout_changed(self, roi_id: str, rect: list):
        roi = self.cfg.find(roi_id)
        if roi is None:
            return
        roi.wall = cfgmod.parse_wall(rect)
        self._save_quietly()
        self._sync_thumb_sizes()

    def _sync_thumb_sizes(self):
        if self.monitor is not None:
            self.monitor.thumb_sides = self.wall.view_sizes()

    def _save_quietly(self):
        """화면 배치처럼 검출에 영향 없는 변경 저장 (실패해도 작업을 막지 않음)."""
        try:
            cfgmod.save(self.cfg)
        except OSError as e:
            self.log("error", tr("설정 저장 실패: {e}", e=e))

    def _select_roi(self, roi_id: str):
        if self.tree.exists(roi_id):
            self.tree.selection_set([roi_id])
            self.tree.see(roi_id)

    def _open_roi(self, roi_id: str):
        self._select_roi(roi_id)
        self.edit_selected()

    def _refresh_kpis(self):
        T = db.T
        k = self.agent.kpis()
        running = self.monitor is not None
        up = int(k["uptime"])
        self.kpi["uptime"].set(f"{up // 3600:02d}:{up % 3600 // 60:02d}:{up % 60:02d}" if running else "--:--:--",
                               tr("에이전트 가동 중") if running else tr("대기 중"), T["accent"] if running else T["muted"])
        self.kpi["inspections"].set(f"{k['inspections']:,}", tr("누적 판정"))
        self.kpi["ng"].set(str(k["ng"]), tr("누적 이상 감지"), T["red"] if k["ng"] else None)
        rate = k["ok_rate"]
        self.kpi["ok_rate"].set(f"{rate:.1f}%" if rate is not None else "—", tr("판정 대비 정상"),
                                T["green"] if rate is not None and rate >= 99 else (T["amber"] if rate is not None else None))
        enabled = sum(r.enabled for r in self.cfg.rois)
        self.kpi["rois"].set(f"{enabled}", tr("전체 {n}개 중 사용", n=len(self.cfg.rois)))
        alarms = sum(1 for s, _d in self.states.values() if s == "alarm") if running else 0
        self.kpi["alarms"].set(str(alarms), tr("즉시 확인 필요") if alarms else tr("이상 없음"),
                               T["red"] if alarms else T["green"])

    # ================= 목록 =================
    def _row_values(self, roi: ROI):
        if self.monitor is None:
            state, detail = ("off", "") if not roi.enabled else ("idle", "")
        else:
            state, detail = self.states.get(roi.id, ("idle", ""))
        kind = roi.detector_label().split(" (")[0]
        if roi.detector == "match":
            n = {c: len(paths.reference_paths(roi.id, c)) for c in detectors.SAMPLE_CLASSES}
            kind += tr(" · OK{ok}/NG{ng}/무시{skip}", ok=n["ok"], ng=n["ng"], skip=n["skip"])
        elif roi.detector in detectors.REFERENCE_KINDS:
            n = {c: len(paths.reference_paths(roi.id, c)) for c in detectors.SAMPLE_CLASSES}
            kind += (tr(" · OK{ok}/NG{ng}/무시{skip}", ok=n["ok"], ng=n["ng"], skip=n["skip"]) if n["ok"]
                     else tr(" · 기준 없음"))
        return ("✔" if roi.enabled else "–", roi.name, kind,
                f"{roi.x},{roi.y}  {roi.w}×{roi.h}", roi.assignee or "-",
                tr(STATE_TEXT.get(state, state)), detail), state

    def _refresh_tree(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for roi in self.cfg.rois:
            values, state = self._row_values(roi)
            self.tree.insert("", "end", iid=roi.id, values=values, tags=(state,))
        keep = [iid for iid in selected if self.tree.exists(iid)]
        if keep:
            self.tree.selection_set(keep)
        self.wall.set_rois(self.cfg.rois, self.states, self.monitor is not None)
        self.wall.select(set(keep))
        self._sync_thumb_sizes()
        self.agent.configure(self.cfg.rois)
        self._update_status_bar()

    def _update_row(self, roi_id: str):
        roi = self.cfg.find(roi_id)
        if roi is None or not self.tree.exists(roi_id):
            return
        values, state = self._row_values(roi)
        self.tree.item(roi_id, values=values, tags=(state,))
        if self.monitor is not None and roi.enabled:
            self.wall.update_state(roi_id, *self.states.get(roi_id, ("idle", "")))

    def _selected_rois(self) -> List[ROI]:
        return [r for r in (self.cfg.find(i) for i in self.tree.selection()) if r is not None]

    def _one_selected(self) -> Optional[ROI]:
        rois = self._selected_rois()
        if len(rois) != 1:
            messagebox.showinfo(tr("안내"), tr("목록에서 ROI를 하나 선택하세요."), parent=self.root)
            return None
        return rois[0]

    def _commit(self, message: Optional[str] = None):
        """설정 저장 + 실행 중인 검출에 즉시 반영."""
        try:
            cfgmod.save(self.cfg)
        except OSError as e:
            messagebox.showerror(tr("저장 실패"), tr("설정을 저장할 수 없습니다.\n{e}", e=e), parent=self.root)
        if self.monitor is not None:
            self.monitor.update_config(self.cfg)
        self.alerts.sound_enabled = self.cfg.sound_enabled
        self._refresh_tree()
        self._sync_overlay()
        self._sync_mini()
        self._refresh_trends()
        if message:
            self.log("info", message)

    # ================= ROI 조작 =================
    def _select_on_screen(self, existing, single):
        """메인 창을 숨기고 화면을 캡처한 뒤 오버레이에서 ROI를 그린다.
        반환: (사각형 목록 또는 None, 각 사각형 중심의 프로그램 이름 목록)"""
        try:
            self.overlay.hide()
            self.root.withdraw()
            self.root.update()
            time.sleep(0.4)
            with Grabber() as g:
                image, left, top = g.grab_virtual_screen()
            rects = roi_editor.select_regions(self.root, image, left, top, existing=existing, single=single)
            processes = []
            if rects:
                self.root.update()
                time.sleep(0.3)   # 오버레이가 사라진 뒤 실제 창 기준으로 프로그램 확인
                processes = [winutil.process_name_at(x + w // 2, y + h // 2) for x, y, w, h in rects]
            return rects, processes
        finally:
            self.root.deiconify()
            self.root.lift()
            self._sync_overlay()

    def add_rois(self):
        try:
            rects, processes = self._select_on_screen(self.cfg.rois, single=False)
        except Exception as e:
            log.exception("ROI 지정 실패")
            messagebox.showerror(tr("오류"), tr("화면 캡처/ROI 지정 실패: {e}", e=e), parent=self.root)
            return
        if not rects:
            return
        added = 0
        base = len(self.cfg.rois)
        for i, ((x, y, w, h), proc) in enumerate(zip(rects, processes), 1):
            roi = ROI(name=f"ROI {base + i}", x=x, y=y, w=w, h=h, expected_process=proc or "")
            result = roi_dialog.edit_roi(self.root, roi, tr("새 ROI 설정 ({i}/{total}) – 취소하면 이 ROI는 추가하지 않음",
                                                                    i=i, total=len(rects)))
            if result is None:
                continue
            self.cfg.rois.append(result)
            added += 1
        if added:
            self._commit(tr("ROI {n}개 추가", n=added))

    def edit_selected(self):
        roi = self._one_selected()
        if roi is None:
            return
        result = roi_dialog.edit_roi(self.root, roi, tr("ROI 설정 – {name}", name=roi.name))
        if result is None:
            return
        note = ""
        if (result.w, result.h) != (roi.w, roi.h):
            n = worker.resize_samples(roi.id, result.w, result.h)   # 샘플은 지우지 않고 새 크기에 맞춤
            note = tr(" · 크기 변경 → 샘플 {n}장 새 크기로 유지", n=n) if n else ""
        self.cfg.rois[self.cfg.rois.index(roi)] = result
        self._commit(tr("[{name}] 설정 변경{note}", name=result.name, note=note))

    def reposition_selected(self):
        roi = self._one_selected()
        if roi is None:
            return
        try:
            others = [r for r in self.cfg.rois if r.id != roi.id]
            rects, processes = self._select_on_screen(others, single=True)
        except Exception as e:
            log.exception("ROI 위치 지정 실패")
            messagebox.showerror(tr("오류"), tr("화면 캡처/ROI 지정 실패: {e}", e=e), parent=self.root)
            return
        if not rects:
            return
        nx, ny, nw, nh = rects[0]
        note = ""
        if (nw, nh) != (roi.w, roi.h):
            keep = messagebox.askyesnocancel(
                tr("ROI 크기"), tr("새로 그린 크기 {nw}×{nh}가 기존 {w}×{h}와 다릅니다.\n\n"
                                  "[예] 기존 크기 {w}×{h}를 유지하고 위치만 이동 (권장 – 샘플 그대로 사용)\n"
                                  "[아니오] 새 크기로 변경 (샘플/기준 이미지를 새 크기에 맞춰 유지)\n[취소] 변경 안 함",
                                  nw=nw, nh=nh, w=roi.w, h=roi.h),
                parent=self.root)
            if keep is None:
                return
            if keep:   # 그린 영역의 중심에 기존 크기로 배치
                nx, ny, nw, nh = nx + nw // 2 - roi.w // 2, ny + nh // 2 - roi.h // 2, roi.w, roi.h
            else:
                n = worker.resize_samples(roi.id, nw, nh)
                note = tr(" · 샘플 {n}장 새 크기로 유지", n=n) if n else ""
        roi.x, roi.y, roi.w, roi.h = nx, ny, nw, nh
        if processes and processes[0] and not roi.expected_process:
            roi.expected_process = processes[0]
        self._commit(tr("[{name}] 위치 변경: {x},{y} {w}×{h} (샘플/기준 이미지 유지){note}",
                        name=roi.name, x=roi.x, y=roi.y, w=roi.w, h=roi.h, note=note))

    def duplicate_selected(self):
        roi = self._one_selected()
        if roi is None:
            return
        dup = copy.deepcopy(roi)
        dup.id = cfgmod.new_roi_id()
        dup.wall = []
        dup.name = tr("{name} 복사본", name=roi.name)
        result = roi_dialog.edit_roi(self.root, dup, tr("ROI 복제"))
        if result is not None:
            if (result.x, result.y, result.w, result.h) == (roi.x, roi.y, roi.w, roi.h):
                for cls in detectors.SAMPLE_CLASSES:     # 같은 위치면 샘플/기준 이미지도 복사
                    for src in paths.reference_paths(roi.id, cls):
                        shutil.copyfile(src, paths.new_reference_path(result.id, cls))
            self.cfg.rois.insert(self.cfg.rois.index(roi) + 1, result)
            self._commit(tr("[{name}] 추가 (복제)", name=result.name))

    def toggle_selected(self):
        rois = self._selected_rois()
        if not rois:
            messagebox.showinfo(tr("안내"), tr("목록에서 ROI를 선택하세요."), parent=self.root)
            return
        new_state = not all(r.enabled for r in rois)
        for r in rois:
            r.enabled = new_state
        self._commit(tr("ROI {n}개 사용", n=len(rois)) if new_state else tr("ROI {n}개 해제", n=len(rois)))

    def delete_selected(self):
        rois = self._selected_rois()
        if not rois:
            return
        names = ", ".join(r.name for r in rois)
        if not messagebox.askyesno(tr("삭제 확인"), tr("다음 ROI를 삭제할까요?\n{names}", names=names), parent=self.root):
            return
        for r in rois:
            self.cfg.rois.remove(r)
            self.states.pop(r.id, None)
            self._delete_reference(r.id)
        self._commit(tr("ROI 삭제: {names}", names=names))

    def open_samples(self):
        roi = self._one_selected()
        if roi is None:
            return
        if roi.detector not in detectors.REFERENCE_KINDS:
            messagebox.showinfo(tr("안내"), tr("[{name}]의 검출 유형({label})은 샘플 이미지를 쓰지 않습니다.\n"
                                             "'OK/NG 이미지 매칭', '형상 검사', '기준 화면과 다름' 유형에서 사용합니다.",
                                             name=roi.name, label=roi.detector_label()),
                                parent=self.root)
            return
        samples_dialog.manage_samples(self.root, roi)
        self._refresh_tree()
        self.log("info", tr("[{name}] 샘플 이미지 갱신 (검출 중이면 바로 반영)", name=roi.name))

    def register_sample(self, roi_id: str, cls: str, raw_path: str) -> str:
        """경보 팝업의 'OK로 등록 / NG로 등록' 버튼. 성공 시 빈 문자열, 실패 시 오류 메시지."""
        roi = self.cfg.find(roi_id)
        if roi is None:
            return tr("ROI가 삭제되었습니다.")
        try:
            frame = worker._load_png(raw_path)
        except Exception as e:
            return tr("스냅샷을 열 수 없습니다: {e}", e=e)
        if frame.shape[:2] != (roi.h, roi.w):
            return tr("ROI 크기가 바뀌어 등록할 수 없습니다.")
        before = self._auto_threshold(roi)
        dest = paths.new_reference_path(roi_id, cls)
        shutil.copyfile(raw_path, dest)
        label = tr(detectors.SAMPLE_CLASSES.get(cls, cls))
        self.log("info", tr("[{name}] 경보 화면을 {label} 샘플로 등록: {file}",
                             name=roi.name, label=label, file=os.path.basename(dest)))
        self.agent.on_feedback(roi.name, cls, before, self._auto_threshold(roi))
        self._refresh_tree()
        return ""

    @staticmethod
    def _auto_threshold(roi: ROI) -> Optional[float]:
        """OK/NG 매칭 ROI의 자동 계산 OK 허용 거리 (에이전트 학습 기록용)."""
        if roi.detector != "match":
            return None
        try:
            samples = worker.load_samples(roi.id)
            if not samples["ok"]:
                return None
            p = detectors.normalize_params("match", roi.params)
            return detectors.match_calibration(samples, (roi.h, roi.w), p["max_shift"])["threshold"]
        except Exception:
            log.exception("자동 기준 계산 실패")
            return None

    @staticmethod
    def _delete_reference(roi_id: str):
        paths.delete_references(roi_id)   # 모든 클래스(OK/NG/무시) 삭제

    # ================= 설정/테스트 =================
    def open_settings(self):
        result = settings_dialog.edit_settings(self.root, self.cfg)
        if result is not None:
            result.rois = self.cfg.rois
            self.cfg = result
            self._commit(tr("설정 저장"))

    def test_teams(self):
        rois = self._selected_rois()
        sent = 0
        for roi in rois or [None]:
            url = self.cfg.webhook_for(roi)
            name = roi.name if roi else tr("공통")
            err = notifier.validate_url(url)
            if err:
                self.log("warning", tr("Teams 테스트 ({name}): {err}", name=name, err=err))
                continue
            payload = notifier.build_payload(
                "test", roi_name=roi.name if roi else tr("(테스트)"),
                detector_label=roi.detector_label() if roi else "-", detail=tr("테스트 메시지"),
                assignee=roi.assignee if roi else "", assignee_email=roi.assignee_email if roi else "",
                pc_label=self.cfg.pc_label, when=worker.now_text())
            self.teams.send(url, payload, tr("테스트 ({name})", name=name))
            sent += 1
        if sent:
            self.log("info", tr("Teams 테스트 전송 요청 {n}건 – 결과는 로그에 표시됩니다.", n=sent))
        elif not rois:
            messagebox.showinfo(tr("안내"), tr("[설정]에서 공통 Webhook URL을 먼저 입력하세요.\n"
                                             "(ROI를 선택하면 해당 ROI의 담당자/Webhook으로 테스트합니다)"),
                                parent=self.root)

    def open_folder(self):
        if hasattr(os, "startfile"):
            os.startfile(paths.BASE_DIR)  # type: ignore[attr-defined]

    # ================= 검출 시작/중지 =================
    def start(self):
        if self.monitor is not None:
            return
        if not any(r.enabled for r in self.cfg.rois):
            messagebox.showwarning(tr("안내"), tr("사용 중인 ROI가 없습니다. [화면에서 ROI 추가]로 먼저 지정하세요."),
                                   parent=self.root)
            return
        if self.cfg.teams_enabled and not any(self.cfg.webhook_for(r) for r in self.cfg.rois if r.enabled):
            self.log("warning", tr("Teams 알림이 켜져 있지만 Webhook URL이 없습니다. 팝업만 표시됩니다."))
        self.states.clear()
        self.alerts.sound_enabled = self.cfg.sound_enabled
        self.monitor = worker.Monitor(self.cfg, self.events, self.teams)
        self.monitor.send_frames = True
        self._sync_thumb_sizes()
        self._last_status = time.monotonic()
        counts = {r.id: sum(len(paths.reference_paths(r.id, c)) for c in detectors.SAMPLE_CLASSES)
                  for r in self.cfg.rois if r.enabled}
        self.agent.boot(self.cfg.rois, counts)
        self.monitor.start()
        self.log("info", tr("검출 시작 (ROI {n}개, {sec}초 주기)",
                            n=sum(r.enabled for r in self.cfg.rois), sec=f"{self.cfg.interval_sec:g}"))
        self.consecutive.clear()
        self._update_running_ui()
        if self.cfg.minimize_on_start:
            self.root.after(300, self.root.iconify)
        self.root.after(400, self._sync_mini)

    def stop(self):
        if self.monitor is None:
            return
        self.monitor.stop()
        self.monitor.join(timeout=5)
        self.monitor = None
        self.states.clear()
        self._update_running_ui()
        self.mini.hide()

    def _popup_avoid_rects(self):
        """탐지 팝업이 가리면 안 되는 영역: 감시 중인 ROI + 미니 모니터."""
        rects = [(r.x, r.y, r.w, r.h) for r in self.cfg.rois if r.enabled]
        mini = self.mini.rect() if hasattr(self, "mini") else None
        if mini:
            rects.append(mini)
        return rects

    def _open_dashboard(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _sync_mini(self):
        """검출 중이면 화면 하단에 ROI 트렌드 미니 모니터를 띄운다."""
        try:
            if self.monitor is not None and self.cfg.mini_monitor:
                self.mini.show(self.agent.roi_trends([r for r in self.cfg.rois if r.enabled]),
                               self.cfg.mini_position, [(r.x, r.y, r.w, r.h) for r in self.cfg.rois if r.enabled])
            else:
                self.mini.hide()
        except tk.TclError:
            log.exception("미니 모니터 오류")

    def _refresh_trends(self):
        trends = self.agent.roi_trends(self.cfg.rois)
        self.roi_trend.draw(trends)
        if self.monitor is not None and self.mini.visible():
            alarms = sum(1 for s, _d in self.states.values() if s == "alarm")
            ok = time.monotonic() - self._last_status < max(10.0, self.cfg.interval_sec * 5)
            status = (tr("⚠ 응답 없음") if not ok else
                      tr("● 감시 중 · 경보 {n}건", n=alarms) if alarms else tr("● 실시간 감시 중 · 이상 없음"))
            self.mini.update([t for t in trends if t["enabled"]], status, ok and not alarms)

    def _update_running_ui(self):
        running = self.monitor is not None
        self.btn_start.set_enabled(not running)
        self.btn_stop.set_enabled(running)
        self.status_pill.configure(text=tr("●  AGENT ONLINE · 실시간 감시 중") if running else tr("○  STANDBY · 대기"),
                                   fg="#04130a" if running else db.T["muted"],
                                   bg=db.T["green"] if running else db.T["card"])
        self.root.title(APP_TITLE + " – " + (tr("감시 중") if running else tr("대기")))
        self._refresh_tree()
        self._sync_overlay()

    def _sync_overlay(self):
        """검출 중이면 화면 표시(ROI 테두리·동작 배지)를 보이고, 아니면 숨긴다."""
        try:
            if self.monitor is not None:
                self.overlay.show(self.cfg.rois, self.states, self.cfg.show_overlay, self.cfg.show_badge)
                if self.overlay.win is not None and not self.overlay.capture_excluded \
                        and not getattr(self, "_warned_capture", False):
                    self._warned_capture = True
                    self.log("warning", tr("이 Windows는 화면 표시를 캡처에서 제외하지 못합니다(Windows 10 2004 이상 필요). "
                                           "ROI끼리 붙어 있으면 테두리가 옆 ROI 판정에 영향을 줄 수 있으니 [설정]에서 화면 표시를 끄세요."))
            else:
                self.overlay.hide()
        except tk.TclError:
            log.exception("화면 표시 오버레이 오류")

    def _heartbeat(self):
        """0.5초마다: 시계·KPI·깜빡임·추이 차트·교대 리포트."""
        self._beat += 1
        on = self._beat % 2 == 0
        running = self.monitor is not None
        try:
            self.clock_label.configure(text=datetime.now().strftime("%H:%M:%S"))
            self.feed.pulse(running, on)
            self.wall.blink(on)
            if running:
                stall_limit = max(10.0, self.cfg.interval_sec * 5)
                ok = time.monotonic() - self._last_status < stall_limit
                alarms = sum(1 for s, _d in self.states.values() if s == "alarm")
                self.overlay.heartbeat(ok, sum(r.enabled for r in self.cfg.rois), alarms)
                if not ok and self._beat % 20 == 0:
                    self.agent.say("warn", tr("검출 엔진 응답 없음 {sec}초 – 감시 중",
                                               sec=int(time.monotonic() - self._last_status)))
                if self.agent.due_shift(self.cfg.shift_times):
                    self.generate_report(auto=True)
            if on:
                self._refresh_kpis()
            if self._beat % 60 == 1:
                self.trend.draw(self.agent.hourly_series(12))
            if self._beat % 4 == 1:
                self._refresh_trends()
            if self._beat % 600 == 0:              # 5분마다 의견 에이전트 분석
                self._run_advisor()
            if self._beat % 7200 == 0:             # 1시간마다 보관 기간 정리
                self._purge_old_files()
        except tk.TclError:
            log.exception("대시보드 갱신 오류")
        self.root.after(500, self._heartbeat)

    # ================= 의견 에이전트 (Advisor) =================
    def _advisor_inputs(self):
        """분석 스레드에 넘길 자료 사본 (화면 스레드에서 만든다)."""
        rois = copy.deepcopy(self.cfg.rois)
        stats = {rid: copy.deepcopy(st) for rid, st in self.agent.stats.items()}
        hourly = {r.id: dict(self.agent.hourly_series(12, r.id)) for r in rois}
        ctx = advisormod.Context(running=self.monitor is not None, teams_enabled=self.cfg.teams_enabled,
                                 uptime_sec=self.agent.kpis().get("uptime", 0.0))
        return rois, stats, hourly, ctx

    def _sample_info(self, rois):
        """ROI별 샘플 수와 자체 검증 요약 (샘플 파일이 바뀌었을 때만 다시 계산)."""
        counts, checks = {}, {}
        for roi in rois:
            files = {c: paths.reference_paths(roi.id, c) for c in detectors.SAMPLE_CLASSES}
            counts[roi.id] = {c: len(f) for c, f in files.items()}
            if roi.detector not in detectors.REFERENCE_KINDS or not files["ok"]:
                continue
            try:
                key = (roi.detector, json.dumps(roi.params, sort_keys=True),
                       tuple((p, os.path.getmtime(p)) for f in files.values() for p in f))
            except OSError:
                continue
            cached = self._selfcheck_cache.get(roi.id)
            if cached and cached[0] == key:
                checks[roi.id] = cached[1]
                continue
            try:
                summary = detectors.self_check(roi.detector, roi.params, worker.load_samples(roi.id))["summary"]
            except Exception as e:
                summary = ""
                log.warning("자체 검증 실패 [%s]: %s", roi.name, e)
            self._selfcheck_cache[roi.id] = (key, summary)
            checks[roi.id] = summary
        return counts, checks

    def _run_advisor(self, force: bool = False):
        """의견 분석 (백그라운드). force: 사용자가 요청 – 지금은 주기 분석과 같고 표시만 즉시."""
        if self._advisor_busy:
            return
        self._advisor_busy = True
        rois, stats, hourly, ctx = self._advisor_inputs()

        def work():
            try:
                counts, checks = self._sample_info(rois)
                items = advisormod.analyze(rois, stats, counts, checks, hourly, ctx)
            except Exception as e:
                log.exception("의견 분석 실패")
                items = [advisormod.Advice("advisor_error", "warn", tr("의견 분석 오류"), str(e))]
            self.events.put(("advice", items, datetime.now().strftime("%H:%M:%S")))

        threading.Thread(target=work, name="advisor", daemon=True).start()

    def _show_advice(self, announce: bool = False):
        items, when = self._advice
        client = llm.from_config(self.cfg)
        self.advisor_panel.show(items, client.model if client and client.model else None, when)
        _n, important = self.advisor_panel.visible_count()
        self.side_tabs.tab(self.advisor_panel, text=tr("  💡 의견 {n}  ", n=important) if important
                           else tr("  💡 의견  "))
        if announce:
            new = [a for a in items if a.level in ("critical", "warn") and a.key not in self._advice_known]
            self._advice_known = {a.key for a in items}
            if new:
                more = tr(" 외 {n}건", n=len(new) - 1) if len(new) > 1 else ""
                self.agent.say("think", tr("의견 에이전트: {title}{more} – [💡 의견] 탭에서 확인",
                                           title=new[0].title, more=more))

    def _advice_action(self, advice):
        if advice.roi_id and self.tree.exists(advice.roi_id):
            self._select_roi(advice.roi_id)
        if advice.action == "samples":
            self.open_samples()
        elif advice.action == "edit":
            self.edit_selected()
        elif advice.action == "settings":
            self.open_settings()
        self._run_advisor(force=True)

    def _ask_llm(self, question: str):
        client = llm.from_config(self.cfg)
        if client is None:
            items = self._advice[0] if self._advice else []
            words = [r.name for r in self.cfg.rois if r.name and r.name in question]
            related = [a for a in items if not words or any(w in a.title for w in words)][:4]
            lines = [tr("LLM이 연결되어 있지 않아 규칙 분석 결과로 답합니다. "
                        "(설정 → LLM 연결에서 켜면 자연어로 답합니다)")]
            lines += [f"• {a.title} – {a.body}" for a in related] or [tr("관련된 개선 의견이 없습니다.")]
            self.advisor_panel.show_answer(question, "\n".join(lines))
            return
        if self._llm_busy:
            return
        self._llm_busy = True
        self.advisor_panel.set_busy(True)
        rois, stats, _hourly, ctx = self._advisor_inputs()
        items = self._advice[0] if self._advice else []
        counts = {r.id: {c: len(paths.reference_paths(r.id, c)) for c in detectors.SAMPLE_CLASSES} for r in rois}
        data = advisormod.summary_text(rois, stats, counts, items, ctx)

        def work():
            try:
                answer, error = client.chat(f"{question}\n\n---\n{data}"), False
            except llm.LLMError as e:
                answer, error = str(e), True
            except Exception as e:
                log.exception("LLM 요청 실패")
                answer, error = str(e), True
            self.events.put(("llm", question, answer, error))

        threading.Thread(target=work, name="llm", daemon=True).start()

    def _llm_summary(self):
        self._ask_llm(tr("현재 상태를 종합해서 우선순위가 높은 운영 의견을 주세요."))

    # ================= 에이전트 행동 =================
    def _run_actions(self, actions):
        for act in actions:
            if act.kind == "restart":
                self.root.after(5000, self._auto_restart)
            elif act.kind == "teams":
                self._send_agent_message(act.title, act.message, escalation=True)

    def _auto_restart(self):
        if self.monitor is None:
            self.log("warning", tr("에이전트: 검출 엔진 자동 재시작"))
            self.start()

    def _send_agent_message(self, title: str, message: str, escalation: bool):
        if not self.cfg.teams_enabled or (escalation and not self.cfg.agent_escalation):
            self.agent.say("act", tr("Teams 알림 꺼짐 – 대시보드에만 기록"))
            return
        url = self.cfg.webhook_for(None)
        if notifier.validate_url(url):
            self.agent.say("warn", tr("공통 Webhook URL이 없어 Teams 전송 생략"))
            return
        payload = notifier.build_agent_payload(title, message, pc_label=self.cfg.pc_label, when=worker.now_text())
        self.teams.send(url, payload, tr("에이전트: {title}", title=title))

    def generate_report(self, auto: bool):
        """근무 리포트(HTML) 작성. 자동(교대 시각)이면 Teams로 요약 전송, 수동이면 바로 열기."""
        now = datetime.now()
        title = tr("FMVS 근무 리포트 {when}", when=f"{now:%Y-%m-%d %H:%M}")
        try:
            paths.ensure_dirs()
            path = os.path.join(paths.REPORT_DIR, f"report_{now:%Y%m%d_%H%M}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.agent.report_html(title, self.cfg.rois, frames=dict(self.latest_frames)))
        except OSError as e:
            self.log("error", tr("리포트 저장 실패: {e}", e=e))
            return None
        summary = self.agent.report_summary()
        self.agent.say("act", (tr("교대 시각 도래 → ") if auto else "")
                       + tr("근무 리포트 작성: {file} ({summary})", file=os.path.basename(path), summary=summary))
        if auto and self.cfg.report_to_teams:
            self._send_agent_message(title, summary + tr("\n리포트 파일: {path}", path=path), escalation=False)
        if not auto and hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
        return path

    def _update_status_bar(self):
        running = self.monitor is not None
        enabled = sum(r.enabled for r in self.cfg.rois)
        alarms = sum(1 for s, _d in self.states.values() if s == "alarm")
        teams = tr("Teams 알림 켜짐") if self.cfg.teams_enabled else tr("Teams 알림 꺼짐")
        self.status_var.set(tr("{run}   |   ROI {enabled}/{total}개 사용   |   경보 {alarms}건   |   {teams}   |   설정 파일: {path}",
                               run=tr("● 검출 중") if running else tr("○ 중지됨"), enabled=enabled,
                               total=len(self.cfg.rois), alarms=alarms, teams=teams, path=paths.SETTINGS_PATH))

    # ================= 이벤트 처리 =================
    def _report_threadsafe(self, level: str, message: str):
        self.events.put(("log", level, message))

    def _poll_events(self):
        changed = False
        frames = {}
        try:
            for _ in range(1000):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "frame":
                    if self.monitor is not None:
                        frames[event[1]] = event[2]      # ROI별 최신 프레임만 표시
                    continue
                if kind == "status":
                    _k, roi_id, state, detail = event
                    self._last_status = time.monotonic()
                    if self.monitor is not None:
                        self.agent.on_status(roi_id, state, detail)
                    if state == "ok":
                        self.consecutive[roi_id] = 0       # OK 판정이 나오면 연속 횟수 초기화
                    if (self.monitor is not None and self.cfg.find(roi_id) is not None
                            and self.states.get(roi_id) != (state, detail)):
                        self.states[roi_id] = (state, detail)
                        self._update_row(roi_id)
                        self.overlay.set_state(roi_id, state)
                        changed = True
                elif kind == "alert":
                    info = event[1]
                    tag = tr("재알림") if info["kind"] == "repeat" else tr("이상 감지")
                    self.log("error", tr("🚨 [{name}] {tag} – {detail}", name=info["roi_name"], tag=tag, detail=info["detail"]))
                    count = self.consecutive.get(info["roi_id"], 0) + 1
                    self.consecutive[info["roi_id"]] = count
                    info["consecutive"] = count
                    actions = self.agent.on_alert(info)
                    info["total_ng"] = self.agent.stats[info["roi_id"]].ng
                    need = max(1, self.cfg.popup_consecutive)
                    if self.cfg.popup_enabled and count >= need:
                        self.alerts.alert(info)
                    elif self.cfg.popup_enabled:
                        self.log("info", tr("[{name}] 연속 NG {count}/{need}회 – {need}회부터 팝업",
                                          name=info["roi_name"], count=count, need=need))
                    self._run_actions(actions)
                    self._refresh_trends()
                elif kind == "recover":
                    info = event[1]
                    self.log("info", tr("✅ [{name}] 정상 복구 – {detail}", name=info["roi_name"], detail=info["detail"]))
                    self.alerts.recover(info)
                    self.agent.on_recover(info)
                elif kind == "log":
                    self.log(event[1], event[2])
                elif kind == "advice":
                    self._advisor_busy = False
                    self._advice = (event[1], event[2])
                    self._show_advice(announce=True)
                elif kind == "llm":
                    self._llm_busy = False
                    self.advisor_panel.set_busy(False)
                    self.advisor_panel.show_answer(event[1], event[2], event[3])
                    self.side_tabs.select(self.advisor_panel)
                elif kind == "stopped":
                    if self.monitor is not None and not self.monitor.is_alive():
                        self.monitor = None
                        self.states.clear()
                        self._update_running_ui()
                    level = "warning" if "오류" in event[1] or "error" in event[1].lower() else "info"  # i18n: skip
                    self.log(level, tr("검출 중지 ({reason})", reason=event[1]))
                    self._run_actions(self.agent.on_monitor_stopped(event[1], self.cfg.agent_auto_restart))
        except queue.Empty:
            pass
        for roi_id, rgb in frames.items():
            self.latest_frames[roi_id] = rgb
            try:
                self.wall.update_frame(roi_id, rgb)
            except Exception:
                log.exception("썸네일 표시 실패")
        if changed:
            self._update_status_bar()
        self.root.after(200, self._poll_events)

    def log(self, level: str, message: str):
        """시스템 로그 – 파일 로그 + 화면의 '에이전트 활동 · 시스템 로그' 통합 스트림."""
        getattr(log, level if level in ("info", "warning", "error") else "info")(message)
        kind = {"error": "error", "warning": "warn"}.get(level, "sys")
        item = agentmod.FeedItem(time.time(), kind, message)
        self.agent.feed.append(item)        # 언어 전환으로 화면을 다시 만들 때 다시 표시
        self.feed.add(item)

    def _purge_old_files(self):
        try:
            removed = housekeeping.purge(self.cfg.retention_days)
            if removed:
                self.log("info", tr("보관 기간({days}일) 지난 로그·스냅샷·리포트 {n}개 정리",
                                    days=self.cfg.retention_days, n=removed))
        except Exception:
            log.exception("보관 기간 정리 실패")

    def _on_tk_error(self, exc, value, tb):
        log.error("UI 오류", exc_info=(exc, value, tb))
        messagebox.showerror(tr("오류"), tr("예기치 않은 오류가 발생했습니다.\n{value}\n\n자세한 내용은 logs 폴더를 확인하세요.",
                                           value=value),
                             parent=self.root)

    def _on_close(self):
        if self.monitor is not None:
            if not messagebox.askyesno(tr("종료"), tr("검출이 실행 중입니다. 종료하면 감시가 멈춥니다.\n종료할까요?"),
                                       parent=self.root):
                return
            self.stop()
        try:
            cfgmod.save(self.cfg)
        except OSError:
            log.exception("종료 시 설정 저장 실패")
        self.alerts.close_all()
        self.overlay.destroy()
        self.mini.destroy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

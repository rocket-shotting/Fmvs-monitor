"""메인 창 (관제센터 대시보드): KPI·카메라 월·에이전트 활동 피드·NG 추이 + ROI 관리/설정."""
import copy
import logging
import os
import queue
import shutil
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

import agent as agentmod
import alert
import config as cfgmod
import dashboard as db
import detectors
import housekeeping
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

        self._build()
        self.agent.listeners.append(self.feed.add)
        self.agent.configure(self.cfg.rois)
        self.agent.say("boot", f"FMVS Vision Agent 준비 완료 – ROI {len(self.cfg.rois)}개 로드 · 외부 전송 없이 PC 내부에서 동작")
        self._update_running_ui()
        self._refresh_kpis()
        self._purge_old_files()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(200, self._poll_events)
        self.root.after(500, self._heartbeat)
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
        tk.Label(brand, text="자율 영상 품질 관제 에이전트", bg=T["panel"], fg=T["muted"],
                 font=(db.F, 9)).pack(anchor="w")
        right = tk.Frame(header, bg=T["panel"])
        right.pack(side="right", padx=18)
        self.btn_stop = db.FlatButton(right, "■  정지", self.stop, kind="danger", padx=16, pady=8)
        self.btn_stop.pack(side="right", padx=(8, 0))
        self.btn_start = db.FlatButton(right, "▶  에이전트 시작", self.start, kind="primary", padx=16, pady=8)
        self.btn_start.pack(side="right")
        self.clock_label = tk.Label(right, text="", bg=T["panel"], fg=T["text"], font=("Segoe UI", 15, "bold"))
        self.clock_label.pack(side="right", padx=18)
        self.status_pill = tk.Label(header, text="", bg=T["card"], fg=T["muted"], font=(db.F, 10, "bold"),
                                    padx=14, pady=4)
        self.status_pill.pack(side="right", padx=8)
        tk.Frame(self.root, bg=T["accent"], height=2).pack(fill="x")

        # ---- 도구 모음 ----
        bar = tk.Frame(self.root, bg=T["bg"])
        bar.pack(fill="x", padx=14, pady=(10, 4))
        for text, cmd in (("＋ ROI 추가", self.add_rois), ("✎ 편집", self.edit_selected),
                          ("⌖ 위치 재지정", self.reposition_selected), ("⧉ 복제", self.duplicate_selected),
                          ("◐ 사용/해제", self.toggle_selected), ("🖼 샘플/기준 이미지", self.open_samples),
                          ("🗑 삭제", self.delete_selected)):
            db.FlatButton(bar, text, cmd).pack(side="left", padx=(0, 6))
        for text, cmd in (("📁 폴더", self.open_folder), ("💬 Teams 테스트", self.test_teams),
                          ("📄 리포트 생성", lambda: self.generate_report(auto=False)), ("⚙ 설정", self.open_settings)):
            db.FlatButton(bar, text, cmd).pack(side="right", padx=(6, 0))

        # ---- KPI ----
        kpi = tk.Frame(self.root, bg=T["bg"])
        kpi.pack(fill="x", padx=14, pady=6)
        self.kpi = {}
        for key, title, color in (("uptime", "가동 시간", T["accent"]), ("inspections", "판정 수", T["sky"]),
                                  ("ng", "NG 감지", T["red"]), ("ok_rate", "정상률", T["green"]),
                                  ("rois", "감시 ROI", T["indigo"]), ("alarms", "현재 경보", T["amber"])):
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
        tk.Label(wall_head, text="카드 끌기: 이동 · ◢ 끌기: 크기 조절", bg=T["bg"], fg=T["muted"],
                 font=(db.F, 8)).pack(side="left", padx=12)
        db.FlatButton(wall_head, "⟲ 자동 정렬", self.reset_wall_layout, padx=10, pady=3).pack(side="right")
        self.wall = db.CameraWall(wall_box, on_select=self._select_roi, on_open=self._open_roi,
                                  on_layout=self._wall_layout_changed)
        self.wall.pack(fill="both", expand=True)
        hpaned.add(wall_box, weight=3)
        side = tk.Frame(hpaned, bg=T["bg"], width=430)
        self.feed = db.FeedPanel(side)          # 에이전트 활동 + 시스템 로그 통합
        self.feed.pack(fill="both", expand=True, pady=(0, 8))
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
            self.tree.heading(key, text=text)
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
        self.log("info", "카메라 월 배치를 자동 정렬로 되돌렸습니다")

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
            self.log("error", f"설정 저장 실패: {e}")

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
                               "에이전트 가동 중" if running else "대기 중", T["accent"] if running else T["muted"])
        self.kpi["inspections"].set(f"{k['inspections']:,}", "누적 판정")
        self.kpi["ng"].set(str(k["ng"]), "누적 이상 감지", T["red"] if k["ng"] else None)
        rate = k["ok_rate"]
        self.kpi["ok_rate"].set(f"{rate:.1f}%" if rate is not None else "—", "판정 대비 정상",
                                T["green"] if rate is not None and rate >= 99 else (T["amber"] if rate is not None else None))
        enabled = sum(r.enabled for r in self.cfg.rois)
        self.kpi["rois"].set(f"{enabled}", f"전체 {len(self.cfg.rois)}개 중 사용")
        alarms = sum(1 for s, _d in self.states.values() if s == "alarm") if running else 0
        self.kpi["alarms"].set(str(alarms), "즉시 확인 필요" if alarms else "이상 없음",
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
            kind += f" · OK{n['ok']}/NG{n['ng']}/무시{n['skip']}"
        elif roi.detector in detectors.REFERENCE_KINDS:
            n = {c: len(paths.reference_paths(roi.id, c)) for c in detectors.SAMPLE_CLASSES}
            kind += f" · OK{n['ok']}/NG{n['ng']}/무시{n['skip']}" if n["ok"] else " · 기준 없음"
        return ("✔" if roi.enabled else "–", roi.name, kind,
                f"{roi.x},{roi.y}  {roi.w}×{roi.h}", roi.assignee or "-",
                STATE_TEXT.get(state, state), detail), state

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
            messagebox.showinfo("안내", "목록에서 ROI를 하나 선택하세요.", parent=self.root)
            return None
        return rois[0]

    def _commit(self, message: Optional[str] = None):
        """설정 저장 + 실행 중인 검출에 즉시 반영."""
        try:
            cfgmod.save(self.cfg)
        except OSError as e:
            messagebox.showerror("저장 실패", f"설정을 저장할 수 없습니다.\n{e}", parent=self.root)
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
            messagebox.showerror("오류", f"화면 캡처/ROI 지정 실패: {e}", parent=self.root)
            return
        if not rects:
            return
        added = 0
        base = len(self.cfg.rois)
        for i, ((x, y, w, h), proc) in enumerate(zip(rects, processes), 1):
            roi = ROI(name=f"ROI {base + i}", x=x, y=y, w=w, h=h, expected_process=proc or "")
            result = roi_dialog.edit_roi(self.root, roi, f"새 ROI 설정 ({i}/{len(rects)}) – 취소하면 이 ROI는 추가하지 않음")
            if result is None:
                continue
            self.cfg.rois.append(result)
            added += 1
        if added:
            self._commit(f"ROI {added}개 추가")

    def edit_selected(self):
        roi = self._one_selected()
        if roi is None:
            return
        result = roi_dialog.edit_roi(self.root, roi, f"ROI 설정 – {roi.name}")
        if result is None:
            return
        note = ""
        if (result.w, result.h) != (roi.w, roi.h):
            n = worker.resize_samples(roi.id, result.w, result.h)   # 샘플은 지우지 않고 새 크기에 맞춤
            note = f" · 크기 변경 → 샘플 {n}장 새 크기로 유지" if n else ""
        self.cfg.rois[self.cfg.rois.index(roi)] = result
        self._commit(f"[{result.name}] 설정 변경{note}")

    def reposition_selected(self):
        roi = self._one_selected()
        if roi is None:
            return
        try:
            others = [r for r in self.cfg.rois if r.id != roi.id]
            rects, processes = self._select_on_screen(others, single=True)
        except Exception as e:
            log.exception("ROI 위치 지정 실패")
            messagebox.showerror("오류", f"화면 캡처/ROI 지정 실패: {e}", parent=self.root)
            return
        if not rects:
            return
        nx, ny, nw, nh = rects[0]
        note = ""
        if (nw, nh) != (roi.w, roi.h):
            keep = messagebox.askyesnocancel(
                "ROI 크기", f"새로 그린 크기 {nw}×{nh}가 기존 {roi.w}×{roi.h}와 다릅니다.\n\n"
                          f"[예] 기존 크기 {roi.w}×{roi.h}를 유지하고 위치만 이동 (권장 – 샘플 그대로 사용)\n"
                          f"[아니오] 새 크기로 변경 (샘플/기준 이미지를 새 크기에 맞춰 유지)\n[취소] 변경 안 함",
                parent=self.root)
            if keep is None:
                return
            if keep:   # 그린 영역의 중심에 기존 크기로 배치
                nx, ny, nw, nh = nx + nw // 2 - roi.w // 2, ny + nh // 2 - roi.h // 2, roi.w, roi.h
            else:
                n = worker.resize_samples(roi.id, nw, nh)
                note = f" · 샘플 {n}장 새 크기로 유지" if n else ""
        roi.x, roi.y, roi.w, roi.h = nx, ny, nw, nh
        if processes and processes[0] and not roi.expected_process:
            roi.expected_process = processes[0]
        self._commit(f"[{roi.name}] 위치 변경: {roi.x},{roi.y} {roi.w}×{roi.h} (샘플/기준 이미지 유지){note}")

    def duplicate_selected(self):
        roi = self._one_selected()
        if roi is None:
            return
        dup = copy.deepcopy(roi)
        dup.id = cfgmod.new_roi_id()
        dup.wall = []
        dup.name = f"{roi.name} 복사본"
        result = roi_dialog.edit_roi(self.root, dup, "ROI 복제")
        if result is not None:
            if (result.x, result.y, result.w, result.h) == (roi.x, roi.y, roi.w, roi.h):
                for cls in detectors.SAMPLE_CLASSES:     # 같은 위치면 샘플/기준 이미지도 복사
                    for src in paths.reference_paths(roi.id, cls):
                        shutil.copyfile(src, paths.new_reference_path(result.id, cls))
            self.cfg.rois.insert(self.cfg.rois.index(roi) + 1, result)
            self._commit(f"[{result.name}] 추가 (복제)")

    def toggle_selected(self):
        rois = self._selected_rois()
        if not rois:
            messagebox.showinfo("안내", "목록에서 ROI를 선택하세요.", parent=self.root)
            return
        new_state = not all(r.enabled for r in rois)
        for r in rois:
            r.enabled = new_state
        self._commit(f"ROI {len(rois)}개 {'사용' if new_state else '해제'}")

    def delete_selected(self):
        rois = self._selected_rois()
        if not rois:
            return
        names = ", ".join(r.name for r in rois)
        if not messagebox.askyesno("삭제 확인", f"다음 ROI를 삭제할까요?\n{names}", parent=self.root):
            return
        for r in rois:
            self.cfg.rois.remove(r)
            self.states.pop(r.id, None)
            self._delete_reference(r.id)
        self._commit(f"ROI 삭제: {names}")

    def open_samples(self):
        roi = self._one_selected()
        if roi is None:
            return
        if roi.detector not in detectors.REFERENCE_KINDS:
            messagebox.showinfo("안내", f"[{roi.name}]의 검출 유형({roi.detector_label()})은 샘플 이미지를 쓰지 않습니다.\n"
                                      "'OK/NG 이미지 매칭', '형상 검사', '기준 화면과 다름' 유형에서 사용합니다.",
                                parent=self.root)
            return
        samples_dialog.manage_samples(self.root, roi)
        self._refresh_tree()
        self.log("info", f"[{roi.name}] 샘플 이미지 갱신 (검출 중이면 바로 반영)")

    def register_sample(self, roi_id: str, cls: str, raw_path: str) -> str:
        """경보 팝업의 'OK로 등록 / NG로 등록' 버튼. 성공 시 빈 문자열, 실패 시 오류 메시지."""
        roi = self.cfg.find(roi_id)
        if roi is None:
            return "ROI가 삭제되었습니다."
        try:
            frame = worker._load_png(raw_path)
        except Exception as e:
            return f"스냅샷을 열 수 없습니다: {e}"
        if frame.shape[:2] != (roi.h, roi.w):
            return "ROI 크기가 바뀌어 등록할 수 없습니다."
        before = self._auto_threshold(roi)
        dest = paths.new_reference_path(roi_id, cls)
        shutil.copyfile(raw_path, dest)
        label = detectors.SAMPLE_CLASSES.get(cls, cls)
        self.log("info", f"[{roi.name}] 경보 화면을 {label} 샘플로 등록: {os.path.basename(dest)}")
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
            self._commit("설정 저장")

    def test_teams(self):
        rois = self._selected_rois()
        sent = 0
        for roi in rois or [None]:
            url = self.cfg.webhook_for(roi)
            name = roi.name if roi else "공통"
            err = notifier.validate_url(url)
            if err:
                self.log("warning", f"Teams 테스트 ({name}): {err}")
                continue
            payload = notifier.build_payload(
                "test", roi_name=roi.name if roi else "(테스트)",
                detector_label=roi.detector_label() if roi else "-", detail="테스트 메시지",
                assignee=roi.assignee if roi else "", assignee_email=roi.assignee_email if roi else "",
                pc_label=self.cfg.pc_label, when=worker.now_text())
            self.teams.send(url, payload, f"테스트 ({name})")
            sent += 1
        if sent:
            self.log("info", f"Teams 테스트 전송 요청 {sent}건 – 결과는 로그에 표시됩니다.")
        elif not rois:
            messagebox.showinfo("안내", "[설정]에서 공통 Webhook URL을 먼저 입력하세요.\n"
                                      "(ROI를 선택하면 해당 ROI의 담당자/Webhook으로 테스트합니다)",
                                parent=self.root)

    def open_folder(self):
        if hasattr(os, "startfile"):
            os.startfile(paths.BASE_DIR)  # type: ignore[attr-defined]

    # ================= 검출 시작/중지 =================
    def start(self):
        if self.monitor is not None:
            return
        if not any(r.enabled for r in self.cfg.rois):
            messagebox.showwarning("안내", "사용 중인 ROI가 없습니다. [화면에서 ROI 추가]로 먼저 지정하세요.",
                                   parent=self.root)
            return
        if self.cfg.teams_enabled and not any(self.cfg.webhook_for(r) for r in self.cfg.rois if r.enabled):
            self.log("warning", "Teams 알림이 켜져 있지만 Webhook URL이 없습니다. 팝업만 표시됩니다.")
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
        self.log("info", f"검출 시작 (ROI {sum(r.enabled for r in self.cfg.rois)}개, "
                         f"{self.cfg.interval_sec:g}초 주기)")
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
            status = ("⚠ 응답 없음" if not ok else
                      f"● 감시 중 · 경보 {alarms}건" if alarms else "● 실시간 감시 중 · 이상 없음")
            self.mini.update([t for t in trends if t["enabled"]], status, ok and not alarms)

    def _update_running_ui(self):
        running = self.monitor is not None
        self.btn_start.set_enabled(not running)
        self.btn_stop.set_enabled(running)
        self.status_pill.configure(text="●  AGENT ONLINE · 실시간 감시 중" if running else "○  STANDBY · 대기",
                                   fg="#04130a" if running else db.T["muted"],
                                   bg=db.T["green"] if running else db.T["card"])
        self.root.title(f"{APP_TITLE} – {'감시 중' if running else '대기'}")
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
                    self.log("warning", "이 Windows는 화면 표시를 캡처에서 제외하지 못합니다(Windows 10 2004 이상 필요). "
                                        "ROI끼리 붙어 있으면 테두리가 옆 ROI 판정에 영향을 줄 수 있으니 [설정]에서 화면 표시를 끄세요.")
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
                    self.agent.say("warn", f"검출 엔진 응답 없음 {int(time.monotonic() - self._last_status)}초 – 감시 중")
                if self.agent.due_shift(self.cfg.shift_times):
                    self.generate_report(auto=True)
            if on:
                self._refresh_kpis()
            if self._beat % 60 == 1:
                self.trend.draw(self.agent.hourly_series(12))
            if self._beat % 4 == 1:
                self._refresh_trends()
            if self._beat % 7200 == 0:             # 1시간마다 보관 기간 정리
                self._purge_old_files()
        except tk.TclError:
            log.exception("대시보드 갱신 오류")
        self.root.after(500, self._heartbeat)

    # ================= 에이전트 행동 =================
    def _run_actions(self, actions):
        for act in actions:
            if act.kind == "restart":
                self.root.after(5000, self._auto_restart)
            elif act.kind == "teams":
                self._send_agent_message(act.title, act.message, escalation=True)

    def _auto_restart(self):
        if self.monitor is None:
            self.log("warning", "에이전트: 검출 엔진 자동 재시작")
            self.start()

    def _send_agent_message(self, title: str, message: str, escalation: bool):
        if not self.cfg.teams_enabled or (escalation and not self.cfg.agent_escalation):
            self.agent.say("act", "Teams 알림 꺼짐 – 대시보드에만 기록")
            return
        url = self.cfg.webhook_for(None)
        if notifier.validate_url(url):
            self.agent.say("warn", "공통 Webhook URL이 없어 Teams 전송 생략")
            return
        payload = notifier.build_agent_payload(title, message, pc_label=self.cfg.pc_label, when=worker.now_text())
        self.teams.send(url, payload, f"에이전트: {title}")

    def generate_report(self, auto: bool):
        """근무 리포트(HTML) 작성. 자동(교대 시각)이면 Teams로 요약 전송, 수동이면 바로 열기."""
        now = datetime.now()
        title = f"FMVS 근무 리포트 {now:%Y-%m-%d %H:%M}"
        try:
            paths.ensure_dirs()
            path = os.path.join(paths.REPORT_DIR, f"report_{now:%Y%m%d_%H%M}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.agent.report_html(title, self.cfg.rois, frames=dict(self.latest_frames)))
        except OSError as e:
            self.log("error", f"리포트 저장 실패: {e}")
            return None
        summary = self.agent.report_summary()
        self.agent.say("act", f"{'교대 시각 도래 → ' if auto else ''}근무 리포트 작성: {os.path.basename(path)} ({summary})")
        if auto and self.cfg.report_to_teams:
            self._send_agent_message(title, summary + f"\n리포트 파일: {path}", escalation=False)
        if not auto and hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
        return path

    def _update_status_bar(self):
        running = self.monitor is not None
        enabled = sum(r.enabled for r in self.cfg.rois)
        alarms = sum(1 for s, _d in self.states.values() if s == "alarm")
        teams = "Teams 알림 켜짐" if self.cfg.teams_enabled else "Teams 알림 꺼짐"
        self.status_var.set(f"{'● 검출 중' if running else '○ 중지됨'}   |   ROI {enabled}/{len(self.cfg.rois)}개 사용"
                            f"   |   경보 {alarms}건   |   {teams}   |   설정 파일: {paths.SETTINGS_PATH}")

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
                    tag = "재알림" if info["kind"] == "repeat" else "이상 감지"
                    self.log("error", f"🚨 [{info['roi_name']}] {tag} – {info['detail']}")
                    count = self.consecutive.get(info["roi_id"], 0) + 1
                    self.consecutive[info["roi_id"]] = count
                    info["consecutive"] = count
                    actions = self.agent.on_alert(info)
                    info["total_ng"] = self.agent.stats[info["roi_id"]].ng
                    need = max(1, self.cfg.popup_consecutive)
                    if self.cfg.popup_enabled and count >= need:
                        self.alerts.alert(info)
                    elif self.cfg.popup_enabled:
                        self.log("info", f"[{info['roi_name']}] 연속 NG {count}/{need}회 – {need}회부터 팝업")
                    self._run_actions(actions)
                    self._refresh_trends()
                elif kind == "recover":
                    info = event[1]
                    self.log("info", f"✅ [{info['roi_name']}] 정상 복구 – {info['detail']}")
                    self.alerts.recover(info)
                    self.agent.on_recover(info)
                elif kind == "log":
                    self.log(event[1], event[2])
                elif kind == "stopped":
                    if self.monitor is not None and not self.monitor.is_alive():
                        self.monitor = None
                        self.states.clear()
                        self._update_running_ui()
                    self.log("warning" if "오류" in event[1] else "info", f"검출 중지 ({event[1]})")
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
        self.feed.add(agentmod.FeedItem(time.time(), kind, message))

    def _purge_old_files(self):
        try:
            removed = housekeeping.purge(self.cfg.retention_days)
            if removed:
                self.log("info", f"보관 기간({self.cfg.retention_days}일) 지난 로그·스냅샷·리포트 {removed}개 정리")
        except Exception:
            log.exception("보관 기간 정리 실패")

    def _on_tk_error(self, exc, value, tb):
        log.error("UI 오류", exc_info=(exc, value, tb))
        messagebox.showerror("오류", f"예기치 않은 오류가 발생했습니다.\n{value}\n\n자세한 내용은 logs 폴더를 확인하세요.",
                             parent=self.root)

    def _on_close(self):
        if self.monitor is not None:
            if not messagebox.askyesno("종료", "검출이 실행 중입니다. 종료하면 감시가 멈춥니다.\n종료할까요?",
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

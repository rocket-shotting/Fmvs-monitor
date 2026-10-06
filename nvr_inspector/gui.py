"""메인 창: ROI 목록/상태, 검출 시작·중지, ROI 추가·편집, 설정, Teams 테스트, 로그."""
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

import alert
import config as cfgmod
import detectors
import notifier
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

APP_TITLE = "NVR 화면 이상 검출기"
_MAX_LOG_LINES = 500

STATE_TEXT = {
    "idle": "-", "ok": "정상", "pending": "이상 감지(확인 중)", "alarm": "🚨 경보",
    "skip": "건너뜀(다른 화면)", "wait": "대기", "off": "꺼짐", "error": "오류",
}
STATE_COLOR = {
    "ok": "#1b5e20", "pending": "#e65100", "alarm": "#b71c1c", "skip": "#616161",
    "wait": "#0d47a1", "off": "#9e9e9e", "error": "#880e4f", "idle": "#000000",
}
COLUMNS = (("enabled", "사용", 50), ("name", "이름", 150), ("detector", "검출 유형", 190),
           ("rect", "위치 (X,Y 폭×높이)", 170), ("assignee", "담당자", 120),
           ("state", "상태", 130), ("detail", "측정값 / 상세", 330))


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1200x640")
        self.root.minsize(900, 480)
        self.root.report_callback_exception = self._on_tk_error

        self.cfg: AppConfig = cfgmod.load()
        self.events: "queue.Queue" = queue.Queue()
        self.teams = notifier.TeamsNotifier(self._report_threadsafe)
        self.monitor: Optional[worker.Monitor] = None
        self.alerts = alert.AlertManager(self.root, on_register=self.register_sample)
        self.states: Dict[str, tuple] = {}

        self._build()
        self._update_running_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(200, self._poll_events)
        if self.cfg.auto_start and self.cfg.rois:
            self.root.after(800, self.start)

    # ================= 화면 구성 =================
    def _build(self):
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=26)

        bar = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self.btn_start = ttk.Button(bar, text="▶ 검출 시작", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="■ 검출 중지", command=self.stop)
        self.btn_stop.pack(side="left", padx=(4, 12))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        for text, cmd in (("＋ 화면에서 ROI 추가", self.add_rois), ("편집", self.edit_selected),
                          ("위치 다시 지정", self.reposition_selected), ("복제", self.duplicate_selected),
                          ("사용/해제", self.toggle_selected), ("샘플/기준 이미지", self.open_samples),
                          ("삭제", self.delete_selected)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        for text, cmd in (("⚙ 설정", self.open_settings), ("Teams 테스트", self.test_teams),
                          ("폴더 열기", self.open_folder)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)

        paned = ttk.PanedWindow(self.root, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        tree_frame = ttk.Frame(paned)
        self.tree = ttk.Treeview(tree_frame, columns=[c[0] for c in COLUMNS], show="headings",
                                 selectmode="extended")
        for key, text, width in COLUMNS:
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor="center" if key in ("enabled", "state") else "w",
                             stretch=key == "detail")
        for state, color in STATE_COLOR.items():
            self.tree.tag_configure(state, foreground=color)
        self.tree.tag_configure("alarm", foreground=STATE_COLOR["alarm"], background="#ffebee")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        paned.add(tree_frame, weight=3)

        log_frame = ttk.LabelFrame(paned, text="로그", padding=4)
        self.log_text = tk.Text(log_frame, height=8, state="disabled", wrap="none", font=("맑은 고딕", 9))
        lsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        for level, color in (("error", "#b71c1c"), ("warning", "#e65100"), ("info", "#000000")):
            self.log_text.tag_configure(level, foreground=color)
        paned.add(log_frame, weight=1)

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(8, 2)).pack(fill="x")

    # ================= 목록 =================
    def _row_values(self, roi: ROI):
        if self.monitor is None:
            state, detail = ("off", "") if not roi.enabled else ("idle", "")
        else:
            state, detail = self.states.get(roi.id, ("idle", ""))
        kind = roi.detector_label()
        if roi.detector == "match":
            n = {c: len(paths.reference_paths(roi.id, c)) for c in detectors.SAMPLE_CLASSES}
            kind += f" · OK {n['ok']} / NG {n['ng']} / 무시 {n['skip']}"
        elif roi.detector in detectors.REFERENCE_KINDS:
            n = len(paths.reference_paths(roi.id))
            kind += f" · 기준 {n}장" if n else " · 기준 없음"
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
        self._update_status_bar()

    def _update_row(self, roi_id: str):
        roi = self.cfg.find(roi_id)
        if roi is None or not self.tree.exists(roi_id):
            return
        values, state = self._row_values(roi)
        self.tree.item(roi_id, values=values, tags=(state,))

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
        if message:
            self.log("info", message)

    # ================= ROI 조작 =================
    def _select_on_screen(self, existing, single):
        """메인 창을 숨기고 화면을 캡처한 뒤 오버레이에서 ROI를 그린다.
        반환: (사각형 목록 또는 None, 각 사각형 중심의 프로그램 이름 목록)"""
        try:
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
        if (result.x, result.y, result.w, result.h) != (roi.x, roi.y, roi.w, roi.h):
            self._delete_reference(roi.id)
        self.cfg.rois[self.cfg.rois.index(roi)] = result
        self._commit(f"[{result.name}] 설정 변경")

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
        roi.x, roi.y, roi.w, roi.h = rects[0]
        if processes and processes[0] and not roi.expected_process:
            roi.expected_process = processes[0]
        self._delete_reference(roi.id)
        hint = " – 기준 이미지를 다시 저장하세요" if roi.detector in detectors.REFERENCE_KINDS else ""
        self._commit(f"[{roi.name}] 위치 변경: {roi.x},{roi.y} {roi.w}×{roi.h}{hint}")

    def duplicate_selected(self):
        roi = self._one_selected()
        if roi is None:
            return
        dup = copy.deepcopy(roi)
        dup.id = cfgmod.new_roi_id()
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
        dest = paths.new_reference_path(roi_id, cls)
        shutil.copyfile(raw_path, dest)
        label = detectors.SAMPLE_CLASSES.get(cls, cls)
        self.log("info", f"[{roi.name}] 경보 화면을 {label} 샘플로 등록: {os.path.basename(dest)}")
        self._refresh_tree()
        return ""

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
        self.monitor.start()
        self.log("info", f"검출 시작 (ROI {sum(r.enabled for r in self.cfg.rois)}개, "
                         f"{self.cfg.interval_sec:g}초 주기)")
        self._update_running_ui()
        if self.cfg.minimize_on_start:
            self.root.after(300, self.root.iconify)

    def stop(self):
        if self.monitor is None:
            return
        self.monitor.stop()
        self.monitor.join(timeout=5)
        self.monitor = None
        self.states.clear()
        self._update_running_ui()

    def _update_running_ui(self):
        running = self.monitor is not None
        self.btn_start.state(["disabled"] if running else ["!disabled"])
        self.btn_stop.state(["!disabled"] if running else ["disabled"])
        self.root.title(f"{APP_TITLE} – {'검출 중' if running else '중지됨'}")
        self._refresh_tree()

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
        try:
            for _ in range(1000):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "status":
                    _k, roi_id, state, detail = event
                    if (self.monitor is not None and self.cfg.find(roi_id) is not None
                            and self.states.get(roi_id) != (state, detail)):
                        self.states[roi_id] = (state, detail)
                        self._update_row(roi_id)
                        changed = True
                elif kind == "alert":
                    info = event[1]
                    tag = "재알림" if info["kind"] == "repeat" else "이상 감지"
                    self.log("error", f"🚨 [{info['roi_name']}] {tag} – {info['detail']}")
                    if self.cfg.popup_enabled:
                        self.alerts.alert(info)
                elif kind == "recover":
                    info = event[1]
                    self.log("info", f"✅ [{info['roi_name']}] 정상 복구 – {info['detail']}")
                    self.alerts.recover(info)
                elif kind == "log":
                    self.log(event[1], event[2])
                elif kind == "stopped":
                    if self.monitor is not None and not self.monitor.is_alive():
                        self.monitor = None
                        self.states.clear()
                        self._update_running_ui()
                    self.log("warning" if "오류" in event[1] else "info", f"검출 중지 ({event[1]})")
        except queue.Empty:
            pass
        if changed:
            self._update_status_bar()
        self.root.after(200, self._poll_events)

    def log(self, level: str, message: str):
        getattr(log, level if level in ("info", "warning", "error") else "info")(message)
        line = f"[{datetime.now():%H:%M:%S}] {message}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, level)
        excess = int(self.log_text.index("end-1c").split(".")[0]) - _MAX_LOG_LINES
        if excess > 0:
            self.log_text.delete("1.0", f"{excess + 1}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

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
        self.root.destroy()

    def run(self):
        self.root.mainloop()

"""검출 스레드. ROI별로 화면을 캡처해 판정하고, 이상 상태가 지속되면 알림 이벤트를 만든다.

GUI와는 queue로만 통신한다:
  ("status", roi_id, state, detail)   state: ok | pending | alarm | skip | wait | off | error
  ("alert",  info dict)               최초 경보/재알림
  ("recover", info dict)              정상 복구
  ("log", level, message)
  ("stopped", reason)"""
import copy
import logging
import os
import queue
import re
import threading
import time
from datetime import datetime
from typing import Dict, Optional

import numpy as np

import detectors
import notifier
import paths
import winutil
from capture import Grabber
from config import ROI, AppConfig

log = logging.getLogger(__name__)

_ERROR_LOG_INTERVAL = 60.0   # 같은 ROI의 같은 오류는 1분에 한 번만 로그


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_reference(roi_id: str) -> Optional[np.ndarray]:
    path = paths.reference_path(roi_id)
    if not os.path.exists(path):
        return None
    from PIL import Image
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))


def save_png(rgb: np.ndarray, path: str) -> None:
    from PIL import Image
    tmp = path + ".tmp.png"
    Image.fromarray(rgb).save(tmp)
    os.replace(tmp, path)


def _safe_filename(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_") or "roi"


class RoiRuntime:
    def __init__(self, signature: str):
        self.signature = signature
        self.abnormal_since: Optional[float] = None
        self.alerted = False
        self.last_alert = 0.0
        self.det_state: dict = {}
        self.last_error = ""
        self.last_error_at = 0.0


class Monitor(threading.Thread):
    def __init__(self, cfg: AppConfig, events: "queue.Queue", teams: notifier.TeamsNotifier):
        super().__init__(name="NVRMonitor", daemon=True)
        self._cfg = copy.deepcopy(cfg)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._events = events
        self._teams = teams
        self._runtime: Dict[str, RoiRuntime] = {}
        self._refs: Dict[str, tuple] = {}   # roi_id -> (mtime, array)

    # ---- GUI에서 호출 ----
    def update_config(self, cfg: AppConfig) -> None:
        with self._lock:
            self._cfg = copy.deepcopy(cfg)

    def stop(self) -> None:
        self._stop_event.set()

    # ---- 스레드 본체 ----
    def run(self) -> None:
        reason = "사용자 중지"
        try:
            with Grabber() as grabber:
                while not self._stop_event.is_set():
                    started = time.monotonic()
                    with self._lock:
                        cfg = self._cfg
                    self._tick(cfg, grabber)
                    elapsed = time.monotonic() - started
                    self._stop_event.wait(max(0.05, cfg.interval_sec - elapsed))
        except Exception as e:
            log.exception("검출 스레드 비정상 종료")
            reason = f"오류로 중지됨: {e}"
        self._events.put(("stopped", reason))

    def _emit(self, *event) -> None:
        self._events.put(event)

    def _tick(self, cfg: AppConfig, grabber: Grabber) -> None:
        alive = set()
        for roi in cfg.rois:
            if self._stop_event.is_set():
                return
            alive.add(roi.id)
            sig = roi.signature()
            rt = self._runtime.get(roi.id)
            if rt is None or rt.signature != sig:
                rt = RoiRuntime(sig)
                self._runtime[roi.id] = rt
            if not roi.enabled:
                rt.abnormal_since, rt.alerted = None, False
                self._emit("status", roi.id, "off", "사용 안 함")
                continue
            try:
                self._check(cfg, roi, rt, grabber)
            except Exception as e:
                msg = f"{e.__class__.__name__}: {e}"
                now = time.monotonic()
                if msg != rt.last_error or now - rt.last_error_at > _ERROR_LOG_INTERVAL:
                    rt.last_error, rt.last_error_at = msg, now
                    log.exception("[%s] 검사 오류", roi.name)
                    self._emit("log", "error", f"[{roi.name}] 검사 오류: {msg}")
                self._emit("status", roi.id, "error", msg)
        for stale in set(self._runtime) - alive:
            del self._runtime[stale]
            self._refs.pop(stale, None)

    def _reference(self, roi_id: str) -> Optional[np.ndarray]:
        path = paths.reference_path(roi_id)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            self._refs.pop(roi_id, None)
            return None
        cached = self._refs.get(roi_id)
        if cached and cached[0] == mtime:
            return cached[1]
        arr = load_reference(roi_id)
        self._refs[roi_id] = (mtime, arr)
        return arr

    def _check(self, cfg: AppConfig, roi: ROI, rt: RoiRuntime, grabber: Grabber) -> None:
        # 1) ROI 위치에 지정한 프로그램(NVR)이 보이는지 확인. 다른 창이 덮고 있으면 판정하지 않는다.
        if roi.expected_process and winutil.IS_WINDOWS:
            cx, cy = roi.center()
            proc = winutil.process_name_at(cx, cy)
            if proc is None or proc.lower() != roi.expected_process.lower():
                rt.abnormal_since = None
                rt.det_state.clear()
                self._emit("status", roi.id, "skip", f"다른 화면: {proc or '확인 불가(화면 잠금 등)'}")
                return

        # 2) 캡처 + 판정
        frame = grabber.grab(roi.x, roi.y, roi.w, roi.h)
        ref = self._reference(roi.id) if roi.detector == "reference" else None
        res = detectors.evaluate(roi.detector, roi.params, frame, rt.det_state, reference=ref)
        now = time.time()

        if res.abnormal is None:
            rt.abnormal_since = None
            self._emit("status", roi.id, "wait", res.detail)
            return

        if not res.abnormal:
            if rt.alerted:
                elapsed = now - rt.abnormal_since if rt.abnormal_since else None
                self._fire(cfg, roi, "recover", res.detail, elapsed, None)
            rt.abnormal_since, rt.alerted = None, False
            self._emit("status", roi.id, "ok", res.detail)
            return

        # 3) 이상 – 지속 시간 확인 후 경보
        if rt.abnormal_since is None:
            rt.abnormal_since = now
        elapsed = now - rt.abnormal_since
        if elapsed < roi.duration_sec:
            self._emit("status", roi.id, "pending",
                       f"{res.detail} · {elapsed:.0f}/{roi.duration_sec:.0f}초")
            return
        repeat_due = roi.repeat_min > 0 and now - rt.last_alert >= roi.repeat_min * 60
        if not rt.alerted or repeat_due:
            kind = "repeat" if rt.alerted else "alert"
            snapshot = self._save_snapshot(roi, frame)
            self._fire(cfg, roi, kind, res.detail, elapsed, snapshot)
            rt.alerted, rt.last_alert = True, now
        self._emit("status", roi.id, "alarm", f"{res.detail} · {notifier.fmt_duration(elapsed)} 지속")

    def _save_snapshot(self, roi: ROI, frame: np.ndarray) -> Optional[str]:
        try:
            name = f"{datetime.now():%Y%m%d_%H%M%S}_{_safe_filename(roi.name)}.png"
            path = os.path.join(paths.SNAPSHOT_DIR, name)
            save_png(frame, path)
            return path
        except Exception as e:
            log.warning("스냅샷 저장 실패: %s", e)
            return None

    def _fire(self, cfg: AppConfig, roi: ROI, kind: str, detail: str,
              elapsed: Optional[float], snapshot: Optional[str]) -> None:
        when = now_text()
        info = {
            "kind": kind, "roi_id": roi.id, "roi_name": roi.name,
            "detector": roi.detector_label(), "detail": detail, "elapsed": elapsed,
            "assignee": roi.assignee, "assignee_email": roi.assignee_email,
            "time": when, "snapshot": snapshot,
        }
        label = {"alert": "이상 감지", "repeat": "재알림", "recover": "복구"}[kind]
        log.warning("[%s] %s – %s", roi.name, label, detail)
        self._emit("recover" if kind == "recover" else "alert", info)
        if not cfg.teams_enabled:
            return
        if kind == "recover" and not roi.notify_recovery:
            return
        payload = notifier.build_payload(
            kind, roi_name=roi.name, detector_label=roi.detector_label(), detail=detail,
            assignee=roi.assignee, assignee_email=roi.assignee_email,
            pc_label=cfg.pc_label, when=when, elapsed_sec=elapsed)
        self._teams.send(cfg.webhook_for(roi), payload, f"{roi.name} {label}")

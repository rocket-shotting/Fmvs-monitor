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
from typing import Dict, List, Optional

import numpy as np

import detectors
import notifier
import paths
import winutil
from capture import Grabber
from config import ROI, AppConfig

log = logging.getLogger(__name__)

_ERROR_LOG_INTERVAL = 60.0   # 같은 ROI의 같은 오류는 1분에 한 번만 로그
_UNION_MIN_ROIS = 4          # ROI가 이 개수 이상이면 전체 영역을 한 번에 캡처해서 잘라 쓴다
_UNION_MAX_PIXELS = 16_000_000
THUMB_INTERVAL = 1.0         # 대시보드 썸네일 전송 간격(초)
THUMB_MAX_SIDE = 320


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_png(path: str) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))


def load_references(roi_id: str) -> List[np.ndarray]:
    return [_load_png(path) for path in paths.reference_paths(roi_id)]


def load_samples(roi_id: str) -> Dict[str, List[np.ndarray]]:
    """OK/NG/무시 샘플 이미지 전체."""
    return {cls: [_load_png(p) for p in paths.reference_paths(roi_id, cls)]
            for cls in detectors.SAMPLE_CLASSES}


def load_for_detector(roi_id: str, detector: str):
    """검출 유형에 맞는 샘플 이미지 – 매칭·형상·기준화면 모두 OK/NG/무시 클래스별 dict."""
    if detector in detectors.REFERENCE_KINDS:
        return load_samples(roi_id)
    return None


def resize_samples(roi_id: str, w: int, h: int) -> int:
    """ROI 크기가 바뀌었을 때 샘플/기준 이미지를 새 크기로 맞춘다 (삭제하지 않고 유지). 반환: 바꾼 장수."""
    from PIL import Image
    changed = 0
    for cls in detectors.SAMPLE_CLASSES:
        for path in paths.reference_paths(roi_id, cls):
            with Image.open(path) as img:
                if img.size == (w, h):
                    continue
                resized = img.convert("RGB").resize((w, h), Image.LANCZOS)
            save_png(np.asarray(resized), path)
            changed += 1
    return changed


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
        # 정지 시에만 판정 모드
        self.motion_prev = None
        self.still_count = 0
        self.inspected = False          # 이번 정지에서 이미 판정했는지
        self.last_result = ("wait", "")  # 이번 정지의 판정 결과 (상태, 상세)
        self.last_frame_sent = 0.0       # 대시보드 썸네일 전송 시각
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
        self._refs: Dict[str, tuple] = {}   # roi_id -> ((파일, 수정시각)…, 배열 목록)
        self._clock = time.time              # 테스트에서 교체 가능
        self._union = None                   # (x0, y0, 전체 캡처) – 한 번에 캡처한 화면
        self.send_frames = False             # 대시보드 썸네일 전송 여부

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

    def _prefetch(self, cfg: AppConfig, grabber: Grabber) -> None:
        """ROI가 많으면 감싸는 영역을 한 번에 캡처 (캡처 호출 횟수 감소 + 모든 ROI 같은 순간 판정)."""
        self._union = None
        rois = [r for r in cfg.rois if r.enabled]
        if len(rois) < _UNION_MIN_ROIS:
            return
        x0, y0 = min(r.x for r in rois), min(r.y for r in rois)
        x1, y1 = max(r.x + r.w for r in rois), max(r.y + r.h for r in rois)
        if (x1 - x0) * (y1 - y0) > _UNION_MAX_PIXELS:
            return
        try:
            self._union = (x0, y0, grabber.grab(x0, y0, x1 - x0, y1 - y0))
        except Exception as e:
            log.warning("전체 영역 캡처 실패, ROI별 캡처로 진행: %s", e)

    def _grab(self, roi: ROI, grabber: Grabber) -> np.ndarray:
        if self._union is not None:
            x0, y0, big = self._union
            frame = big[roi.y - y0:roi.y - y0 + roi.h, roi.x - x0:roi.x - x0 + roi.w]
            if frame.shape[:2] == (roi.h, roi.w):
                return frame
        return grabber.grab(roi.x, roi.y, roi.w, roi.h)

    def _tick(self, cfg: AppConfig, grabber: Grabber) -> None:
        alive = set()
        self._prefetch(cfg, grabber)
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

    def _references(self, roi: ROI):
        """기준/샘플 이미지 (파일이 바뀌었을 때만 다시 읽음)."""
        classes = list(detectors.SAMPLE_CLASSES)
        files = [f for c in classes for f in paths.reference_paths(roi.id, c)]
        try:
            key = (roi.detector, tuple((f, os.path.getmtime(f)) for f in files))
        except OSError:
            key = None
        cached = self._refs.get(roi.id)
        if key is not None and cached and cached[0] == key:
            return cached[1]
        data = load_for_detector(roi.id, roi.detector)
        self._refs[roi.id] = (key, data)
        return data

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
        frame = self._grab(roi, grabber)
        self._send_thumbnail(roi, rt, frame)
        if roi.still_only and roi.detector != "frozen":
            self._check_on_stop(cfg, roi, rt, frame)
            return
        ref = self._references(roi) if roi.detector in detectors.REFERENCE_KINDS else None
        res = detectors.evaluate(roi.detector, roi.params, frame, rt.det_state, reference=ref)
        now = self._clock()

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
            snapshot, raw = self._save_snapshot(roi, frame, res.mask)
            self._fire(cfg, roi, kind, res.detail, elapsed, snapshot, raw)
            rt.alerted, rt.last_alert = True, now
        self._emit("status", roi.id, "alarm", f"{res.detail} · {notifier.fmt_duration(elapsed)} 지속")

    def _send_thumbnail(self, roi: ROI, rt: RoiRuntime, frame: np.ndarray) -> None:
        """대시보드 카메라 월에 띄울 축소 이미지 (ROI당 초당 1회 이하)."""
        if not self.send_frames:
            return
        now = time.monotonic()
        if now - rt.last_frame_sent < THUMB_INTERVAL:
            return
        rt.last_frame_sent = now
        step = max(1, -(-max(frame.shape[:2]) // THUMB_MAX_SIDE))
        self._emit("frame", roi.id, np.ascontiguousarray(frame[::step, ::step]))

    def _check_on_stop(self, cfg: AppConfig, roi: ROI, rt: RoiRuntime, frame: np.ndarray) -> None:
        """움직이는 동안은 판정하지 않고, 정지가 확인된 순간 1회만 판정한다.
        정지마다 독립 판정: NG면 그때마다 경보, 직전 경보 후 OK면 복구."""
        gray = detectors.motion_gray(frame)
        motion = detectors.motion_amount(rt.motion_prev, gray)
        rt.motion_prev = gray
        if motion is None or motion > roi.still_diff:
            rt.still_count, rt.inspected = 0, False
            amount = "-" if motion is None else f"{motion:.1f}"
            self._emit("status", roi.id, "moving", f"움직임 – 정지 대기 (변화량 {amount} > {roi.still_diff:g})")
            return
        rt.still_count += 1
        if rt.still_count < roi.still_frames:
            self._emit("status", roi.id, "moving",
                       f"정지 확인 중 {rt.still_count}/{roi.still_frames} (변화량 {motion:.1f})")
            return
        if rt.inspected:   # 이번 정지는 이미 판정함 → 결과 유지
            self._emit("status", roi.id, *rt.last_result)
            return

        rt.inspected = True
        ref = self._references(roi) if roi.detector in detectors.REFERENCE_KINDS else None
        res = detectors.evaluate(roi.detector, roi.params, frame, rt.det_state, reference=ref)
        stamp = f"[정지 판정 {datetime.now():%H:%M:%S}] "
        if res.abnormal is None:
            rt.last_result = ("wait", stamp + res.detail)
        elif res.abnormal:
            snapshot, raw = self._save_snapshot(roi, frame, res.mask)
            self._fire(cfg, roi, "alert", res.detail, None, snapshot, raw)
            rt.alerted, rt.last_alert = True, self._clock()
            rt.last_result = ("alarm", stamp + res.detail)
        else:
            if rt.alerted:
                self._fire(cfg, roi, "recover", res.detail, None, None)
            rt.alerted = False
            rt.last_result = ("ok", stamp + res.detail)
        self._emit("status", roi.id, *rt.last_result)

    def _save_snapshot(self, roi: ROI, frame: np.ndarray, mask):
        """원본(샘플 등록용)과, 불량 위치가 있으면 빨간 표시본을 저장. 반환: (보기용, 원본)."""
        try:
            base = os.path.join(paths.SNAPSHOT_DIR,
                                f"{datetime.now():%Y%m%d_%H%M%S}_{_safe_filename(roi.name)}")
            raw = base + ".png"
            save_png(frame, raw)
            if mask is None or not mask.any():
                return raw, raw
            marked = base + "_표시.png"
            save_png(detectors.overlay_defects(frame, mask), marked)
            return marked, raw
        except Exception as e:
            log.warning("스냅샷 저장 실패: %s", e)
            return None, None

    def _fire(self, cfg: AppConfig, roi: ROI, kind: str, detail: str,
              elapsed: Optional[float], snapshot: Optional[str], raw: Optional[str] = None) -> None:
        when = now_text()
        info = {
            "kind": kind, "roi_id": roi.id, "roi_name": roi.name,
            "detector": roi.detector_label(), "detail": detail, "elapsed": elapsed,
            "assignee": roi.assignee, "assignee_email": roi.assignee_email,
            "time": when, "snapshot": snapshot, "raw_snapshot": raw,
            "roi_detector": roi.detector,
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

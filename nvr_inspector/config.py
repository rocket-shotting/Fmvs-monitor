"""설정(settings.json) 구조, 로드/저장, 구버전(단일 ROI) 설정 자동 변환."""
import copy
import json
import logging
import os
import shutil
import socket
import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional

import detectors
import paths

log = logging.getLogger(__name__)

CONFIG_VERSION = 2


def new_roi_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class ROI:
    id: str = field(default_factory=new_roi_id)
    name: str = "새 ROI"
    enabled: bool = True
    x: int = 0
    y: int = 0
    w: int = 100
    h: int = 100
    detector: str = "black"
    params: dict = field(default_factory=lambda: detectors.default_params("black"))
    duration_sec: float = 5.0          # 이 시간 이상 이상 상태가 지속되어야 경보
    repeat_min: float = 0.0            # 경보 지속 중 재알림 간격(분), 0 = 재알림 안 함
    notify_recovery: bool = True       # 정상 복구 시 알림
    assignee: str = ""                 # 담당자 이름
    assignee_email: str = ""           # 담당자 Teams(회사) 이메일
    webhook_url: str = ""              # 비우면 공통 Webhook 사용
    expected_process: str = ""         # ROI 위치에 있어야 하는 프로그램(예: NVR_VIEWER.exe). 비우면 검사 안 함
    still_only: bool = False           # 대상이 움직이는 동안은 판정하지 않고, 정지한 순간 1회만 판정
    still_diff: float = 3.0            # 이 값 이하의 화면 변화량이면 '정지'로 본다 (밝기 0~255 평균 차)
    still_frames: int = 2              # 연속 몇 번 변화가 없어야 정지로 확정할지

    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def signature(self) -> str:
        """판정 상태를 초기화해야 하는 변경(위치/유형/조건)을 구분하기 위한 값."""
        return json.dumps([self.x, self.y, self.w, self.h, self.detector, self.params,
                           self.expected_process.lower(), self.still_only, self.still_diff,
                           self.still_frames], sort_keys=True)

    def detector_label(self) -> str:
        return detectors.DETECTORS.get(self.detector, {}).get("label", self.detector)


@dataclass
class AppConfig:
    version: int = CONFIG_VERSION
    interval_sec: float = 1.0
    teams_enabled: bool = False
    webhook_url: str = ""
    popup_enabled: bool = True
    sound_enabled: bool = True
    auto_start: bool = False
    minimize_on_start: bool = True
    pc_label: str = field(default_factory=socket.gethostname)
    rois: List[ROI] = field(default_factory=list)

    def find(self, roi_id: str) -> Optional[ROI]:
        return next((r for r in self.rois if r.id == roi_id), None)

    def webhook_for(self, roi: Optional[ROI]) -> str:
        if roi is not None and roi.webhook_url.strip():
            return roi.webhook_url.strip()
        return self.webhook_url.strip()


def _to_int(v, default=0) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _to_float(v, default, lo=None, hi=None) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        f = max(lo, f)
    if hi is not None:
        f = min(hi, f)
    return f


def roi_from_dict(d: dict) -> ROI:
    roi = ROI()
    roi.id = str(d.get("id") or new_roi_id())
    roi.name = str(d.get("name") or "ROI")
    roi.enabled = bool(d.get("enabled", True))
    roi.x, roi.y = _to_int(d.get("x")), _to_int(d.get("y"))
    roi.w, roi.h = max(1, _to_int(d.get("w"), 100)), max(1, _to_int(d.get("h"), 100))
    kind = d.get("detector", "black")
    roi.detector = kind if kind in detectors.DETECTORS else "black"
    roi.params = detectors.normalize_params(roi.detector, d.get("params"))
    roi.duration_sec = _to_float(d.get("duration_sec"), 5.0, 0.0, 86400.0)
    roi.repeat_min = _to_float(d.get("repeat_min"), 0.0, 0.0, 1440.0)
    roi.notify_recovery = bool(d.get("notify_recovery", True))
    for key in ("assignee", "assignee_email", "webhook_url", "expected_process"):
        setattr(roi, key, str(d.get(key) or "").strip())
    roi.still_only = bool(d.get("still_only", False))
    roi.still_diff = _to_float(d.get("still_diff"), 3.0, 0.1, 255.0)
    roi.still_frames = max(1, min(20, _to_int(d.get("still_frames"), 2)))
    return roi


def config_from_dict(d: dict) -> AppConfig:
    cfg = AppConfig()
    cfg.interval_sec = _to_float(d.get("interval_sec"), 1.0, 0.2, 60.0)
    cfg.teams_enabled = bool(d.get("teams_enabled", False))
    cfg.webhook_url = str(d.get("webhook_url") or "").strip()
    cfg.popup_enabled = bool(d.get("popup_enabled", True))
    cfg.sound_enabled = bool(d.get("sound_enabled", True))
    cfg.auto_start = bool(d.get("auto_start", False))
    cfg.minimize_on_start = bool(d.get("minimize_on_start", True))
    cfg.pc_label = str(d.get("pc_label") or socket.gethostname())
    seen = set()
    for item in d.get("rois") or []:
        if not isinstance(item, dict):
            continue
        roi = roi_from_dict(item)
        if roi.id in seen:
            roi.id = new_roi_id()
        seen.add(roi.id)
        cfg.rois.append(roi)
    return cfg


def _first(d: dict, keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _parse_rect(value):
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return [_to_int(v) for v in value]
    if isinstance(value, dict):
        x = _first(value, ["x", "left"])
        y = _first(value, ["y", "top"])
        w = _first(value, ["w", "width"])
        h = _first(value, ["h", "height"])
        if None not in (x, y, w, h):
            return [_to_int(x), _to_int(y), _to_int(w), _to_int(h)]
        r, b = _first(value, ["right", "x2"]), _first(value, ["bottom", "y2"])
        if None not in (x, y, r, b):
            return [_to_int(x), _to_int(y), _to_int(r) - _to_int(x), _to_int(b) - _to_int(y)]
    return None


def migrate_v1(d: dict) -> AppConfig:
    """흑변 전용(단일 ROI) 구버전 설정을 ROI 목록 구조로 변환 (키 이름은 최대한 유연하게 인식)."""
    cfg = AppConfig()
    cfg.interval_sec = _to_float(_first(d, ["interval_sec", "interval", "check_interval"]), 1.0, 0.2, 60.0)
    rois_raw = _first(d, ["rois", "roi_list", "regions"])
    if not isinstance(rois_raw, list):
        single = _first(d, ["roi", "ROI", "region", "rect"])
        rois_raw = [single] if single is not None else []
    threshold = _first(d, ["threshold", "black_threshold", "brightness_threshold", "dark_threshold"])
    ratio = _first(d, ["ratio", "black_ratio", "dark_ratio"])
    duration = _first(d, ["duration_sec", "duration", "hold_sec", "consecutive_sec"])
    process = _first(d, ["expected_process", "process_name", "target_process"])
    for i, item in enumerate(rois_raw, 1):
        rect = _parse_rect(item)
        if rect is None or rect[2] <= 0 or rect[3] <= 0:
            continue
        params = {}
        if threshold is not None:
            params["threshold"] = threshold
        if ratio is not None:
            params["ratio"] = ratio
        roi = ROI(name=f"ROI {i}", x=rect[0], y=rect[1], w=rect[2], h=rect[3], detector="black",
                  params=detectors.normalize_params("black", params))
        if duration is not None:
            roi.duration_sec = _to_float(duration, 5.0, 0.0, 86400.0)
        if isinstance(process, str):
            roi.expected_process = process.strip()
        cfg.rois.append(roi)
    return cfg


def load(path: str = paths.SETTINGS_PATH) -> AppConfig:
    if not os.path.exists(path):
        return AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        log.error("설정 파일을 읽을 수 없어 기본값으로 시작합니다: %s", e)
        try:
            shutil.copyfile(path, path + ".broken")
        except OSError:
            pass
        return AppConfig()
    if not isinstance(data, dict):
        return AppConfig()
    if _to_int(data.get("version"), 1) >= CONFIG_VERSION:
        return config_from_dict(data)
    backup = os.path.join(os.path.dirname(path), "settings.v1.bak.json")
    try:
        shutil.copyfile(path, backup)
    except OSError:
        pass
    cfg = migrate_v1(data)
    log.info("구버전 설정을 변환했습니다 (ROI %d개). 원본 백업: %s", len(cfg.rois), backup)
    save(cfg, path)
    return cfg


def save(cfg: AppConfig, path: str = paths.SETTINGS_PATH) -> None:
    data = asdict(cfg)
    data["version"] = CONFIG_VERSION
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def clone(cfg: AppConfig) -> AppConfig:
    return copy.deepcopy(cfg)

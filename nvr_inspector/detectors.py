"""ROI 이미지(RGB uint8, HxWx3)를 받아 이상 여부를 판정하는 순수 함수 모음."""
from dataclasses import dataclass
from typing import Optional

import numpy as np

# 각 검출 유형: 표시 이름, 설명, 파라미터 목록 (키, 라벨, 타입, 기본값, 최소, 최대)
DETECTORS = {
    "black": {
        "label": "흑화면 (검은 화면)",
        "help": "어두운 픽셀이 일정 비율 이상이면 이상으로 판단합니다.",
        "params": [
            ("threshold", "밝기 기준 (0~255, 이 값 이하 = 어두움)", "float", 30.0, 0.0, 255.0),
            ("ratio", "어두운 픽셀 비율 (0~1, 이 값 이상이면 이상)", "float", 0.95, 0.0, 1.0),
        ],
    },
    "white": {
        "label": "백화면 (하얀/과노출 화면)",
        "help": "밝은 픽셀이 일정 비율 이상이면 이상으로 판단합니다.",
        "params": [
            ("threshold", "밝기 기준 (0~255, 이 값 이상 = 밝음)", "float", 225.0, 0.0, 255.0),
            ("ratio", "밝은 픽셀 비율 (0~1, 이 값 이상이면 이상)", "float", 0.95, 0.0, 1.0),
        ],
    },
    "uniform": {
        "label": "단색 화면 (No Signal / 파란 화면 등)",
        "help": "화면 전체가 거의 한 가지 색이면(밝기 표준편차가 작으면) 이상으로 판단합니다.",
        "params": [
            ("max_std", "밝기 표준편차 기준 (이 값 이하면 이상)", "float", 6.0, 0.0, 128.0),
        ],
    },
    "frozen": {
        "label": "화면 정지 (영상 멈춤)",
        "help": "직전 검사 대비 변화량이 기준 이하로 지속되면 이상으로 판단합니다.\n"
                "ROI에 시계/날짜 표시가 들어가면 항상 변하므로 제외하고 지정하세요.\n"
                "움직임이 없는 장면은 정상인데도 정지로 보일 수 있으니 지속 시간을 길게(60초 이상) 두세요.",
        "params": [
            ("max_diff", "프레임 변화량 기준 (이 값 이하면 정지)", "float", 1.0, 0.0, 255.0),
        ],
    },
    "color": {
        "label": "특정 색상 감지",
        "help": "지정한 색과 비슷한 픽셀이 일정 비율 이상이면 이상으로 판단합니다.\n"
                "예: 'No Video' 파란 화면, 빨간 경고 아이콘 등.",
        "params": [
            ("rgb", "대상 색상 R,G,B", "rgb", [0, 0, 255], 0, 255),
            ("tolerance", "색상 허용 오차 (0~255)", "float", 40.0, 0.0, 255.0),
            ("ratio", "해당 색 픽셀 비율 (0~1, 이 값 이상이면 이상)", "float", 0.5, 0.0, 1.0),
        ],
    },
    "reference": {
        "label": "기준 화면과 다름 (화면 구성 변경)",
        "help": "정상일 때 저장한 기준 이미지와 차이가 기준 이상이면 이상으로 판단합니다.\n"
                "[기준 이미지 저장]으로 정상 화면을 먼저 저장해야 합니다.\n"
                "레이아웃 변경, 카메라 방향 틀어짐 등 감지용입니다.",
        "params": [
            ("max_diff", "평균 차이 기준 (0~255, 이 값 이상이면 이상)", "float", 35.0, 0.0, 255.0),
        ],
    },
}

DETECTOR_ORDER = ["black", "white", "uniform", "frozen", "color", "reference"]

_MAX_SIDE = 160      # 판정용 샘플링 최대 변 길이 (속도)
_REF_GRID = 32       # 기준 이미지 비교용 블록 평균 해상도


def default_params(kind: str) -> dict:
    return {key: (list(default) if isinstance(default, list) else default)
            for key, _label, _typ, default, _lo, _hi in DETECTORS[kind]["params"]}


def normalize_params(kind: str, params: Optional[dict]) -> dict:
    """저장된 파라미터를 기본값과 병합하고 범위를 보정한다."""
    result = default_params(kind)
    params = params or {}
    for key, _label, typ, default, lo, hi in DETECTORS[kind]["params"]:
        if key not in params:
            continue
        value = params[key]
        try:
            if typ == "rgb":
                rgb = [int(round(float(v))) for v in value]
                if len(rgb) != 3:
                    raise ValueError
                result[key] = [min(max(v, lo), hi) for v in rgb]
            else:
                result[key] = min(max(float(value), lo), hi)
        except (TypeError, ValueError):
            result[key] = list(default) if isinstance(default, list) else default
    return result


@dataclass
class Result:
    abnormal: Optional[bool]   # None = 판정 불가(대기)
    value: float
    detail: str


def to_gray(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.float32, copy=False)
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def subsample(arr: np.ndarray, max_side: int = _MAX_SIDE) -> np.ndarray:
    longest = max(arr.shape[0], arr.shape[1])
    step = max(1, -(-longest // max_side))
    return arr[::step, ::step]


def block_mean(gray: np.ndarray, grid: int = _REF_GRID) -> np.ndarray:
    gh, gw = min(grid, gray.shape[0]), min(grid, gray.shape[1])
    hh, ww = gray.shape[0] // gh * gh, gray.shape[1] // gw * gw
    return gray[:hh, :ww].reshape(gh, hh // gh, gw, ww // gw).mean(axis=(1, 3))


def evaluate(kind: str, params: dict, rgb: np.ndarray, state: dict,
             reference: Optional[np.ndarray] = None) -> Result:
    """state: ROI별로 유지되는 dict (화면 정지 검출의 직전 프레임 보관용)."""
    if kind not in DETECTORS:
        return Result(None, 0.0, f"알 수 없는 검출 유형: {kind}")
    p = normalize_params(kind, params)
    if rgb.size == 0:
        return Result(None, 0.0, "캡처 영역이 비어 있음")
    small = subsample(rgb)

    if kind == "black":
        ratio = float((to_gray(small) <= p["threshold"]).mean())
        return Result(ratio >= p["ratio"], ratio * 100,
                      f"어두운 픽셀 {ratio * 100:.1f}% (기준 ≥{p['ratio'] * 100:.0f}%)")

    if kind == "white":
        ratio = float((to_gray(small) >= p["threshold"]).mean())
        return Result(ratio >= p["ratio"], ratio * 100,
                      f"밝은 픽셀 {ratio * 100:.1f}% (기준 ≥{p['ratio'] * 100:.0f}%)")

    if kind == "uniform":
        std = float(to_gray(small).std())
        return Result(std <= p["max_std"], std,
                      f"밝기 표준편차 {std:.1f} (기준 ≤{p['max_std']:.1f})")

    if kind == "frozen":
        gray = to_gray(small)
        prev = state.get("prev")
        state["prev"] = gray
        if prev is None or prev.shape != gray.shape:
            return Result(None, 0.0, "비교할 이전 프레임 수집 중")
        diff = float(np.abs(gray - prev).mean())
        return Result(diff <= p["max_diff"], diff,
                      f"프레임 변화량 {diff:.2f} (기준 ≤{p['max_diff']:.2f})")

    if kind == "color":
        target = np.array(p["rgb"], dtype=np.int16)
        dist = np.abs(small.astype(np.int16) - target).max(axis=2)
        ratio = float((dist <= p["tolerance"]).mean())
        r, g, b = p["rgb"]
        return Result(ratio >= p["ratio"], ratio * 100,
                      f"색상({r},{g},{b}) 픽셀 {ratio * 100:.1f}% (기준 ≥{p['ratio'] * 100:.0f}%)")

    # reference
    if reference is None:
        return Result(None, 0.0, "기준 이미지 없음 – [기준 이미지 저장] 필요")
    if reference.shape[:2] != rgb.shape[:2]:
        return Result(None, 0.0, "ROI 크기가 바뀜 – 기준 이미지를 다시 저장하세요")
    diff = float(np.abs(block_mean(to_gray(rgb)) - block_mean(to_gray(reference))).mean())
    return Result(diff >= p["max_diff"], diff,
                  f"기준 대비 차이 {diff:.1f} (기준 ≥{p['max_diff']:.1f})")


def mean_color(rgb: np.ndarray):
    m = subsample(rgb).reshape(-1, 3).mean(axis=0)
    return [int(round(v)) for v in m]

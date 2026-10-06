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

SHAPE_POLARITY = {
    "auto": "자동 판단",
    "bright": "대상(탭)이 배경보다 밝음",
    "dark": "대상(탭)이 배경보다 어두움",
}

DETECTORS["shape"] = {
    "label": "형상 검사 (탭 접힘·찍힘·휨)",
    "help": "정상 제품 화면을 [기준 이미지 저장]으로 저장해 두면, 대상(탭)의 윤곽을 기준과 겹쳐 비교합니다.\n"
            "접힘·휨·찢어짐·찍힘으로 모양이 달라진 면적이 기준 이상이면 불량으로 판단합니다.\n"
            "· 위치가 조금 어긋나도 자동으로 맞춰 비교합니다 (회전은 소폭만 허용).\n"
            "· 정상품 기준 이미지를 여러 장 추가하면, 가장 비슷한 기준과 비교해 오탐이 줄어듭니다.\n"
            "· 제품이 흘러가는 라인이면 '이상 지속 시간'을 0~1초로, 제품 감지 최소 면적을 설정하세요.",
    "params": [
        ("polarity", "대상(탭) 밝기", "choice", "auto", SHAPE_POLARITY, None),
        ("max_defect", "형상 차이 기준 (%, 이 값 이상이면 불량)", "float", 5.0, 0.1, 100.0),
        ("max_shift", "위치 허용 범위 (ROI 크기 대비 %)", "float", 10.0, 0.0, 40.0),
        ("edge_tol", "경계 허용 오차 (픽셀, 0~3)", "float", 1.0, 0.0, 3.0),
        ("max_texture", "표면 차이 기준 (구김·긁힘, 0 = 사용 안 함)", "float", 0.0, 0.0, 5.0),
        ("min_presence", "제품 감지 최소 면적 (기준 대비 %, 0 = 항상 판정)", "float", 0.0, 0.0, 100.0),
    ],
}

DETECTOR_ORDER = ["black", "white", "uniform", "frozen", "color", "reference", "shape"]
REFERENCE_KINDS = ("reference", "shape")   # 기준 이미지가 필요한 검출 유형

_MAX_SIDE = 160      # 판정용 샘플링 최대 변 길이 (속도)
_REF_GRID = 32       # 기준 이미지 비교용 블록 평균 해상도
_SHAPE_SIDE = 200    # 형상 검사 분석 해상도 (긴 변)
_MIN_CONTRAST = 15.0       # 기준 이미지의 대상/배경 최소 밝기 차
_PRESENCE_CONTRAST = 0.4   # 현재 대비가 기준 대비의 40% 미만이면 '대상 없음'으로 본다


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
            if typ == "choice":
                result[key] = value if value in lo else default
            elif typ == "rgb":
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
    mask: Optional[np.ndarray] = None   # 불량 위치 (프레임과 같은 크기, bool). 스냅샷 표시용


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
             reference=None) -> Result:
    """state: ROI별로 유지되는 dict (화면 정지 검출의 직전 프레임 보관용).
    reference: 기준 이미지 배열 1장 또는 여러 장의 리스트 (정상품 여러 장 → 가장 비슷한 것과 비교)."""
    if reference is None:
        refs = []
    elif isinstance(reference, np.ndarray):
        refs = [reference]
    else:
        refs = [r for r in reference if r is not None]
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

    if not refs:
        return Result(None, 0.0, "기준 이미지 없음 – [기준 이미지 저장] 필요")
    refs = [r for r in refs if r.shape[:2] == rgb.shape[:2]]
    if not refs:
        return Result(None, 0.0, "ROI 크기가 바뀜 – 기준 이미지를 다시 저장하세요")

    if kind == "shape":
        return _evaluate_shape(p, rgb, refs)

    # reference: 여러 장 중 가장 비슷한 기준과의 차이
    cur = block_mean(to_gray(rgb))
    diff = min(float(np.abs(cur - block_mean(to_gray(r))).mean()) for r in refs)
    suffix = f" · 기준 {len(refs)}장 중 최소" if len(refs) > 1 else ""
    return Result(diff >= p["max_diff"], diff,
                  f"기준 대비 차이 {diff:.1f} (기준 ≥{p['max_diff']:.1f}){suffix}")


# ===================== 형상 검사 =====================

def resize_area(gray: np.ndarray, max_side: int):
    """면적 평균으로 축소 (압축 노이즈 완화). 반환: (축소 이미지, 배율)."""
    f = max(1, -(-max(gray.shape) // max_side))
    if f == 1:
        return gray, 1
    h, w = gray.shape[0] // f * f, gray.shape[1] // f * f
    return gray[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3)), f


def otsu_threshold(gray: np.ndarray) -> float:
    hist = np.bincount(np.clip(gray, 0, 255).astype(np.uint8).ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 128.0
    omega = np.cumsum(hist) / total
    mu = np.cumsum(hist * np.arange(256)) / total
    with np.errstate(divide="ignore", invalid="ignore"):
        sigma = (mu[-1] * omega - mu) ** 2 / (omega * (1.0 - omega))
    sigma[~np.isfinite(sigma)] = 0.0
    return float(np.argmax(sigma))


def object_mask(gray: np.ndarray, polarity: str):
    """대상(탭) 실루엣과 대비(두 영역 평균 밝기 차).
    이미지마다 자체 임계값(Otsu)을 써서 조명 밝기 변화에 강하게 한다."""
    t = otsu_threshold(gray)
    above = gray > t
    if above.all() or not above.any():
        return np.zeros(gray.shape, dtype=bool), 0.0
    contrast = float(gray[above].mean() - gray[~above].mean())
    return (above if polarity == "bright" else ~above), contrast


def dilate(mask: np.ndarray, n: int) -> np.ndarray:
    for _ in range(int(n)):
        p = np.pad(mask, 1, constant_values=False)
        mask = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return mask


def opening(mask: np.ndarray, n: int) -> np.ndarray:
    """얇은 선(정렬 오차로 생긴 경계 차이)만 지우고, 실제 불량 덩어리는 원래 크기를 유지한다."""
    if n <= 0:
        return mask
    return dilate(erode(mask, n), n) & mask


def erode(mask: np.ndarray, n: int) -> np.ndarray:
    """십자형 침식. 정렬 오차로 생기는 1~2px 경계선 차이를 지운다."""
    for _ in range(int(n)):
        p = np.pad(mask, 1, constant_values=False)
        mask = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return mask


def _overlap(shape, dx: int, dy: int):
    """cur[y+dy, x+dx] ↔ ref[y, x] 가 겹치는 영역의 슬라이스."""
    h, w = shape
    cy0, cy1 = max(0, dy), min(h, h + dy)
    cx0, cx1 = max(0, dx), min(w, w + dx)
    return ((slice(cy0, cy1), slice(cx0, cx1)),
            (slice(cy0 - dy, cy1 - dy), slice(cx0 - dx, cx1 - dx)))


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.count_nonzero(a | b)
    return np.count_nonzero(a & b) / union if union else 0.0


def _search_shift(cur: np.ndarray, ref: np.ndarray, xs, ys):
    best = (-1.0, 0, 0)
    for dy in ys:
        for dx in xs:
            cs, rs = _overlap(cur.shape, dx, dy)
            score = _iou(cur[cs], ref[rs])
            # 같은 점수면 이동량이 작은 쪽을 택한다
            if score > best[0] + 1e-9 or (abs(score - best[0]) <= 1e-9
                                         and abs(dx) + abs(dy) < abs(best[1]) + abs(best[2])):
                best = (score, dx, dy)
    return best


def align_masks(cur: np.ndarray, ref: np.ndarray, max_shift: int):
    """평행 이동 정렬 (거친 탐색 → 정밀 탐색). 반환: (IoU, dx, dy)."""
    if max_shift <= 0:
        return _iou(cur, ref), 0, 0
    if max_shift < 4:
        rng = range(-max_shift, max_shift + 1)
        return _search_shift(cur, ref, rng, rng)
    half = max_shift // 2
    _s, cdx, cdy = _search_shift(cur[::2, ::2], ref[::2, ::2], range(-half, half + 1), range(-half, half + 1))
    xs = range(max(-max_shift, 2 * cdx - 2), min(max_shift, 2 * cdx + 2) + 1)
    ys = range(max(-max_shift, 2 * cdy - 2), min(max_shift, 2 * cdy + 2) + 1)
    return _search_shift(cur, ref, xs, ys)


def _zscore(values: np.ndarray) -> np.ndarray:
    std = values.std()
    return (values - values.mean()) / std if std > 1e-6 else values * 0.0


def compare_shape(cur_gray: np.ndarray, ref_gray: np.ndarray, p: dict):
    """기준 대비 형상 비교. 반환 dict 또는 오류 메시지(str)."""
    cur, f = resize_area(cur_gray, _SHAPE_SIDE)
    ref, _ = resize_area(ref_gray, _SHAPE_SIDE)
    polarity = p["polarity"]
    if polarity == "auto":   # 기준 이미지에서 면적이 작은 쪽을 대상(탭)으로 본다
        polarity = "bright" if (ref > otsu_threshold(ref)).mean() <= 0.5 else "dark"
    ref_m, ref_contrast = object_mask(ref, polarity)
    ref_area = int(np.count_nonzero(ref_m))
    if (ref_contrast < _MIN_CONTRAST or ref_area < 0.002 * ref_m.size
            or ref_area > 0.998 * ref_m.size):
        return "기준 이미지에서 대상 형상을 구분할 수 없음 – ROI를 탭 주변으로 좁히거나 '대상(탭) 밝기'를 지정하세요"
    cur_m, cur_contrast = object_mask(cur, polarity)
    if cur_contrast < ref_contrast * _PRESENCE_CONTRAST:
        cur_m = np.zeros(cur.shape, dtype=bool)   # 배경 노이즈만 있음 → 대상 없음

    max_shift = int(round(p["max_shift"] / 100.0 * max(cur.shape)))
    iou, dx, dy = align_masks(cur_m, ref_m, max_shift)
    cs, rs = _overlap(cur.shape, dx, dy)
    diff = opening(cur_m[cs] ^ ref_m[rs], int(p["edge_tol"]))
    defect_pct = np.count_nonzero(diff) / ref_area * 100.0
    presence_pct = np.count_nonzero(cur_m) / ref_area * 100.0

    texture = 0.0
    if p["max_texture"] > 0:
        inside = erode(cur_m[cs] & ref_m[rs], 2)
        if np.count_nonzero(inside) >= 20:
            texture = float(np.abs(_zscore(cur[cs][inside]) - _zscore(ref[rs][inside])).mean())

    defect_map = np.zeros(cur.shape, dtype=bool)
    defect_map[cs] = diff
    return {"defect": defect_pct, "texture": texture, "presence": presence_pct, "iou": iou,
            "dx": dx * f, "dy": dy * f, "map": defect_map, "factor": f}


def _upscale_mask(small: np.ndarray, factor: int, shape) -> np.ndarray:
    big = np.repeat(np.repeat(small, factor, axis=0), factor, axis=1) if factor > 1 else small
    out = np.zeros(shape[:2], dtype=bool)
    h, w = min(shape[0], big.shape[0]), min(shape[1], big.shape[1])
    out[:h, :w] = big[:h, :w]
    return out


def _evaluate_shape(p: dict, rgb: np.ndarray, refs) -> Result:
    cur_gray = to_gray(rgb)
    best = None
    errors = []
    for ref in refs:
        r = compare_shape(cur_gray, to_gray(ref), p)
        if isinstance(r, str):
            errors.append(r)
            continue
        ratio = r["defect"] / p["max_defect"]
        if p["max_texture"] > 0:
            ratio = max(ratio, r["texture"] / p["max_texture"])
        r["ratio"] = ratio
        if best is None or ratio < best["ratio"]:
            best = r
    if best is None:
        return Result(None, 0.0, errors[0])

    if p["min_presence"] > 0 and best["presence"] < p["min_presence"]:
        return Result(None, best["presence"],
                      f"제품 없음 (대상 면적 {best['presence']:.0f}% < {p['min_presence']:.0f}%) – 판정 보류")

    parts = [f"형상 차이 {best['defect']:.1f}% (기준 ≥{p['max_defect']:g}%)"]
    if p["max_texture"] > 0:
        parts.append(f"표면 차이 {best['texture']:.2f} (기준 ≥{p['max_texture']:g})")
    if best["dx"] or best["dy"]:
        parts.append(f"위치 보정 {best['dx']:+d},{best['dy']:+d}px")
    if len(refs) > 1:
        parts.append(f"기준 {len(refs)}장 중 최근접")
    abnormal = best["ratio"] >= 1.0
    mask = _upscale_mask(best["map"], best["factor"], rgb.shape) if abnormal else None
    return Result(abnormal, best["defect"], " · ".join(parts), mask)


def overlay_defects(rgb: np.ndarray, mask: Optional[np.ndarray]) -> np.ndarray:
    """불량 위치를 빨간색으로 덧칠한 이미지 (스냅샷/미리보기용)."""
    if mask is None or not mask.any():
        return rgb
    out = rgb.astype(np.float32)
    out[mask] = out[mask] * 0.35 + np.array([255.0, 0.0, 0.0]) * 0.65
    return out.astype(np.uint8)


def mean_color(rgb: np.ndarray):
    m = subsample(rgb).reshape(-1, 3).mean(axis=0)
    return [int(round(v)) for v in m]

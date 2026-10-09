"""ROI 모양 (사각형·타원, 회전) 계산.

ROI는 (x, y, w, h) 상자와 모양(shape: rect | ellipse), 각도(angle, 도, 화면에서 시계 방향)로 정의한다.
상자를 중심 기준으로 angle만큼 돌린 것이 실제 감시 영역이다 (원 = 가로세로가 같은 타원).

- capture_rect(roi): 화면 캡처 범위 (돌린 모양을 감싸는 축 정렬 사각형)
- extract(roi, image, origin): 캡처한 화면에서 모양 부분을 바로 세워 w×h 이미지로 꺼낸다.
  판정·샘플·스냅샷은 모두 이 바로 세운 이미지를 쓰므로 각도가 바뀌어도 샘플을 그대로 쓸 수 있다.
  타원 바깥(모서리)은 같은 줄의 가장 가까운 타원 안쪽 픽셀로 채워 판정 수치(어두운 비율 등)를 흐리지 않는다.
- 사각형·0°는 지금까지와 완전히 같다 (변환 없음)."""
import math
from functools import lru_cache
from typing import List, Tuple

import numpy as np

SHAPES = ("rect", "ellipse")
_ELLIPSE_POINTS = 72


def _norm_angle(angle: float) -> float:
    a = float(angle) % 360.0
    return 0.0 if a < 1e-9 or 360.0 - a < 1e-9 else a


def is_plain(roi) -> bool:
    """변환이 필요 없는 ROI (사각형 + 0°)."""
    return getattr(roi, "shape", "rect") != "ellipse" and _norm_angle(getattr(roi, "angle", 0.0)) == 0.0


def center(roi) -> Tuple[float, float]:
    return roi.x + roi.w / 2.0, roi.y + roi.h / 2.0


def shape_polygon(roi, pad: float = 0.0) -> List[Tuple[float, float]]:
    """화면 좌표 외곽선 점 목록 (pad: 바깥으로 넓힐 픽셀 – 화면 표시 테두리용)."""
    cx, cy = center(roi)
    hw, hh = roi.w / 2.0 + pad, roi.h / 2.0 + pad
    rad = math.radians(_norm_angle(getattr(roi, "angle", 0.0)))
    c, s = math.cos(rad), math.sin(rad)
    if getattr(roi, "shape", "rect") == "ellipse":
        local = [(hw * math.cos(t), hh * math.sin(t))
                 for t in (2 * math.pi * i / _ELLIPSE_POINTS for i in range(_ELLIPSE_POINTS))]
    else:
        local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return [(cx + c * u - s * v, cy + s * u + c * v) for u, v in local]


def capture_rect(roi) -> Tuple[int, int, int, int]:
    """돌린 모양을 감싸는 정수 사각형 (x, y, w, h)."""
    if is_plain(roi) or (_norm_angle(roi.angle) == 0.0):
        return roi.x, roi.y, roi.w, roi.h
    cx, cy = center(roi)
    rad = math.radians(_norm_angle(roi.angle))
    c, s = abs(math.cos(rad)), abs(math.sin(rad))
    if getattr(roi, "shape", "rect") == "ellipse":
        a, b = roi.w / 2.0, roi.h / 2.0
        hx = math.sqrt((a * c) ** 2 + (b * s) ** 2)
        hy = math.sqrt((a * s) ** 2 + (b * c) ** 2)
    else:
        hx = roi.w / 2.0 * c + roi.h / 2.0 * s
        hy = roi.w / 2.0 * s + roi.h / 2.0 * c
    x0, y0 = math.floor(cx - hx), math.floor(cy - hy)
    x1, y1 = math.ceil(cx + hx), math.ceil(cy + hy)
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def contains(roi, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """화면 좌표 점들이 감시 영역 안인지 (가림 판정용)."""
    cx, cy = center(roi)
    rad = math.radians(_norm_angle(getattr(roi, "angle", 0.0)))
    c, s = math.cos(rad), math.sin(rad)
    dx, dy = xs - cx, ys - cy
    u, v = c * dx + s * dy, -s * dx + c * dy           # 모양 기준 좌표 (회전 되돌림)
    hw, hh = roi.w / 2.0, roi.h / 2.0
    if getattr(roi, "shape", "rect") == "ellipse":
        return (u / hw) ** 2 + (v / hh) ** 2 <= 1.0
    return (np.abs(u) <= hw) & (np.abs(v) <= hh)


@lru_cache(maxsize=64)
def _ellipse_fill_index(w: int, h: int):
    """타원 바깥 픽셀을 같은 줄의 가장 가까운 안쪽 픽셀로 채우는 색인 (rows, cols)과 안쪽 마스크."""
    ys = (np.arange(h) + 0.5 - h / 2.0) / (h / 2.0)
    xs = (np.arange(w) + 0.5 - w / 2.0) / (w / 2.0)
    inside = xs[None, :] ** 2 + ys[:, None] ** 2 <= 1.0
    if not inside.any():
        inside[h // 2, w // 2] = True
    valid = np.nonzero(inside.any(axis=1))[0]
    rows = np.arange(h)
    # 안쪽 픽셀이 없는 맨 위/아래 줄은 가장 가까운 줄을 쓴다
    src_rows = valid[np.abs(valid[None, :] - rows[:, None]).argmin(axis=1)]
    first = inside.argmax(axis=1)
    last = w - 1 - inside[:, ::-1].argmax(axis=1)
    lo, hi = first[src_rows], last[src_rows]
    cols = np.clip(np.arange(w)[None, :], lo[:, None], hi[:, None])
    row_idx = np.repeat(src_rows[:, None], w, axis=1)
    return row_idx, cols, inside


def ellipse_mask(w: int, h: int) -> np.ndarray:
    """바로 세운 w×h 이미지에서 타원 안쪽 (True)."""
    return _ellipse_fill_index(w, h)[2].copy()


def extract(roi, image: np.ndarray, origin: Tuple[int, int]) -> np.ndarray:
    """image(RGB, 좌상단 화면 좌표 origin)에서 ROI 모양을 바로 세운 (h, w, 3) 이미지."""
    if _norm_angle(getattr(roi, "angle", 0.0)):
        out = _warp(roi, image, origin)
    else:
        out = _crop(roi, image, origin)
    if getattr(roi, "shape", "rect") == "ellipse":
        rows, cols, _inside = _ellipse_fill_index(roi.w, roi.h)
        out = out[rows, cols]
    return np.ascontiguousarray(out)


def _crop(roi, image, origin):
    """회전 없는 경우: 그대로 잘라냄 (범위를 벗어난 부분은 가장자리 픽셀로 채워 정확히 w×h)."""
    ox, oy = origin
    out = image[roi.y - oy:roi.y - oy + roi.h, roi.x - ox:roi.x - ox + roi.w]
    if out.shape[:2] == (roi.h, roi.w) and roi.y >= oy and roi.x >= ox:
        return out
    ys = np.clip(np.arange(roi.h) + roi.y - oy, 0, image.shape[0] - 1)
    xs = np.clip(np.arange(roi.w) + roi.x - ox, 0, image.shape[1] - 1)
    return image[ys[:, None], xs[None, :]]


def _warp(roi, image, origin):
    """회전 영역을 바로 세운다 (양선형 보간, numpy만 사용)."""
    ox, oy = origin
    cx, cy = center(roi)
    rad = math.radians(_norm_angle(roi.angle))
    c, s = math.cos(rad), math.sin(rad)
    u = np.arange(roi.w) + 0.5 - roi.w / 2.0
    v = np.arange(roi.h) + 0.5 - roi.h / 2.0
    uu, vv = np.meshgrid(u, v)
    # 화면 좌표 (픽셀 중심 기준) → 이미지 색인
    sx = cx + c * uu - s * vv - ox - 0.5
    sy = cy + s * uu + c * vv - oy - 0.5
    h, w = image.shape[:2]
    sx = np.clip(sx, 0, w - 1)
    sy = np.clip(sy, 0, h - 1)
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (sx - x0)[..., None]
    fy = (sy - y0)[..., None]
    img = image.astype(np.float32)
    top = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    bot = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    return np.clip(top * (1 - fy) + bot * fy + 0.5, 0, 255).astype(np.uint8)


def grab(grabber, roi) -> np.ndarray:
    """화면에서 ROI 모양을 캡처해 바로 세운 이미지로."""
    x, y, w, h = capture_rect(roi)
    if is_plain(roi):
        return grabber.grab(x, y, w, h)
    return extract(roi, grabber.grab(x, y, w, h), (x, y))


def describe(roi) -> str:
    """목록 표시용 위치 문자열."""
    text = f"{roi.x},{roi.y}  {roi.w}×{roi.h}"
    if getattr(roi, "shape", "rect") == "ellipse":
        text += " ◯"
    angle = _norm_angle(getattr(roi, "angle", 0.0))
    if angle:
        text += f" {angle:g}°"
    return text

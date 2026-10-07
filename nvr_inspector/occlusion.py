"""ROI가 대상 프로그램(NVR/FMVS 뷰어) 화면으로 보이는지 판단.

ROI 중심 한 점만 보면 옆에 붙은 창의 보이지 않는 테두리, 화면에 없는 창(다른 가상 데스크톱 등) 때문에
가리지 않았는데도 '건너뜀'이 나오고, 반대로 ROI 가장자리를 덮은 창은 놓친다.
그래서 위에 있는 창부터 차례로 ROI 영역을 채워 가며, 대상 프로그램보다 위에 있는 다른 창이
ROI를 실제로 덮은 면적이 있을 때만 '가림'으로 판정한다. 대시보드가 떠 있어도 ROI와 겹치지 않으면 판정한다."""
import math
from typing import Iterable, NamedTuple, Tuple

import numpy as np

_EDGE_TOL = 2         # 창 가장자리 1~2px 반올림 오차는 가림으로 보지 않음
_MAX_GRID = 400       # 큰 ROI는 격자를 줄여 계산 (정확도 1~2px)
OWN_LABEL = "FMVS 창(대시보드·팝업)"


class Visibility(NamedTuple):
    ok: bool                  # True면 판정 진행
    detail: str
    covered_pct: float = 0.0  # 다른 창이 덮은 ROI 면적(%)


def _label(win) -> str:
    return OWN_LABEL if getattr(win, "own", False) else win.process


def roi_visibility(roi_rect: Tuple[int, int, int, int], windows: Iterable, expected: str) -> Visibility:
    """roi_rect=(x, y, w, h), windows=위에 있는 창부터 (process, rect=(l, t, r, b), own) 목록."""
    x, y, w, h = roi_rect
    if w <= 0 or h <= 0:
        return Visibility(True, "")
    expected = expected.lower()
    step = max(1, math.ceil(max(w, h) / _MAX_GRID))
    gh, gw = math.ceil(h / step), math.ceil(w / step)
    assigned = np.zeros((gh, gw), dtype=bool)
    target = np.zeros((gh, gw), dtype=bool)
    covers: dict = {}
    top_name = None

    for win in windows:
        left, top, right, bottom = win.rect
        is_target = win.process.lower() == expected
        if not is_target:                      # 다른 창은 가장자리 오차만큼 줄여서 본다
            left, top, right, bottom = left + _EDGE_TOL, top + _EDGE_TOL, right - _EDGE_TOL, bottom - _EDGE_TOL
        c0 = max(0, math.ceil((left - x) / step))
        c1 = min(gw, math.ceil((right - x) / step))
        r0 = max(0, math.ceil((top - y) / step))
        r1 = min(gh, math.ceil((bottom - y) / step))
        if c0 >= c1 or r0 >= r1:
            continue
        if top_name is None:
            top_name = _label(win)
        fresh = ~assigned[r0:r1, c0:c1]
        n = int(fresh.sum())
        if not n:
            continue
        if is_target:
            target[r0:r1, c0:c1] |= fresh
        else:
            covers[_label(win)] = covers.get(_label(win), 0) + n
        assigned[r0:r1, c0:c1] = True
        if assigned.all():
            break

    total = gh * gw
    seen = int(target.sum())
    if seen == 0:
        where = f" · ROI 위치: {top_name}" if top_name else ""
        return Visibility(False, f"대상 프로그램({expected}) 화면이 ROI 위치에 없음{where}", 100.0)
    if seen == total:
        return Visibility(True, "")
    covered_pct = (total - seen) * 100.0 / total
    names = sorted(covers, key=covers.get, reverse=True)
    if not names:
        return Visibility(False, f"ROI 일부가 대상 프로그램 창 밖 ({covered_pct:.0f}%)", covered_pct)
    who = ", ".join(names[:2]) + (" 외" if len(names) > 2 else "")
    hint = " – 창을 ROI 밖으로 옮기세요" if OWN_LABEL in names[:2] else ""
    return Visibility(False, f"다른 창이 ROI를 가림: {who} {covered_pct:.0f}%{hint}", covered_pct)

"""의견 에이전트 (Advisor): 검출 기록·샘플·설정을 분석해 운영 개선 의견을 우선순위와 함께 낸다.

규칙 기반이라 LLM 없이 PC 안에서만 동작한다. LLM(로컬/사내 서버)을 연결하면 같은 분석 자료를 바탕으로
자연어 종합 의견과 질문 답변을 추가로 받을 수 있다 (llm.py).

입력은 화면과 분리된 순수 데이터라 단위 테스트가 가능하다:
    analyze(rois, stats, samples, self_checks, roi_hourly, ctx) -> [Advice, ...]  (심각한 것부터)"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from i18n import tr

LEVEL_ORDER = {"critical": 0, "warn": 1, "info": 2}
REFERENCE_KINDS = ("reference", "shape", "match")

MIN_EVENTS = 30           # 비율 의견을 내기 위한 최소 상태 보고 수
SKIP_RATIO = 0.30         # 가려짐 비율이 이 이상이면 의견
MOVING_RATIO = 0.90       # '움직임'만 계속되면 정지 기준이 너무 엄격한 것으로 추정
NG_RATE = 0.20            # 판정 대비 NG 비율
MIN_JUDGED = 20
BURST_FACTOR = 3.0        # 최근 1시간 NG가 이전 평균의 n배 이상이면 급증
MIN_OK_SAMPLES = 3


@dataclass
class Advice:
    key: str                       # 같은 의견 구분 (숨기기·새 의견 판단)
    level: str                     # critical | warn | info
    title: str
    body: str
    roi_id: Optional[str] = None
    action: Optional[str] = None   # samples | edit | settings | None


@dataclass
class Context:
    running: bool = False
    teams_enabled: bool = False
    uptime_sec: float = 0.0


def analyze(rois, stats: Dict[str, object], samples: Dict[str, Dict[str, int]],
            self_checks: Dict[str, str], roi_hourly: Dict[str, Dict[str, int]],
            ctx: Context) -> List[Advice]:
    """rois: ROI 목록, stats: roi_id→RoiStats, samples: roi_id→{'ok': n, 'ng': n, 'skip': n},
    self_checks: roi_id→자체 검증 요약 문장, roi_hourly: roi_id→{'YYYY-MM-DD HH': NG 수} (시간순)."""
    out: List[Advice] = []
    if not rois:
        out.append(Advice("no_roi", "info", tr("감시할 ROI가 없습니다"),
                          tr("[＋ ROI 추가]로 FMVS 화면에서 감시할 카메라 영역을 지정하세요.")))
        return out

    any_ng = False
    for roi in rois:
        if not roi.enabled:
            continue
        name = roi.name
        st = stats.get(roi.id)
        cnt = samples.get(roi.id, {"ok": 0, "ng": 0, "skip": 0})
        if roi.detector in REFERENCE_KINDS:
            if cnt.get("ok", 0) == 0:
                out.append(Advice(f"no_ok:{roi.id}", "critical",
                                  tr("[{name}] OK 샘플이 없어 판정하지 못합니다", name=name),
                                  tr("정상 제품 화면을 [샘플/기준 이미지]에서 OK로 1장 이상 등록하세요. "
                                     "위치·밝기 편차가 있으면 3장 이상이 좋습니다."),
                                  roi.id, "samples"))
            elif roi.detector == "match" and cnt["ok"] < MIN_OK_SAMPLES:
                out.append(Advice(f"few_ok:{roi.id}", "warn",
                                  tr("[{name}] OK 샘플 {n}장 – 오탐 위험", name=name, n=cnt["ok"]),
                                  tr("정상품도 위치·밝기가 조금씩 달라 OK가 적으면 정상을 NG로 판정하기 쉽습니다. "
                                     "서로 다른 순간의 OK 화면을 {n}장 이상 등록하세요.", n=MIN_OK_SAMPLES),
                                  roi.id, "samples"))
            check = self_checks.get(roi.id, "")
            if check.startswith("⚠"):
                out.append(Advice(f"selfcheck:{roi.id}", "warn",
                                  tr("[{name}] 샘플 자체 검증에서 틀린 판정이 있습니다", name=name),
                                  check + " " + tr("– 잘못 분류된 샘플이 없는지 확인하고(끌어서 다른 칸으로 이동), "
                                                   "헷갈리는 유형의 샘플을 더 등록하세요."),
                                  roi.id, "samples"))
            if roi.still_only and cnt.get("skip", 0) == 0 and cnt.get("ok", 0) > 0:
                out.append(Advice(f"no_skip:{roi.id}", "info",
                                  tr("[{name}] '무시' 샘플이 없습니다", name=name),
                                  tr("셀이 없을 때·이동 중 화면을 '무시'로 1장 등록하면 빈 화면을 NG로 오인하지 않습니다."),
                                  roi.id, "samples"))
        if not roi.expected_process:
            out.append(Advice(f"no_proc:{roi.id}", "info",
                              tr("[{name}] 대상 프로그램 미지정 – 가림 확인 꺼짐", name=name),
                              tr("다른 창이 ROI를 덮어도 그대로 판정해 오탐이 날 수 있습니다. "
                                 "ROI 편집에서 대상 프로그램(FMVS 뷰어 실행 파일)을 지정하세요."),
                              roi.id, "edit"))
        if st is None:
            continue
        counts = getattr(st, "state_counts", {}) or {}
        total = sum(counts.values())
        if st.ng:
            any_ng = True
        if total >= MIN_EVENTS:
            skip = counts.get("skip", 0) / total
            if skip >= SKIP_RATIO:
                out.append(Advice(f"skip:{roi.id}", "warn",
                                  tr("[{name}] {pct}% 시간 동안 가려져 판정하지 못했습니다", name=name,
                                     pct=f"{skip * 100:.0f}"),
                                  tr("최근 원인: {detail}. 대시보드·팝업 창을 ROI 밖으로 옮기거나 FMVS 화면을 맨 앞에 두세요.",
                                     detail=st.last_detail if st.last_state == "skip" else tr("가림")),
                                  roi.id, None))
            moving = counts.get("moving", 0) / total
            if roi.still_only and moving >= MOVING_RATIO and st.inspections == 0:
                out.append(Advice(f"moving:{roi.id}", "warn",
                                  tr("[{name}] 정지를 한 번도 감지하지 못했습니다", name=name),
                                  tr("화면 변화량이 계속 정지 기준({diff})보다 큽니다. 화면 잡음이 큰 카메라라면 "
                                     "ROI 편집에서 정지 기준 값을 올리세요 (현재 상태: {detail}).",
                                     diff=f"{roi.still_diff:g}", detail=st.last_detail),
                                  roi.id, "edit"))
            if counts.get("error", 0) >= 3:
                out.append(Advice(f"error:{roi.id}", "warn",
                                  tr("[{name}] 검사 오류가 반복됩니다 ({n}회)", name=name, n=counts["error"]),
                                  tr("최근 내용: {detail}. ROI 위치가 화면 밖이거나 샘플 파일이 손상되었을 수 있습니다.",
                                     detail=st.last_detail),
                                  roi.id, "edit"))
        judged = st.ok + st.ng
        if judged >= MIN_JUDGED and st.ng / judged >= NG_RATE:
            out.append(Advice(f"ngrate:{roi.id}", "warn",
                              tr("[{name}] NG 비율 {pct}% ({ng}/{n})", name=name,
                                 pct=f"{st.ng / judged * 100:.0f}", ng=st.ng, n=judged),
                              tr("실제 불량이면 해당 공정 점검이 필요합니다. 오탐이면 팝업의 [OK로 등록(오탐)]으로 "
                                 "알려 주세요 – 다음 판정부터 반영됩니다."),
                              roi.id, "samples"))
        burst = _burst(roi_hourly.get(roi.id, {}))
        if burst:
            last, avg = burst
            out.append(Advice(f"burst:{roi.id}", "critical",
                              tr("[{name}] 최근 1시간 NG 급증: {last}건 (이전 평균 {avg}건)", name=name,
                                 last=last, avg=f"{avg:.1f}"),
                              tr("같은 시간대에 설비 조건(장력·위치·조명) 변화가 있었는지 확인하세요. "
                                 "스냅샷 폴더의 확대 이미지로 불량 유형을 비교할 수 있습니다."),
                              roi.id, None))
        if st.ng and not roi.assignee:
            out.append(Advice(f"assignee:{roi.id}", "info",
                              tr("[{name}] 담당자 미지정", name=name),
                              tr("NG가 발생한 ROI입니다. 담당자와 Teams 이메일을 지정하면 알림이 바로 전달됩니다."),
                              roi.id, "edit"))

    if any_ng and not ctx.teams_enabled:
        out.append(Advice("teams_off", "info", tr("Teams 알림이 꺼져 있습니다"),
                          tr("NG가 발생하고 있지만 담당자에게 알림이 가지 않습니다. 설정에서 Teams 알림을 켜세요."),
                          None, "settings"))
    if not ctx.running:
        out.append(Advice("stopped", "info", tr("에이전트가 정지 상태입니다"),
                          tr("[▶ 에이전트 시작]을 누르면 실시간 판정과 분석을 시작합니다.")))
    out.sort(key=lambda a: LEVEL_ORDER.get(a.level, 9))
    return out


def _burst(hourly: Dict[str, int]) -> Optional[Tuple[int, float]]:
    """시간대별 NG (시간순 dict)에서 마지막 1시간이 이전 평균보다 급증했는지."""
    values = list(hourly.values())
    if len(values) < 2:
        return None
    last, before = values[-1], values[:-1][-6:]
    avg = sum(before) / len(before)
    if last >= 3 and last >= BURST_FACTOR * max(avg, 1.0):
        return last, avg
    return None


def summary_text(rois, stats, samples, advice: List[Advice], ctx: Context) -> str:
    """LLM에 넘길 분석 자료 (텍스트만 – 이미지·화면은 보내지 않음)."""
    lines = [f"running={ctx.running} uptime_min={int(ctx.uptime_sec // 60)} teams={ctx.teams_enabled}"]
    for roi in rois:
        st = stats.get(roi.id)
        cnt = samples.get(roi.id, {})
        counts = dict(getattr(st, "state_counts", {}) or {}) if st else {}
        lines.append(
            f"- ROI '{roi.name}' enabled={roi.enabled} detector={roi.detector} still_only={roi.still_only} "
            f"samples(ok/ng/ignore)={cnt.get('ok', 0)}/{cnt.get('ng', 0)}/{cnt.get('skip', 0)} "
            + (f"inspections={st.inspections} ok={st.ok} ng={st.ng} states={counts} last='{st.last_detail[:120]}'"
               if st else "no data yet"))
    lines.append("current findings:")
    lines += [f"  [{a.level}] {a.title} – {a.body}" for a in advice] or ["  (none)"]
    return "\n".join(lines)


def ng_context(info: dict, roi, st, hourly: Dict[str, int], samples: Dict[str, int], others: List[str]) -> str:
    """NG 1건 분석 자료 (텍스트). others: 최근 1분 안에 함께 NG가 난 다른 ROI 이름."""
    lines = [f"ROI: {info.get('roi_name')} / detector: {info.get('detector')}",
             f"result: {info.get('detail')}",
             f"time: NVR {info.get('nvr_time') or '-'} (source {info.get('nvr_source') or 'PC'}), PC {info.get('time')}",
             f"consecutive NG: {info.get('consecutive', 1)}"]
    if roi is not None:
        lines.append(f"roi: shape={getattr(roi, 'shape', 'rect')} angle={getattr(roi, 'angle', 0)} "
                     f"size={roi.w}x{roi.h} still_only={roi.still_only}")
    lines.append(f"samples ok/ng/ignore: {samples.get('ok', 0)}/{samples.get('ng', 0)}/{samples.get('skip', 0)}")
    if st is not None:
        lines.append(f"since start: judged={st.ok + st.ng} ok={st.ok} ng={st.ng}")
    if hourly:
        lines.append("NG per hour (last 12h, oldest first): " + ", ".join(f"{h}h={c}" for h, c in hourly.items()))
    lines.append("other ROIs NG within 1 min: " + (", ".join(others) if others else "none"))
    return "\n".join(lines)

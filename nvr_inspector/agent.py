"""NVR 비전 에이전트 – 관찰 → 판단 → 실행 → 학습 루프 (PC 내부에서만 동작, 외부 전송 없음).

검출 엔진(worker)이 보내는 상태/경보 이벤트를 관찰하고, 스스로 원인을 추론해 행동을 결정한다.
  · 동시다발 경보 → 개별 불량이 아니라 NVR 화면 전체 문제(레이아웃 변경·영상 끊김)로 판단
  · 같은 ROI 연속 불량 → 설비 점검 에스컬레이션
  · NVR 창 가려짐/최소화 지속 → 원인 안내
  · 검출 엔진 비정상 종료 → 자동 재시작 (시간당 횟수 제한)
  · 운영자 피드백(OK/NG 등록) → 자동 기준 재보정 결과 기록
  · 교대 시각 → 근무 리포트 자동 작성

순수 로직이며 화면(Tk)과 무관하다. 실행이 필요한 행동은 Action 목록으로 돌려주고 GUI가 수행한다."""
import html
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Deque, Dict, List, Optional, Tuple

# 활동 피드 종류: (아이콘, 이름)
FEED_KINDS = {
    "boot": ("◆", "시작"),
    "observe": ("👁", "관찰"),
    "think": ("🧠", "판단"),
    "act": ("⚡", "실행"),
    "learn": ("📚", "학습"),
    "warn": ("⚠", "주의"),
}

MASS_WINDOW = 15.0          # 이 시간(초) 안에
MASS_MIN_ROIS = 3           # 이 개수 이상, 그리고
MASS_RATIO = 0.5            # 사용 중 ROI의 이 비율 이상이 동시에 경보면 '화면 전체 문제'
TREND_WINDOW = 600.0        # 같은 ROI에서 10분 안에
TREND_COUNT = 3             # 3회 이상 불량이면 에스컬레이션
SKIP_PERSIST = 60.0         # 다른 화면(가려짐) 상태가 60초 이상 지속되면 안내
RESTART_LIMIT = 3           # 검출 엔진 자동 재시작: 시간당 최대 횟수
COOLDOWN = {"mass": 600.0, "trend": 1800.0, "skip": 600.0, "error": 300.0}


@dataclass
class FeedItem:
    when: float
    kind: str
    text: str


@dataclass
class Action:
    """GUI가 수행할 행동. kind: teams | restart"""
    kind: str
    title: str = ""
    message: str = ""


@dataclass
class RoiStats:
    inspections: int = 0
    ok: int = 0
    ng: int = 0
    last_ng: Optional[float] = None
    last_state: str = "idle"
    last_detail: str = ""
    ng_times: Deque[float] = field(default_factory=lambda: deque(maxlen=200))


class VisionAgent:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.feed: Deque[FeedItem] = deque(maxlen=400)
        self.stats: Dict[str, RoiStats] = defaultdict(RoiStats)
        self.names: Dict[str, str] = {}
        self.enabled_count = 0
        self.started_at: Optional[float] = None
        self.hourly_ng: Counter = Counter()        # 'YYYY-MM-DD HH' → NG 수
        self.timeline: Deque[Tuple[float, str, str, str]] = deque(maxlen=500)  # (시각, ROI, 구분, 상세)
        self._recent_alerts: Deque[Tuple[float, str]] = deque()
        self._skip_since: Dict[str, float] = {}
        self._cooldown: Dict[str, float] = {}
        self._restarts: Deque[float] = deque()
        self._last_shift_key: Optional[str] = None
        self.listeners: List[Callable[[FeedItem], None]] = []

    # ---------------- 공통 ----------------
    def say(self, kind: str, text: str) -> FeedItem:
        item = FeedItem(self.clock(), kind, text)
        self.feed.append(item)
        for fn in self.listeners:
            fn(item)
        return item

    def _ready(self, key: str, kind: str) -> bool:
        now = self.clock()
        if now - self._cooldown.get(key, -1e12) < COOLDOWN[kind]:
            return False
        self._cooldown[key] = now
        return True

    def _name(self, roi_id: str) -> str:
        return self.names.get(roi_id, roi_id)

    # ---------------- 수명 ----------------
    def configure(self, rois) -> None:
        self.names = {r.id: r.name for r in rois}
        self.enabled_count = sum(1 for r in rois if r.enabled)

    def boot(self, rois, sample_counts: Dict[str, int]) -> None:
        """검출 시작 시 부팅 로그."""
        self.configure(rois)
        self.started_at = self.clock()
        self._recent_alerts.clear()
        self._skip_since.clear()
        kinds = Counter(r.detector_label().split(" (")[0] for r in rois if r.enabled)
        self.say("boot", f"비전 에이전트 기동 – 감시 대상 ROI {self.enabled_count}개")
        if kinds:
            self.say("boot", "판정 엔진 로드: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
        total = sum(sample_counts.values())
        if total:
            self.say("boot", f"샘플/기준 이미지 {total}장 인덱싱 완료 · 자동 기준 보정 준비")
        still = sum(1 for r in rois if r.enabled and r.still_only)
        if still:
            self.say("boot", f"움직임 추적 모드 ROI {still}개 – 정지 순간에만 판정")
        self.say("observe", "실시간 관찰 시작")

    def shutdown(self, reason: str) -> None:
        self.say("act" if "사용자" in reason else "warn", f"검출 엔진 정지 ({reason})")
        self.started_at = None

    # ---------------- 관찰 ----------------
    def on_status(self, roi_id: str, state: str, detail: str) -> None:
        st = self.stats[roi_id]
        changed = (state, detail) != (st.last_state, st.last_detail)
        judged_on_stop = detail.startswith("[정지 판정")
        # 판정 수: 연속 판정은 매 검사마다, '정지 시 판정'은 새 판정이 나왔을 때만 센다
        if state in ("ok", "alarm", "pending") and (changed or not judged_on_stop):
            st.inspections += 1
            if state == "ok":
                st.ok += 1
        if judged_on_stop and changed and state in ("ok", "alarm"):
            self.say("observe", f"[{self._name(roi_id)}] 정지 감지 → 판정 {'OK' if state == 'ok' else 'NG'}")
        st.last_state, st.last_detail = state, detail

        now = self.clock()
        if state == "skip":
            since = self._skip_since.setdefault(roi_id, now)
            if now - since >= SKIP_PERSIST and self._ready(f"skip:{roi_id}", "skip"):
                self.say("think", f"[{self._name(roi_id)}] {int(now - since)}초째 다른 화면 – "
                                  "NVR 창이 가려졌거나 최소화된 것으로 추정")
                self.say("act", "오탐 방지를 위해 판정 보류 유지 · NVR 화면을 앞으로 가져와 주세요")
        else:
            self._skip_since.pop(roi_id, None)
        if state == "error" and self._ready(f"error:{roi_id}", "error"):
            self.say("warn", f"[{self._name(roi_id)}] 검사 오류 – {detail[:80]}")

    def on_alert(self, info: dict) -> List[Action]:
        now = self.clock()
        roi_id, name = info["roi_id"], info["roi_name"]
        st = self.stats[roi_id]
        st.ng += 1
        st.last_ng = now
        st.ng_times.append(now)
        self.hourly_ng[datetime.fromtimestamp(now).strftime("%Y-%m-%d %H")] += 1
        self.timeline.append((now, name, "NG 지속" if info.get("kind") == "repeat" else "NG",
                              info.get("detail", "")))
        self.say("observe", f"[{name}] 이상 감지 – {info.get('detail', '')[:70]}")

        # 1) 동시다발 경보 → 화면 전체 문제 추론
        self._recent_alerts.append((now, roi_id))
        while self._recent_alerts and now - self._recent_alerts[0][0] > MASS_WINDOW:
            self._recent_alerts.popleft()
        rois = {r for _t, r in self._recent_alerts}
        if (len(rois) >= MASS_MIN_ROIS and self.enabled_count
                and len(rois) >= self.enabled_count * MASS_RATIO and self._ready("mass", "mass")):
            self.say("think", f"{int(MASS_WINDOW)}초 안에 ROI {len(rois)}/{self.enabled_count}개 동시 이상 → "
                              "개별 불량이 아니라 NVR 화면 전체 문제(레이아웃 변경·영상 끊김·화면 꺼짐)로 추론")
            self.say("act", "원인 추정을 담은 통합 알림 전송")
            return [Action("teams", "NVR 화면 전체 이상 의심",
                           f"{int(MASS_WINDOW)}초 안에 ROI {len(rois)}개에서 동시에 이상이 감지되었습니다. "
                           "개별 불량보다는 NVR 화면 레이아웃 변경, 카메라 영상 끊김, 모니터 꺼짐 가능성이 높습니다. "
                           "NVR 화면 상태를 먼저 확인해 주세요.")]
        # 2) 같은 ROI 연속 불량 → 설비 점검 에스컬레이션
        recent = [t for t in st.ng_times if now - t <= TREND_WINDOW]
        if len(recent) >= TREND_COUNT and self._ready(f"trend:{roi_id}", "trend"):
            self.say("think", f"[{name}] {int(TREND_WINDOW // 60)}분 안에 불량 {len(recent)}회 → "
                              "일시적 이상이 아닌 공정/설비 문제 추세로 판단")
            self.say("act", "설비 점검 에스컬레이션 전송")
            return [Action("teams", f"[{name}] 연속 불량 – 설비 점검 요청",
                           f"최근 {int(TREND_WINDOW // 60)}분 동안 [{name}]에서 불량이 {len(recent)}회 감지되었습니다. "
                           "일시적 이상이 아닌 공정 추세로 보이니 설비 점검을 권장합니다.")]
        return []

    def on_recover(self, info: dict) -> None:
        self.timeline.append((self.clock(), info["roi_name"], "복구", info.get("detail", "")))
        self.say("observe", f"[{info['roi_name']}] 정상 복구 확인")

    def on_monitor_stopped(self, reason: str, auto_restart: bool) -> List[Action]:
        """검출 엔진이 멈췄을 때. 오류로 멈췄으면 자동 재시작을 결정한다."""
        now = self.clock()
        self.shutdown(reason)
        if "오류" not in reason or not auto_restart:
            return []
        while self._restarts and now - self._restarts[0] > 3600:
            self._restarts.popleft()
        if len(self._restarts) >= RESTART_LIMIT:
            self.say("think", f"최근 1시간 자동 재시작 {RESTART_LIMIT}회 소진 → 반복 장애로 판단, 재시작 중단")
            return [Action("teams", "NVR 검출기 반복 장애",
                           f"검출 엔진이 1시간 안에 {RESTART_LIMIT}회 넘게 오류로 멈췄습니다. 현장 확인이 필요합니다. ({reason})")]
        self._restarts.append(now)
        self.say("think", "일시적 오류로 판단 → 자가 복구 시도")
        self.say("act", f"검출 엔진 자동 재시작 ({len(self._restarts)}/{RESTART_LIMIT})")
        return [Action("restart")]

    # ---------------- 학습 ----------------
    def on_feedback(self, roi_name: str, cls: str, before: Optional[float], after: Optional[float]) -> None:
        label = {"ok": "OK(오탐 정정)", "ng": "NG", "skip": "무시"}.get(cls, cls)
        self.say("learn", f"[{roi_name}] 운영자 피드백 반영: {label} 샘플 +1")
        if before is not None and after is not None:
            arrow = "↑" if after > before else ("↓" if after < before else "=")
            self.say("learn", f"[{roi_name}] OK 허용 거리 자동 재보정 {before:.2f} {arrow} {after:.2f}")

    # ---------------- 교대 리포트 ----------------
    def due_shift(self, shift_times: str) -> Optional[str]:
        """교대 시각(예: '08:00,20:00')이 막 지났으면 그 키를 반환 (시각마다 한 번만)."""
        now = datetime.fromtimestamp(self.clock())
        for token in (t.strip() for t in shift_times.split(",") if t.strip()):
            try:
                hh, mm = (int(x) for x in token.split(":"))
            except ValueError:
                continue
            if not (0 <= hh < 24 and 0 <= mm < 60):
                continue
            at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            key = at.strftime("%Y-%m-%d %H:%M")
            if 0 <= (now - at).total_seconds() < 120 and key != self._last_shift_key:
                self._last_shift_key = key
                return key
        return None

    # ---------------- 지표 ----------------
    def kpis(self) -> dict:
        total = sum(s.inspections for s in self.stats.values())
        ng = sum(s.ng for s in self.stats.values())
        uptime = self.clock() - self.started_at if self.started_at else 0.0
        alarms = sum(1 for s in self.stats.values() if s.last_state == "alarm")
        ok_rate = max(0.0, 100.0 * (1 - ng / total)) if total else None
        return {"uptime": uptime, "inspections": total, "ng": ng, "ok_rate": ok_rate, "alarms": alarms}

    def hourly_series(self, hours: int = 12) -> List[Tuple[str, int]]:
        now = datetime.fromtimestamp(self.clock())
        out = []
        for i in range(hours - 1, -1, -1):
            t = now - timedelta(hours=i)
            out.append((t.strftime("%H"), self.hourly_ng.get(t.strftime("%Y-%m-%d %H"), 0)))
        return out

    def report_summary(self) -> str:
        k = self.kpis()
        top = sorted(((s.ng, self._name(rid)) for rid, s in self.stats.items() if s.ng), reverse=True)[:3]
        ok_rate = f"{k['ok_rate']:.2f}%" if k["ok_rate"] is not None else "-"
        text = f"판정 {k['inspections']:,}회 · NG {k['ng']}건 · 정상률 {ok_rate}"
        if top:
            text += " · NG 상위: " + ", ".join(f"{n} {c}건" for c, n in top)
        return text

    def report_html(self, title: str, rois) -> str:
        k = self.kpis()
        now = datetime.fromtimestamp(self.clock())
        rows = []
        for r in rois:
            s = self.stats.get(r.id, RoiStats())
            last = datetime.fromtimestamp(s.last_ng).strftime("%H:%M:%S") if s.last_ng else "-"
            rows.append(f"<tr><td>{html.escape(r.name)}</td><td>{html.escape(r.detector_label())}</td>"
                        f"<td>{s.inspections:,}</td><td class='{'ng' if s.ng else ''}'>{s.ng}</td><td>{last}</td>"
                        f"<td>{html.escape(r.assignee or '-')}</td></tr>")
        events = "".join(
            f"<tr><td>{datetime.fromtimestamp(t).strftime('%m-%d %H:%M:%S')}</td><td>{html.escape(n)}</td>"
            f"<td>{html.escape(kind)}</td><td>{html.escape(d)}</td></tr>"
            for t, n, kind, d in list(self.timeline)[-200:][::-1]) or "<tr><td colspan=4>기록 없음</td></tr>"
        insights = "".join(f"<li>{html.escape(f.text)}</li>" for f in self.feed if f.kind in ("think", "learn"))
        ok_rate = f"{k['ok_rate']:.2f}%" if k["ok_rate"] is not None else "-"
        hours, mins = int(k["uptime"] // 3600), int(k["uptime"] % 3600 // 60)
        return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#0b1220;color:#e6edf7;margin:32px}}
h1{{color:#22d3ee;margin:0}} .sub{{color:#8aa0c0;margin:4px 0 24px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}}
.kpi{{background:#16213a;border:1px solid #23304d;border-radius:10px;padding:14px 18px;min-width:150px}}
.kpi b{{display:block;font-size:26px;color:#fff}} .kpi span{{color:#8aa0c0;font-size:13px}}
table{{border-collapse:collapse;width:100%;margin-bottom:24px;background:#111a2e}}
th,td{{border-bottom:1px solid #23304d;padding:8px 10px;text-align:left;font-size:13px}}
th{{color:#8aa0c0;font-weight:600}} td.ng{{color:#ef4444;font-weight:700}} h2{{color:#cbd5e1;font-size:17px}}
li{{margin:4px 0;color:#cbd5e1}}
</style></head><body>
<h1>◆ {html.escape(title)}</h1><div class="sub">작성 {now:%Y-%m-%d %H:%M} · NVR 비전 에이전트 자동 리포트</div>
<div class="kpis">
<div class="kpi"><span>가동 시간</span><b>{hours}h {mins:02d}m</b></div>
<div class="kpi"><span>판정 수</span><b>{k['inspections']:,}</b></div>
<div class="kpi"><span>NG 감지</span><b style="color:#ef4444">{k['ng']}</b></div>
<div class="kpi"><span>정상률</span><b>{ok_rate}</b></div>
<div class="kpi"><span>감시 ROI</span><b>{sum(1 for r in rois if r.enabled)}</b></div>
</div>
<h2>ROI별 현황</h2><table><tr><th>ROI</th><th>검출 유형</th><th>판정 수</th><th>NG</th><th>마지막 NG</th><th>담당자</th></tr>
{''.join(rows)}</table>
<h2>에이전트 판단·학습 기록</h2><ul>{insights or '<li>특이사항 없음</li>'}</ul>
<h2>이벤트 타임라인</h2><table><tr><th>시각</th><th>ROI</th><th>구분</th><th>상세</th></tr>{events}</table>
</body></html>"""

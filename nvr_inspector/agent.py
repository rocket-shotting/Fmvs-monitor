"""FMVS 비전 에이전트 – 관찰 → 판단 → 실행 → 학습 루프 (PC 내부에서만 동작, 외부 전송 없음).

검출 엔진(worker)이 보내는 상태/경보 이벤트를 관찰하고, 스스로 원인을 추론해 행동을 결정한다.
  · 동시다발 경보 → 개별 불량이 아니라 FMVS 화면 전체 문제(레이아웃 변경·영상 끊김)로 판단
  · 같은 ROI 연속 불량 → 설비 점검 에스컬레이션
  · FMVS 창 가려짐/최소화 지속 → 원인 안내
  · 검출 엔진 비정상 종료 → 자동 재시작 (시간당 횟수 제한)
  · 운영자 피드백(OK/NG 등록) → 자동 기준 재보정 결과 기록
  · 교대 시각 → 근무 리포트 자동 작성

순수 로직이며 화면(Tk)과 무관하다. 실행이 필요한 행동은 Action 목록으로 돌려주고 GUI가 수행한다."""
import html
import re
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Deque, Dict, List, Optional, Tuple

from i18n import language, tr

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
# 정지 판정 상세 앞머리: '[정지 판정 HH:MM:SS] ' (언어와 무관하게 시각 형식으로 인식)
_STOP_STAMP = re.compile(r"^\[[^\]]*\d{2}:\d{2}:\d{2}\]")


def _user_stop(reason: str) -> bool:
    return "사용자" in reason or "user" in reason.lower()  # i18n: skip


def _error_stop(reason: str) -> bool:
    return "오류" in reason or "error" in reason.lower()  # i18n: skip


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
    state_counts: Counter = field(default_factory=Counter)   # 상태별 보고 횟수 (의견 에이전트 분석용)


class VisionAgent:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.feed: Deque[FeedItem] = deque(maxlen=400)
        self.stats: Dict[str, RoiStats] = defaultdict(RoiStats)
        self.names: Dict[str, str] = {}
        self.enabled_count = 0
        self.started_at: Optional[float] = None
        self.hourly_ng: Counter = Counter()        # 'YYYY-MM-DD HH' → NG 수
        self.roi_hourly: Dict[str, Counter] = defaultdict(Counter)   # ROI별 'YYYY-MM-DD HH' → NG 수
        # (시각, ROI, 구분, 상세, 스냅샷 경로)
        self.timeline: Deque[Tuple[float, str, str, str, Optional[str]]] = deque(maxlen=500)
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
        self.say("boot", tr("비전 에이전트 기동 – 감시 대상 ROI {n}개", n=self.enabled_count))
        if kinds:
            self.say("boot", tr("판정 엔진 로드: {engines}",
                                engines=", ".join(f"{k} {v}" for k, v in kinds.most_common())))
        total = sum(sample_counts.values())
        if total:
            self.say("boot", tr("샘플/기준 이미지 {n}장 인덱싱 완료 · 자동 기준 보정 준비", n=total))
        still = sum(1 for r in rois if r.enabled and r.still_only)
        if still:
            self.say("boot", tr("움직임 추적 모드 ROI {n}개 – 정지 순간에만 판정", n=still))
        self.say("observe", tr("실시간 관찰 시작"))

    def shutdown(self, reason: str) -> None:
        self.say("act" if _user_stop(reason) else "warn", tr("검출 엔진 정지 ({reason})", reason=reason))
        self.started_at = None

    # ---------------- 관찰 ----------------
    def on_status(self, roi_id: str, state: str, detail: str) -> None:
        st = self.stats[roi_id]
        st.state_counts[state] += 1
        changed = (state, detail) != (st.last_state, st.last_detail)
        judged_on_stop = bool(_STOP_STAMP.match(detail))
        # 판정 수: 연속 판정은 매 검사마다, '정지 시 판정'은 새 판정이 나왔을 때만 센다
        if state in ("ok", "alarm", "pending") and (changed or not judged_on_stop):
            st.inspections += 1
            if state == "ok":
                st.ok += 1
        if judged_on_stop and changed and state in ("ok", "alarm"):
            self.say("observe", tr("[{name}] 정지 감지 → 판정 {result}", name=self._name(roi_id),
                                   result="OK" if state == "ok" else "NG"))
        st.last_state, st.last_detail = state, detail

        now = self.clock()
        if state == "skip":
            since = self._skip_since.setdefault(roi_id, now)
            if now - since >= SKIP_PERSIST and self._ready(f"skip:{roi_id}", "skip"):
                self.say("think", tr("[{name}] {sec}초째 다른 화면 – "
                                     "FMVS 창이 가려졌거나 최소화된 것으로 추정",
                                     name=self._name(roi_id), sec=int(now - since)))
                self.say("act", tr("오탐 방지를 위해 판정 보류 유지 · FMVS 화면을 앞으로 가져와 주세요"))
        else:
            self._skip_since.pop(roi_id, None)
        if state == "error" and self._ready(f"error:{roi_id}", "error"):
            self.say("warn", tr("[{name}] 검사 오류 – {detail}", name=self._name(roi_id), detail=detail[:80]))

    def on_alert(self, info: dict) -> List[Action]:
        now = self.clock()
        roi_id, name = info["roi_id"], info["roi_name"]
        st = self.stats[roi_id]
        st.ng += 1
        st.last_ng = now
        st.ng_times.append(now)
        hour = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H")
        self.hourly_ng[hour] += 1
        self.roi_hourly[roi_id][hour] += 1
        self.timeline.append((now, name, tr("NG 지속") if info.get("kind") == "repeat" else "NG",
                              info.get("detail", ""), info.get("snapshot")))
        self.say("observe", tr("[{name}] 이상 감지 – {detail}", name=name, detail=info.get("detail", "")[:70]))

        # 1) 동시다발 경보 → 화면 전체 문제 추론
        self._recent_alerts.append((now, roi_id))
        while self._recent_alerts and now - self._recent_alerts[0][0] > MASS_WINDOW:
            self._recent_alerts.popleft()
        rois = {r for _t, r in self._recent_alerts}
        if (len(rois) >= MASS_MIN_ROIS and self.enabled_count
                and len(rois) >= self.enabled_count * MASS_RATIO and self._ready("mass", "mass")):
            self.say("think", tr("{sec}초 안에 ROI {n}/{total}개 동시 이상 → "
                                 "개별 불량이 아니라 FMVS 화면 전체 문제(레이아웃 변경·영상 끊김·화면 꺼짐)로 추론",
                                 sec=int(MASS_WINDOW), n=len(rois), total=self.enabled_count))
            self.say("act", tr("원인 추정을 담은 통합 알림 전송"))
            return [Action("teams", tr("FMVS 화면 전체 이상 의심"),
                           tr("{sec}초 안에 ROI {n}개에서 동시에 이상이 감지되었습니다. "
                              "개별 불량보다는 FMVS 화면 레이아웃 변경, 카메라 영상 끊김, 모니터 꺼짐 가능성이 높습니다. "
                              "FMVS 화면 상태를 먼저 확인해 주세요.", sec=int(MASS_WINDOW), n=len(rois)))]
        # 2) 같은 ROI 연속 불량 → 설비 점검 에스컬레이션
        recent = [t for t in st.ng_times if now - t <= TREND_WINDOW]
        if len(recent) >= TREND_COUNT and self._ready(f"trend:{roi_id}", "trend"):
            self.say("think", tr("[{name}] {min}분 안에 불량 {n}회 → "
                                 "일시적 이상이 아닌 공정/설비 문제 추세로 판단",
                                 name=name, min=int(TREND_WINDOW // 60), n=len(recent)))
            self.say("act", tr("설비 점검 에스컬레이션 전송"))
            return [Action("teams", tr("[{name}] 연속 불량 – 설비 점검 요청", name=name),
                           tr("최근 {min}분 동안 [{name}]에서 불량이 {n}회 감지되었습니다. "
                              "일시적 이상이 아닌 공정 추세로 보이니 설비 점검을 권장합니다.",
                              min=int(TREND_WINDOW // 60), name=name, n=len(recent)))]
        return []

    def on_recover(self, info: dict) -> None:
        self.timeline.append((self.clock(), info["roi_name"], tr("복구"), info.get("detail", ""), None))
        self.say("observe", tr("[{name}] 정상 복구 확인", name=info["roi_name"]))

    def on_monitor_stopped(self, reason: str, auto_restart: bool) -> List[Action]:
        """검출 엔진이 멈췄을 때. 오류로 멈췄으면 자동 재시작을 결정한다."""
        now = self.clock()
        self.shutdown(reason)
        if not _error_stop(reason) or not auto_restart:
            return []
        while self._restarts and now - self._restarts[0] > 3600:
            self._restarts.popleft()
        if len(self._restarts) >= RESTART_LIMIT:
            self.say("think", tr("최근 1시간 자동 재시작 {n}회 소진 → 반복 장애로 판단, 재시작 중단", n=RESTART_LIMIT))
            return [Action("teams", tr("FMVS 검출기 반복 장애"),
                           tr("검출 엔진이 1시간 안에 {n}회 넘게 오류로 멈췄습니다. 현장 확인이 필요합니다. ({reason})",
                              n=RESTART_LIMIT, reason=reason))]
        self._restarts.append(now)
        self.say("think", tr("일시적 오류로 판단 → 자가 복구 시도"))
        self.say("act", tr("검출 엔진 자동 재시작 ({n}/{limit})", n=len(self._restarts), limit=RESTART_LIMIT))
        return [Action("restart")]

    # ---------------- 학습 ----------------
    def on_feedback(self, roi_name: str, cls: str, before: Optional[float], after: Optional[float]) -> None:
        label = {"ok": tr("OK(오탐 정정)"), "ng": "NG", "skip": tr("무시")}.get(cls, cls)
        self.say("learn", tr("[{name}] 운영자 피드백 반영: {label} 샘플 +1", name=roi_name, label=label))
        if before is not None and after is not None:
            arrow = "↑" if after > before else ("↓" if after < before else "=")
            self.say("learn", tr("[{name}] OK 허용 거리 자동 재보정 {before} {arrow} {after}", name=roi_name,
                                 before=f"{before:.2f}", arrow=arrow, after=f"{after:.2f}"))

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
    def rename_snapshots(self, renamed: dict) -> None:
        """스냅샷 파일 이름이 NVR 시간으로 바뀌면 기록(리포트 이미지)의 경로도 바꾼다."""
        if not renamed:
            return
        self.timeline = deque(((t, n, k, d, renamed.get(snap, snap)) for t, n, k, d, snap in self.timeline),
                              maxlen=self.timeline.maxlen)

    def kpis(self) -> dict:
        total = sum(s.inspections for s in self.stats.values())
        ng = sum(s.ng for s in self.stats.values())
        uptime = self.clock() - self.started_at if self.started_at else 0.0
        alarms = sum(1 for s in self.stats.values() if s.last_state == "alarm")
        ok_rate = max(0.0, 100.0 * (1 - ng / total)) if total else None
        return {"uptime": uptime, "inspections": total, "ng": ng, "ok_rate": ok_rate, "alarms": alarms}

    def hourly_series(self, hours: int = 12, roi_id: Optional[str] = None) -> List[Tuple[str, int]]:
        """최근 hours시간의 시간대별 NG 수. roi_id를 주면 그 ROI만."""
        counter = self.hourly_ng if roi_id is None else self.roi_hourly.get(roi_id, Counter())
        now = datetime.fromtimestamp(self.clock())
        out = []
        for i in range(hours - 1, -1, -1):
            t = now - timedelta(hours=i)
            out.append((t.strftime("%H"), counter.get(t.strftime("%Y-%m-%d %H"), 0)))
        return out

    def roi_trends(self, rois, hours: int = 12) -> List[dict]:
        """ROI별 트렌드 (대시보드·미니 모니터·리포트 공용)."""
        out = []
        for r in rois:
            st = self.stats.get(r.id, RoiStats())
            series = self.hourly_series(hours, r.id)
            out.append({"id": r.id, "name": r.name, "enabled": r.enabled, "state": st.last_state,
                        "ng": st.ng, "inspections": st.inspections,
                        "recent": sum(c for _h, c in series), "series": series})
        return out

    def report_summary(self) -> str:
        k = self.kpis()
        top = sorted(((s.ng, self._name(rid)) for rid, s in self.stats.items() if s.ng), reverse=True)[:3]
        ok_rate = f"{k['ok_rate']:.2f}%" if k["ok_rate"] is not None else "-"
        text = tr("판정 {n}회 · NG {ng}건 · 정상률 {rate}", n=f"{k['inspections']:,}", ng=k["ng"], rate=ok_rate)
        if top:
            text += tr(" · NG 상위: {items}", items=", ".join(tr("{name} {n}건", name=n, n=c) for c, n in top))
        return text

    def report_html(self, title: str, rois, frames: Optional[Dict[str, object]] = None,
                    max_images: int = 40) -> str:
        """근무 리포트(HTML, 이미지 내장). frames: ROI별 최신 화면(RGB 배열) – 현재 화면 갤러리에 사용.
        이미지를 파일 안에 넣으므로 스냅샷이 보관 기간 후 삭제돼도 리포트에는 남는다."""
        k = self.kpis()
        now = datetime.fromtimestamp(self.clock())
        rows = []
        for t in self.roi_trends(rois):
            r = next(x for x in rois if x.id == t["id"])
            s = self.stats.get(r.id, RoiStats())
            last = datetime.fromtimestamp(s.last_ng).strftime("%H:%M:%S") if s.last_ng else "-"
            peak = max([c for _h, c in t["series"]] + [1])
            bars = "".join(f"<i style='height:{max(2, int(22 * c / peak)) if c else 2}px' "
                           f"class='{'b ng' if c else 'b'}' title='{tr('{h}시 {n}건', h=h, n=c)}'></i>" for h, c in t["series"])
            rows.append(f"<tr><td>{html.escape(r.name)}</td><td>{html.escape(r.detector_label())}</td>"
                        f"<td>{s.inspections:,}</td><td class='{'ng' if s.ng else ''}'>{s.ng}</td><td>{last}</td>"
                        f"<td><div class='spark'>{bars}</div></td><td>{html.escape(r.assignee or '-')}</td></tr>")
        # 현재 화면 (ROI별 최신 프레임)
        live = []
        for r in rois:
            img = (frames or {}).get(r.id)
            uri = _image_uri(img, 320) if img is not None else None
            if uri:
                live.append(f"<figure><img src='{uri}'><figcaption>{html.escape(r.name)}</figcaption></figure>")
        # NG 스냅샷 (최근 순)
        gallery = []
        for t, n, kind, d, snap in reversed(list(self.timeline)):
            if kind.startswith("NG") and snap and len(gallery) < max_images:
                uri = _image_uri(snap, 360)
                if uri:
                    gallery.append(f"<figure class='ngfig'><img src='{uri}'><figcaption><b>{html.escape(n)}</b> · "
                                   f"{datetime.fromtimestamp(t).strftime('%m-%d %H:%M:%S')}<br>{html.escape(d[:90])}"
                                   f"</figcaption></figure>")
        events = "".join(
            f"<tr><td>{datetime.fromtimestamp(t).strftime('%m-%d %H:%M:%S')}</td><td>{html.escape(n)}</td>"
            f"<td class='{'ng' if kind.startswith('NG') else ''}'>{html.escape(kind)}</td><td>{html.escape(d)}</td></tr>"
            for t, n, kind, d, _s in list(self.timeline)[-200:][::-1]) or f"<tr><td colspan=4>{tr('기록 없음')}</td></tr>"
        insights = "".join(f"<li>{html.escape(f.text)}</li>" for f in self.feed if f.kind in ("think", "learn"))
        ok_rate = f"{k['ok_rate']:.2f}%" if k["ok_rate"] is not None else "-"
        hours, mins = int(k["uptime"] // 3600), int(k["uptime"] % 3600 // 60)
        more = tr(", 최근 {n}장까지", n=max_images) if len(gallery) >= max_images else ""
        L = {key: tr(key) for key in (
            "가동 시간", "판정 수", "NG 감지", "정상률", "감시 ROI", "ROI별 현황 · 최근 12시간 NG 추이", "검출 유형",
            "마지막 NG", "NG 추이", "담당자", "NG 이미지 없음", "리포트 작성 시점 ROI 화면",
            "검출 중이 아니어서 현재 화면 없음", "에이전트 판단·학습 기록", "특이사항 없음", "이벤트 타임라인",
            "시각", "구분", "상세")}
        written = tr("작성 {time} · FMVS 비전 에이전트 자동 리포트", time=f"{now:%Y-%m-%d %H:%M}")
        gallery_title = tr("NG 탐지 이미지 ({n}장{more})", n=len(gallery), more=more)
        return f"""<!doctype html><html lang="{language()}"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#0b1220;color:#e6edf7;margin:32px}}
h1{{color:#22d3ee;margin:0}} .sub{{color:#8aa0c0;margin:4px 0 24px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}}
.kpi{{background:#16213a;border:1px solid #23304d;border-radius:10px;padding:14px 18px;min-width:150px}}
.kpi b{{display:block;font-size:26px;color:#fff}} .kpi span{{color:#8aa0c0;font-size:13px}}
table{{border-collapse:collapse;width:100%;margin-bottom:24px;background:#111a2e}}
th,td{{border-bottom:1px solid #23304d;padding:8px 10px;text-align:left;font-size:13px;vertical-align:middle}}
th{{color:#8aa0c0;font-weight:600}} td.ng{{color:#ef4444;font-weight:700}} h2{{color:#cbd5e1;font-size:17px}}
li{{margin:4px 0;color:#cbd5e1}}
.spark{{display:flex;align-items:flex-end;gap:2px;height:24px}} .b{{display:inline-block;width:7px;background:#23304d}}
.b.ng{{background:#ef4444}}
.gal{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px}}
figure{{margin:0;background:#111a2e;border:1px solid #23304d;border-radius:8px;padding:6px}}
figure img{{display:block;max-width:360px;border-radius:4px}} .ngfig{{border-color:#7f1d1d}}
figcaption{{font-size:12px;color:#cbd5e1;margin-top:4px;max-width:360px}}
</style></head><body>
<h1>◆ {html.escape(title)}</h1><div class="sub">{written}</div>
<div class="kpis">
<div class="kpi"><span>{L['가동 시간']}</span><b>{hours}h {mins:02d}m</b></div>
<div class="kpi"><span>{L['판정 수']}</span><b>{k['inspections']:,}</b></div>
<div class="kpi"><span>{L['NG 감지']}</span><b style="color:#ef4444">{k['ng']}</b></div>
<div class="kpi"><span>{L['정상률']}</span><b>{ok_rate}</b></div>
<div class="kpi"><span>{L['감시 ROI']}</span><b>{sum(1 for r in rois if r.enabled)}</b></div>
</div>
<h2>{L['ROI별 현황 · 최근 12시간 NG 추이']}</h2><table><tr><th>ROI</th><th>{L['검출 유형']}</th><th>{L['판정 수']}</th><th>NG</th>
<th>{L['마지막 NG']}</th><th>{L['NG 추이']}</th><th>{L['담당자']}</th></tr>{''.join(rows)}</table>
<h2>{gallery_title}</h2>
<div class="gal">{''.join(gallery) or '<p>' + L['NG 이미지 없음'] + '</p>'}</div>
<h2>{L['리포트 작성 시점 ROI 화면']}</h2><div class="gal">{''.join(live) or '<p>' + L['검출 중이 아니어서 현재 화면 없음'] + '</p>'}</div>
<h2>{L['에이전트 판단·학습 기록']}</h2><ul>{insights or '<li>' + L['특이사항 없음'] + '</li>'}</ul>
<h2>{L['이벤트 타임라인']}</h2><table><tr><th>{L['시각']}</th><th>ROI</th><th>{L['구분']}</th><th>{L['상세']}</th></tr>{events}</table>
</body></html>"""


def _image_uri(source, max_side: int) -> Optional[str]:
    """이미지 파일 경로 또는 RGB 배열 → 리포트에 넣을 JPEG data URI. 실패하면 None."""
    import base64
    import io
    import os
    try:
        from PIL import Image
        if isinstance(source, str):
            if not os.path.exists(source):
                return None
            with Image.open(source) as im:
                img = im.convert("RGB")
        else:
            img = Image.fromarray(source).convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None

"""영어 번역 (원문 한국어 → 영어)."""

EN = {
    # ---- agent.py: 활동 피드 종류 ----
    "시작": "Start",
    "관찰": "Observe",
    "판단": "Think",
    "실행": "Act",
    "학습": "Learn",
    "주의": "Warning",

    # ---- agent.py: 활동 피드 메시지 ----
    "비전 에이전트 기동 – 감시 대상 ROI {n}개": "Vision agent started – monitoring {n} ROIs",
    "판정 엔진 로드: {engines}": "Judgment engines loaded: {engines}",
    "샘플/기준 이미지 {n}장 인덱싱 완료 · 자동 기준 보정 준비":
        "Indexed {n} sample/reference images · auto-calibration ready",
    "움직임 추적 모드 ROI {n}개 – 정지 순간에만 판정": "{n} ROIs in motion-tracking mode – judged only when still",
    "실시간 관찰 시작": "Live observation started",
    "검출 엔진 정지 ({reason})": "Detection engine stopped ({reason})",
    "[{name}] 정지 감지 → 판정 {result}": "[{name}] Stop detected → judgment {result}",
    "[{name}] {sec}초째 다른 화면 – FMVS 창이 가려졌거나 최소화된 것으로 추정":
        "[{name}] Other screen for {sec}s – FMVS window seems covered or minimized",
    "오탐 방지를 위해 판정 보류 유지 · FMVS 화면을 앞으로 가져와 주세요":
        "Holding judgment to avoid false alarms · please bring the FMVS screen to the front",
    "[{name}] 검사 오류 – {detail}": "[{name}] Inspection error – {detail}",
    "NG 지속": "NG ongoing",
    "[{name}] 이상 감지 – {detail}": "[{name}] Abnormality detected – {detail}",
    "{sec}초 안에 ROI {n}/{total}개 동시 이상 → 개별 불량이 아니라 FMVS 화면 전체 문제(레이아웃 변경·영상 끊김·화면 꺼짐)로 추론":
        "{n}/{total} ROIs abnormal within {sec}s → inferred a whole-screen FMVS problem "
        "(layout change, video loss or screen off), not individual defects",
    "원인 추정을 담은 통합 알림 전송": "Sending a combined alert with the probable cause",
    "FMVS 화면 전체 이상 의심": "Suspected whole-screen FMVS problem",
    "{sec}초 안에 ROI {n}개에서 동시에 이상이 감지되었습니다. 개별 불량보다는 FMVS 화면 레이아웃 변경, "
    "카메라 영상 끊김, 모니터 꺼짐 가능성이 높습니다. FMVS 화면 상태를 먼저 확인해 주세요.":
        "Abnormalities were detected in {n} ROIs at once within {sec}s. Rather than individual defects, "
        "an FMVS layout change, camera video loss or a monitor turned off is more likely. "
        "Please check the FMVS screen first.",
    "[{name}] {min}분 안에 불량 {n}회 → 일시적 이상이 아닌 공정/설비 문제 추세로 판단":
        "[{name}] {n} defects within {min} min → judged a process/equipment trend, not a transient issue",
    "설비 점검 에스컬레이션 전송": "Sending equipment-check escalation",
    "[{name}] 연속 불량 – 설비 점검 요청": "[{name}] Repeated defects – equipment check requested",
    "최근 {min}분 동안 [{name}]에서 불량이 {n}회 감지되었습니다. 일시적 이상이 아닌 공정 추세로 보이니 "
    "설비 점검을 권장합니다.":
        "{n} defects were detected on [{name}] in the last {min} min. This looks like a process trend "
        "rather than a transient issue, so an equipment check is recommended.",
    "복구": "Recovered",
    "[{name}] 정상 복구 확인": "[{name}] Recovery to OK confirmed",
    "최근 1시간 자동 재시작 {n}회 소진 → 반복 장애로 판단, 재시작 중단":
        "{n} auto-restarts used in the last hour → judged a recurring fault, restarts stopped",
    "FMVS 검출기 반복 장애": "FMVS detector recurring fault",
    "검출 엔진이 1시간 안에 {n}회 넘게 오류로 멈췄습니다. 현장 확인이 필요합니다. ({reason})":
        "The detection engine stopped on error more than {n} times within an hour. "
        "On-site check required. ({reason})",
    "일시적 오류로 판단 → 자가 복구 시도": "Judged a transient error → attempting self-recovery",
    "검출 엔진 자동 재시작 ({n}/{limit})": "Auto-restarting detection engine ({n}/{limit})",
    "OK(오탐 정정)": "OK (false alarm fixed)",
    "무시": "Ignore",
    "[{name}] 운영자 피드백 반영: {label} 샘플 +1": "[{name}] Operator feedback applied: {label} sample +1",
    "[{name}] OK 허용 거리 자동 재보정 {before} {arrow} {after}":
        "[{name}] OK tolerance auto-recalibrated {before} {arrow} {after}",

    # ---- agent.py: 요약 / HTML 리포트 ----
    "판정 {n}회 · NG {ng}건 · 정상률 {rate}": "{n} judgments · {ng} NG · OK rate {rate}",
    " · NG 상위: {items}": " · Top NG: {items}",
    "{name} {n}건": "{name} {n}",
    "{h}시 {n}건": "{h}h: {n}",
    "기록 없음": "No records",
    ", 최근 {n}장까지": ", latest {n} max",
    "작성 {time} · FMVS 비전 에이전트 자동 리포트": "Created {time} · FMVS Vision Agent automatic report",
    "NG 탐지 이미지 ({n}장{more})": "NG detection images ({n}{more})",
    "가동 시간": "Uptime",
    "판정 수": "Judgments",
    "NG 감지": "NG detected",
    "정상률": "OK rate",
    "감시 ROI": "Monitored ROIs",
    "ROI별 현황 · 최근 12시간 NG 추이": "Status by ROI · NG trend, last 12 hours",
    "검출 유형": "Detection type",
    "마지막 NG": "Last NG",
    "NG 추이": "NG trend",
    "담당자": "Assignee",
    "NG 이미지 없음": "No NG images",
    "리포트 작성 시점 ROI 화면": "ROI screens at report time",
    "검출 중이 아니어서 현재 화면 없음": "No current screens (detection not running)",
    "에이전트 판단·학습 기록": "Agent judgment and learning log",
    "특이사항 없음": "Nothing notable",
    "이벤트 타임라인": "Event timeline",
    "시각": "Time",
    "구분": "Type",
    "상세": "Detail",

    # ---- alert.py: 검출 팝업 ----
    "탐지 시각 (이 PC 시간)": "Detected at (this PC's time)",
    "복구 시각 (이 PC 시간)": "Recovered at (this PC's time)",
    "확인": "OK",
    "스냅샷": "Snapshot",
    "NG로 등록": "Register as NG",
    "OK로 등록(오탐)": "Register as OK (false alarm)",
    "무시로 등록(셀 없음)": "Register as Ignore (no cell)",
    "✅ 복구됨 – {name}": "✅ Recovered – {name}",
    "화면이 정상으로 돌아왔습니다.": "The screen is back to OK.",
    "현재 값: {value}": "Current value: {value}",
    "이상 지속 시간: {duration}": "Abnormal for: {duration}",
    "🚨 이상 지속 (재알림)": "🚨 Still abnormal (reminder)",
    "🚨 이상 탐지": "🚨 Abnormality detected",
    "검출 유형: {detector}": "Detection type: {detector}",
    "측정값: {value}": "Measured: {value}",
    "담당자: {assignee}": "Assignee: {assignee}",
    "미지정": "Unassigned",
    "지속 시간: {duration}": "Duration: {duration}",
    "연속 NG {n}회": "{n} consecutive NG",
    "이 ROI 누적 탐지 {n}회": "{n} detections on this ROI",
    " · 이전 탐지: {times}": " · Previous: {times}",
    "등록 실패": "Failed",
    "등록됨 ✔": "Registered ✔",

    # ---- overlay.py: 화면 오버레이 ----
    "정상": "OK",
    "확인 중": "Checking",
    "경보": "Alarm",
    "건너뜀": "Skipped",
    "대기": "Waiting",
    "움직임": "Moving",
    "꺼짐": "Off",
    "오류": "Error",
    "시작 중": "Starting",
    "FMVS 검출 시작 중…": "Starting FMVS detection…",
    "⚠ FMVS 검출기 응답 없음 · {time}": "⚠ FMVS detector not responding · {time}",
    "{dot} FMVS 검출 중 · 경보 {n}건 · {time}": "{dot} FMVS detecting · {n} alarms · {time}",
    "{dot} FMVS 검출 중 · ROI {n}개 · {time}": "{dot} FMVS detecting · {n} ROIs · {time}",

    # ---- dashboard.py: 대시보드 / 미니 모니터 ----
    "가려짐": "Covered",
    "로그": "Log",
    "등록된 ROI가 없습니다\n상단의 [＋ ROI 추가]로 감시할 카메라 영역을 지정하세요":
        "No ROIs registered\nUse [＋ Add ROI] at the top to select a camera area to monitor",
    "사용 안 함": "Disabled",
    "검사 준비 중": "Preparing inspection",
    "검출 대기 – ▶ 시작을 누르면 실시간 판정": "Standby – press ▶ Start for live judgment",
    "에이전트 관찰·판단·실행·학습 + 시스템 기록": "Agent Observe · Think · Act · Learn + system log",
    "ROI별 NG 추이 · 최근 12시간": "NG trend by ROI · last 12 h",
    "{h}시": "{h}h",
    "ROI를 추가하면 여기서 ROI별 NG 추이를 볼 수 있습니다": "Add ROIs to see the NG trend for each ROI here",
    "외 {n}개 ROI (창을 키우면 더 보입니다)": "+{n} more ROIs (enlarge the window to see them)",
    "외 {n}개 ROI": "+{n} more ROIs",
    "대시보드 열기": "Open dashboard",
    "● 실시간 감시 중": "● Live monitoring",
    "NG · 최근 12시간": "NG · last 12 h",
    "감시 중인 ROI 없음": "No ROIs being monitored",
    "시간대별 NG (최근 12시간)": "NG per hour (last 12 h)",
    "합계 {n}건": "Total {n}",
}

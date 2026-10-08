"""영어 번역 (원문 한국어 → 영어)."""

EN = {
    # ---- 상태 / 목록 열 (모듈 상수) ----
    "정상": "OK",
    "이상 감지(확인 중)": "Abnormal (verifying)",
    "🚨 경보": "🚨 Alarm",
    "건너뜀(다른 화면)": "Skipped (other screen)",
    "대기": "Waiting",
    "꺼짐": "Off",
    "오류": "Error",
    "움직임(대기)": "Moving (waiting)",
    "사용": "On",
    "이름": "Name",
    "검출 유형 · 샘플": "Detection type · Samples",
    "위치 (X,Y 폭×높이)": "Position (X,Y W×H)",
    "담당자": "Assignee",
    "상태": "State",
    "측정값 / 상세": "Measurement / Details",

    # ---- 헤더 / 도구 모음 ----
    "자율 영상 품질 관제 에이전트": "Autonomous video quality monitoring agent",
    "■  정지": "■  Stop",
    "▶  에이전트 시작": "▶  Start agent",
    "＋ ROI 추가": "+ Add ROI",
    "✎ 편집": "✎ Edit",
    "⌖ 위치 재지정": "⌖ Reposition",
    "⧉ 복제": "⧉ Duplicate",
    "◐ 사용/해제": "◐ On/Off",
    "🖼 샘플/기준 이미지": "🖼 Samples",
    "🗑 삭제": "🗑 Delete",
    "📁 폴더": "📁 Folder",
    "💬 Teams 테스트": "💬 Teams test",
    "📄 리포트 생성": "📄 Report",
    "⚙ 설정": "⚙ Settings",
    "카드 끌기: 이동 · ◢ 끌기: 크기 조절": "Drag card: move · Drag ◢: resize",
    "⟲ 자동 정렬": "⟲ Auto arrange",

    # ---- KPI ----
    "가동 시간": "Uptime",
    "판정 수": "Judgments",
    "NG 감지": "NG detected",
    "정상률": "OK rate",
    "감시 ROI": "Monitored ROIs",
    "현재 경보": "Active alarms",
    "에이전트 가동 중": "Agent running",
    "대기 중": "Waiting",
    "누적 판정": "Total judgments",
    "누적 이상 감지": "Total abnormal detections",
    "판정 대비 정상": "OK per judgment",
    "전체 {n}개 중 사용": "Enabled of {n} total",
    "즉시 확인 필요": "Check immediately",
    "이상 없음": "No issues",

    # ---- 목록 ----
    " · OK{ok}/NG{ng}/무시{skip}": " · OK{ok}/NG{ng}/Ignore{skip}",
    " · 기준 없음": " · No reference",

    # ---- 안내 / 메시지 상자 ----
    "안내": "Notice",
    "목록에서 ROI를 하나 선택하세요.": "Select one ROI in the list.",
    "목록에서 ROI를 선택하세요.": "Select ROIs in the list.",
    "저장 실패": "Save failed",
    "설정을 저장할 수 없습니다.\n{e}": "Could not save settings.\n{e}",
    "설정 저장 실패: {e}": "Failed to save settings: {e}",
    "화면 캡처/ROI 지정 실패: {e}": "Screen capture / ROI selection failed: {e}",
    "ROI 크기": "ROI size",
    "새로 그린 크기 {nw}×{nh}가 기존 {w}×{h}와 다릅니다.\n\n"
    "[예] 기존 크기 {w}×{h}를 유지하고 위치만 이동 (권장 – 샘플 그대로 사용)\n"
    "[아니오] 새 크기로 변경 (샘플/기준 이미지를 새 크기에 맞춰 유지)\n[취소] 변경 안 함":
        "The new size {nw}×{nh} differs from the current {w}×{h}.\n\n"
        "[Yes] Keep size {w}×{h} and move only (recommended – samples stay as is)\n"
        "[No] Change to the new size (samples/reference images are resized to fit)\n[Cancel] No change",
    "삭제 확인": "Confirm delete",
    "다음 ROI를 삭제할까요?\n{names}": "Delete these ROIs?\n{names}",
    "[{name}]의 검출 유형({label})은 샘플 이미지를 쓰지 않습니다.\n"
    "'OK/NG 이미지 매칭', '형상 검사', '기준 화면과 다름' 유형에서 사용합니다.":
        "The detection type of [{name}] ({label}) does not use sample images.\n"
        "Samples are used by the 'OK/NG image matching', 'Shape inspection' and "
        "'Differs from reference screen' types.",
    "[설정]에서 공통 Webhook URL을 먼저 입력하세요.\n"
    "(ROI를 선택하면 해당 ROI의 담당자/Webhook으로 테스트합니다)":
        "Enter the common Webhook URL in [Settings] first.\n"
        "(Select an ROI to test with that ROI's assignee/Webhook)",
    "사용 중인 ROI가 없습니다. [화면에서 ROI 추가]로 먼저 지정하세요.":
        "No ROIs are enabled. Add one first with [Add ROI].",
    "예기치 않은 오류가 발생했습니다.\n{value}\n\n자세한 내용은 logs 폴더를 확인하세요.":
        "An unexpected error occurred.\n{value}\n\nSee the logs folder for details.",
    "종료": "Exit",
    "검출이 실행 중입니다. 종료하면 감시가 멈춥니다.\n종료할까요?":
        "Detection is running. Exiting will stop monitoring.\nExit anyway?",

    # ---- ROI 조작 ----
    "새 ROI 설정 ({i}/{total}) – 취소하면 이 ROI는 추가하지 않음":
        "New ROI settings ({i}/{total}) – cancel to skip this ROI",
    "ROI {n}개 추가": "Added {n} ROI(s)",
    "ROI 설정 – {name}": "ROI settings – {name}",
    " · 크기 변경 → 샘플 {n}장 새 크기로 유지": " · size changed → {n} sample(s) resized",
    "[{name}] 설정 변경{note}": "[{name}] settings changed{note}",
    " · 샘플 {n}장 새 크기로 유지": " · {n} sample(s) resized",
    "[{name}] 위치 변경: {x},{y} {w}×{h} (샘플/기준 이미지 유지){note}":
        "[{name}] moved: {x},{y} {w}×{h} (samples/reference images kept){note}",
    "{name} 복사본": "{name} copy",
    "ROI 복제": "Duplicate ROI",
    "[{name}] 추가 (복제)": "[{name}] added (duplicate)",
    "ROI {n}개 사용": "{n} ROI(s) enabled",
    "ROI {n}개 해제": "{n} ROI(s) disabled",
    "ROI 삭제: {names}": "ROIs deleted: {names}",
    "[{name}] 샘플 이미지 갱신 (검출 중이면 바로 반영)":
        "[{name}] sample images updated (applied immediately if running)",
    "ROI가 삭제되었습니다.": "The ROI has been deleted.",
    "스냅샷을 열 수 없습니다: {e}": "Cannot open snapshot: {e}",
    "ROI 크기가 바뀌어 등록할 수 없습니다.": "The ROI size has changed; cannot register.",
    "[{name}] 경보 화면을 {label} 샘플로 등록: {file}":
        "[{name}] alarm image registered as {label} sample: {file}",
    "카메라 월 배치를 자동 정렬로 되돌렸습니다": "Camera wall layout reset to auto arrange",

    # ---- 설정 / Teams ----
    "설정 저장": "Settings saved",
    "공통": "Common",
    "Teams 테스트 ({name}): {err}": "Teams test ({name}): {err}",
    "(테스트)": "(test)",
    "테스트 메시지": "Test message",
    "테스트 ({name})": "Test ({name})",
    "Teams 테스트 전송 요청 {n}건 – 결과는 로그에 표시됩니다.":
        "{n} Teams test message(s) queued – results will appear in the log.",
    "Teams 알림이 켜져 있지만 Webhook URL이 없습니다. 팝업만 표시됩니다.":
        "Teams alerts are on but no Webhook URL is set. Only popups will be shown.",

    # ---- 시작 / 상태 ----
    "FMVS Vision Agent 준비 완료 – ROI {n}개 로드 · 외부 전송 없이 PC 내부에서 동작":
        "FMVS Vision Agent ready – {n} ROI(s) loaded · runs locally on this PC, no external transfer",
    "검출 시작 (ROI {n}개, {sec}초 주기)": "Detection started ({n} ROI(s), every {sec}s)",
    "⚠ 응답 없음": "⚠ Not responding",
    "● 감시 중 · 경보 {n}건": "● Monitoring · {n} alarm(s)",
    "● 실시간 감시 중 · 이상 없음": "● Live monitoring · No issues",
    "●  AGENT ONLINE · 실시간 감시 중": "●  AGENT ONLINE · Live monitoring",
    "○  STANDBY · 대기": "○  STANDBY · Waiting",
    "감시 중": "Monitoring",
    "이 Windows는 화면 표시를 캡처에서 제외하지 못합니다(Windows 10 2004 이상 필요). "
    "ROI끼리 붙어 있으면 테두리가 옆 ROI 판정에 영향을 줄 수 있으니 [설정]에서 화면 표시를 끄세요.":
        "This Windows version cannot exclude the on-screen overlay from capture (requires Windows 10 2004 or later). "
        "If ROIs are adjacent, borders may affect neighboring ROI judgments; turn off the overlay in [Settings].",
    "검출 엔진 응답 없음 {sec}초 – 감시 중": "Detection engine not responding for {sec}s – watching",
    "에이전트: 검출 엔진 자동 재시작": "Agent: auto-restarting detection engine",
    "Teams 알림 꺼짐 – 대시보드에만 기록": "Teams alerts off – recorded on dashboard only",
    "공통 Webhook URL이 없어 Teams 전송 생략": "No common Webhook URL – Teams message skipped",
    "에이전트: {title}": "Agent: {title}",

    # ---- 리포트 ----
    "FMVS 근무 리포트 {when}": "FMVS shift report {when}",
    "리포트 저장 실패: {e}": "Failed to save report: {e}",
    "교대 시각 도래 → ": "Shift change → ",
    "근무 리포트 작성: {file} ({summary})": "Shift report created: {file} ({summary})",
    "\n리포트 파일: {path}": "\nReport file: {path}",

    # ---- 상태 표시줄 ----
    "Teams 알림 켜짐": "Teams alerts on",
    "Teams 알림 꺼짐": "Teams alerts off",
    "● 검출 중": "● Detecting",
    "○ 중지됨": "○ Stopped",
    "{run}   |   ROI {enabled}/{total}개 사용   |   경보 {alarms}건   |   {teams}   |   설정 파일: {path}":
        "{run}   |   ROIs {enabled}/{total} enabled   |   {alarms} alarm(s)   |   {teams}   |   Settings file: {path}",

    # ---- 이벤트 ----
    "재알림": "Repeat alert",
    "이상 감지": "Abnormal detected",
    "🚨 [{name}] {tag} – {detail}": "🚨 [{name}] {tag} – {detail}",
    "[{name}] 연속 NG {count}/{need}회 – {need}회부터 팝업":
        "[{name}] consecutive NG {count}/{need} – popup from {need}",
    "✅ [{name}] 정상 복구 – {detail}": "✅ [{name}] back to OK – {detail}",
    "검출 중지 ({reason})": "Detection stopped ({reason})",
    "보관 기간({days}일) 지난 로그·스냅샷·리포트 {n}개 정리":
        "Cleaned up {n} log/snapshot/report file(s) older than the retention period ({days} days)",
    "화면 언어를 한국어로 바꿨습니다": "Display language changed to English",
}

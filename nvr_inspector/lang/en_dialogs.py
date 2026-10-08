"""영어 번역 (원문 한국어 → 영어)."""

EN = {
    # ---- 공통 버튼 / 메시지 제목 ----
    "저장": "Save",
    "취소": "Cancel",
    "닫기": "Close",
    "삭제": "Delete",
    "확인": "Confirm",
    "안내": "Info",
    "입력 오류": "Input error",
    "캡처 실패": "Capture failed",
    "감지 실패": "Detection failed",
    "이동 실패": "Move failed",
    "삭제 실패": "Delete failed",
    "일부 실패": "Partially failed",

    # ---- ROI 설정 창 (roi_dialog.py) ----
    "ROI 설정": "ROI settings",
    "기본": "Basic",
    "이름": "Name",
    "이 ROI 검출 사용": "Enable detection for this ROI",
    "폭": "W",
    "높이": "H",
    "검출 조건": "Detection conditions",
    "검출 유형": "Detection type",
    "이상 지속 시간(초) – 이 시간 이상 계속되면 경보": "Abnormal duration (s) – alarm if it lasts this long",
    "재알림 간격(분) – 0이면 한 번만": "Re-alert interval (min) – 0 = once only",
    "정상 복구 시에도 Teams 알림": "Notify Teams on recovery too",
    "움직이는 대상": "Moving target",
    "정지 시에만 판정 (움직이는 동안은 판정하지 않고, 멈춘 순간 1회 판정)":
        "Judge only when stopped (no judgment while moving; judge once when it stops)",
    "정지 기준 변화량 (이 값 이하면 정지, 0.1~255)": "Stop threshold change (at or below = stopped, 0.1~255)",
    "정지 확인 횟수 (연속 n번 변화 없으면 정지)": "Stop confirmations (stopped after n unchanged checks in a row)",
    "켜면 '이상 지속 시간'은 쓰지 않고, 멈출 때마다 판정해 NG면 바로 알립니다.\n"
    "[현재 화면으로 측정]에서 지금 변화량을 확인해 기준을 정하세요.\n"
    "검사 주기 × 정지 확인 횟수보다 오래 멈춰야 판정됩니다.":
        "When on, 'Abnormal duration' is not used; it judges each time the target stops and alerts immediately on NG.\n"
        "Use [Measure current screen] to check the current change amount and set the threshold.\n"
        "The target must stay stopped longer than check interval × stop confirmations to be judged.",
    "현재 화면으로 측정": "Measure current screen",
    "조건 조정 후 눌러서 현재 값을 확인하세요.": "Adjust the conditions, then press to check the current value.",
    "대상 프로그램 확인 (다른 창이 덮으면 검사 건너뜀)": "Target program check (skip inspection if covered by another window)",
    "지금 화면에서 감지": "Detect from screen",
    "예: NVR_VIEWER.exe  ·  비우면 확인하지 않음\n"
    "창 핸들이 아닌 프로그램(프로세스) 이름으로 비교하므로\n"
    "FMVS이 내부적으로 창을 다시 만들어도 오탐이 없습니다.":
        "e.g. NVR_VIEWER.exe  ·  leave empty to skip the check\n"
        "Compared by program (process) name, not window handle,\n"
        "so there are no false alarms even if FMVS recreates its windows internally.",
    "담당자 / Teams 알림": "Assignee / Teams notification",
    "담당자 이름": "Assignee name",
    "담당자 이메일(Teams)": "Assignee email (Teams)",
    "개별 Webhook URL": "Per-ROI Webhook URL",
    "개별 Webhook을 비우면 [설정]의 공통 Webhook으로 보냅니다.\n"
    "담당자별로 다른 채팅방에 보내려면 여기에 해당 흐름의 URL을 넣으세요.":
        "If the per-ROI Webhook is empty, the common Webhook in [Settings] is used.\n"
        "To send to a different chat per assignee, enter that flow's URL here.",
    "ROI 평균색 가져오기": "Get ROI average color",
    "위치 '{label}' 값이 숫자가 아닙니다.": "Position '{label}' is not a number.",
    "ROI 폭/높이는 4 이상이어야 합니다.": "ROI width/height must be at least 4.",
    "이름을 입력하세요.": "Enter a name.",
    "'{label}' 값이 올바르지 않습니다. (범위 {lo}~{hi})": "Invalid value for '{label}'. (range {lo}~{hi})",
    "지속 시간/재알림 간격은 숫자로 입력하세요.": "Enter numbers for the duration / re-alert interval.",
    "정지 기준 변화량/정지 확인 횟수는 숫자로 입력하세요.": "Enter numbers for the stop threshold / stop confirmations.",
    "정지 기준 변화량은 0.1~255, 정지 확인 횟수는 1~20 사이여야 합니다.":
        "Stop threshold must be 0.1~255 and stop confirmations 1~20.",
    "개별 {err}": "Per-ROI {err}",
    "🚨 이상": "🚨 Abnormal",
    "✅ 정상": "✅ OK",
    "⏸ 판정 불가": "⏸ Cannot judge",
    "판정: {verdict}": "Judgment: {verdict}",
    "0.5초 간 변화량 {motion} → {state} · 기준 {limit}": "Change over 0.5 s {motion} → {state} · threshold {limit}",
    "움직임 (판정 안 함)": "Moving (not judged)",
    "정지 (판정함)": "Stopped (judged)",
    "대상 프로그램 확인: {process} ✔ (ROI를 가린 창 없음)": "Target program: {process} ✔ (no window covering the ROI)",
    "⚠ 검출 시 건너뜀: {detail}": "⚠ Skipped during detection: {detail}",
    "Windows에서만 지원됩니다.": "Supported on Windows only.",
    "ROI 위치의 프로그램을 확인할 수 없습니다.": "Could not identify the program at the ROI position.",

    # ---- 설정 창 (settings_dialog.py) ----
    "설정": "Settings",
    "검출": "Detection",
    "검사 주기(초, 0.2~60)": "Check interval (s, 0.2~60)",
    "PC 표시 이름(알림에 표시)": "PC display name (shown in notifications)",
    "검출 시 팝업 표시": "Show popup on detection",
    "검출 시 경고음": "Beep on detection",
    "프로그램 시작 시 검출 자동 시작": "Start detection automatically when the program starts",
    "검출 시작 시 이 창 최소화 (창이 ROI를 가리지 않도록)":
        "Minimize this window when detection starts (so it does not cover ROIs)",
    "검출 중 화면에 ROI 위치·상태 테두리 표시 (클릭 통과, 캡처에 안 찍힘)":
        "Show ROI position/status borders on screen during detection (click-through, not captured)",
    "검출 중 화면 모서리에 '동작 중' 배지 표시": "Show 'Running' badge in the screen corner during detection",
    "Teams 알림 (Power Automate Workflows 웹훅)": "Teams notification (Power Automate Workflows webhook)",
    "Teams 알림 사용": "Use Teams notification",
    "공통 Webhook URL": "Common Webhook URL",
    "Teams → 워크플로 → 'Webhook 요청 수신 시 채팅/채널에 게시' 흐름을 만들고\n"
    "생성된 URL을 붙여넣으세요. 자세한 방법은 README 참고.\n"
    "※ URL에 인증 서명이 들어 있으니 외부에 공유하지 마세요.":
        "In Teams → Workflows, create a 'Post to a chat/channel when a webhook request is received' flow\n"
        "and paste the generated URL. See the README for details.\n"
        "※ The URL contains an authentication signature; do not share it externally.",
    "비전 에이전트 (PC 내부에서만 동작)": "Vision agent (runs locally on this PC only)",
    "검출 엔진이 오류로 멈추면 자동 재시작 (시간당 최대 3회)":
        "Auto-restart the detection engine if it stops on an error (max 3 per hour)",
    "동시다발 이상(화면 전체 문제)·연속 불량(설비 점검) 판단을 Teams로 전송":
        "Send simultaneous-abnormality (whole-screen issue) / consecutive-defect (equipment check) judgments to Teams",
    "교대 시각 (근무 리포트 자동 작성, 쉼표 구분)": "Shift change times (auto shift report, comma-separated)",
    "근무 리포트 요약을 Teams로 전송": "Send shift report summary to Teams",
    "예: 08:00,20:00 · 비우면 자동 리포트 안 함 · 리포트는 reports 폴더에 HTML로 저장":
        "e.g. 08:00,20:00 · empty = no auto report · reports are saved as HTML in the reports folder",
    "팝업 · 미니 모니터 · 보관": "Popup · Mini monitor · Retention",
    "자동 (ROI와 덜 겹치는 쪽)": "Auto (side overlapping ROIs less)",
    "오른쪽 하단": "Bottom right",
    "왼쪽 하단": "Bottom left",
    "연속 이상 발생 시 팝업 – 같은 ROI에서 연속 몇 회 NG면 팝업 (1~99)":
        "Popup on consecutive abnormalities – popup after this many NGs in a row on the same ROI (1~99)",
    "검출 시작 시 화면 하단에 ROI 트렌드 미니 모니터 표시":
        "Show ROI trend mini monitor at the bottom of the screen when detection starts",
    "로그·스냅샷·리포트 보관 기간 (일, 최대 {days}일)": "Log/snapshot/report retention (days, max {days})",
    "NG 스냅샷 확대 배율 (1~4배, 원본은 ROI 크기로 따로 저장)":
        "NG snapshot zoom (1~4x, original saved separately at ROI size)",
    "연속 횟수는 NG 판정마다 1씩 오르고, OK 판정이 나오면 0으로 돌아갑니다. "
    "Teams 알림은 이 설정과 무관하게 판정마다 전송됩니다.":
        "The consecutive count increases by 1 on each NG judgment and resets to 0 on an OK judgment. "
        "Teams notifications are sent on every judgment regardless of this setting.",
    "검사 주기는 숫자로 입력하세요.": "Enter a number for the check interval.",
    "검사 주기는 0.2~60초 사이여야 합니다.": "Check interval must be between 0.2 and 60 seconds.",
    "공통 Webhook URL이 비어 있습니다.\n"
    "개별 Webhook이 없는 ROI는 Teams 알림이 가지 않습니다.\n저장할까요?":
        "The common Webhook URL is empty.\n"
        "ROIs without a per-ROI Webhook will not send Teams notifications.\nSave anyway?",
    "교대 시각 형식이 올바르지 않습니다: {value} (예: 08:00)": "Invalid shift time format: {value} (e.g. 08:00)",
    "연속 횟수·보관 기간·확대 배율은 숫자로 입력하세요.": "Enter numbers for consecutive count, retention and zoom.",
    "연속 횟수는 1~99, 보관 기간은 1~{days}일, 확대 배율은 1~4배여야 합니다.":
        "Consecutive count must be 1~99, retention 1~{days} days, and zoom 1~4x.",

    # ---- 샘플 이미지 창 (samples_dialog.py) ----
    "OK (정상품 – 기준)": "OK (good product – reference)",
    "NG (불량품)": "NG (defective product)",
    "무시 (셀 없음·이동 중·가려짐 – 판정하지 않을 화면)": "Ignore (no cell · moving · covered – screens not to judge)",
    "샘플 이미지 – {name}  (ROI {w}×{h})": "Sample images – {name}  (ROI {w}×{h})",
    "현재 화면 또는 파일(과거 NG 사진 등)에서 이미지를 등록합니다. 파일은 ROI 크기에 맞춰 저장됩니다.\n"
    "· OK: 정상 제품 (위치·모양 편차가 있으면 여러 장)   · NG: 불량 제품 (접힘·찍힘·휨 등 유형별로)\n"
    "· 무시: 셀이 없을 때·이동 중·가려진 화면 – 이것과 비슷하면 판정하지 않습니다 (빈 화면 오탐 방지)\n"
    "· 잘못 등록했으면 이미지를 다른 칸으로 끌어 놓거나, 우클릭 → 이동":
        "Register images from the current screen or from files (e.g. past NG photos). Files are resized to the ROI size.\n"
        "· OK: good products (several if position/shape varies)   · NG: defective products (one per type: fold, dent, bend, etc.)\n"
        "· Ignore: no cell, moving or covered screens – similar screens are not judged (prevents empty-screen false alarms)\n"
        "· If registered in the wrong place, drag the image to another section, or right-click → Move",
    "현재 화면 추가": "Add current screen",
    "파일에서 가져오기": "Import from file",
    "모두 삭제": "Delete all",
    "{n}장": "{n} image(s)",
    "등록된 이미지 없음": "No images registered",
    "(열 수 없음)": "(cannot open)",
    "⚠ ROI와 크기 다름\n{name}": "⚠ Size differs from ROI\n{name}",
    "이미지": "Image",
    "{n}장   ⬇ 여기에 놓으면 '{target}'(으)로 이동": "{n} image(s)   ⬇ Drop here to move to '{target}'",
    "→ {target}(으)로 이동": "→ Move to {target}",
    "⚠ OK(정상품) 샘플이 없어 판정하지 않습니다. OK 이미지를 먼저 등록하세요.":
        "⚠ No OK (good product) samples, so nothing is judged. Register OK images first.",
    "샘플로 판정 정확도 자체 검증 중…": "Self-checking judgment accuracy with samples…",
    "자동 계산 OK 허용 거리: {value}": "Auto-calculated OK distance threshold: {value}",
    "  (이 ROI는 수동 값 {value} 사용 중)": "  (this ROI uses manual value {value})",
    "  ← 현재 사용 중": "  ← currently in use",
    "자체 검증 실패: {error}": "Self-check failed: {error}",
    "💡 셀이 없을 때 화면을 '무시'로 1장 이상 등록하면 빈 화면 오탐이 사라집니다.":
        "💡 Register at least one screen without a cell as 'Ignore' to eliminate empty-screen false alarms.",
    "{label} 이미지 선택": "Select {label} images",
    "모든 파일": "All files",
    "비율 확인": "Aspect ratio check",
    "ROI({w}×{h})와 가로세로 비율이 다른 이미지가 있습니다:\n":
        "Some images have a different aspect ratio from the ROI ({w}×{h}):\n",
    "\n\nROI 크기로 늘려서 저장하면 판정이 부정확할 수 있습니다.\n"
    "FMVS 화면에서 ROI 영역만 잘라낸 이미지를 권장합니다. 그래도 등록할까요?":
        "\n\nStretching them to the ROI size may make judgments inaccurate.\n"
        "Images cropped to just the ROI area of the FMVS screen are recommended. Register anyway?",
    "열 수 없는 파일:\n": "Files that could not be opened:\n",
    "{label} 이미지를 모두 삭제할까요?": "Delete all {label} images?",

    # ---- ROI 지정 오버레이 (roi_editor.py) ----
    "드래그: ROI 지정  |  우클릭·Ctrl+Z: 마지막 취소  |  Enter: 완료  |  Esc: 취소":
        "Drag: set ROI  |  Right-click·Ctrl+Z: undo last  |  Enter: done  |  Esc: cancel",
    "ROI 1개 지정 (그리면 바로 적용)": "Set 1 ROI (applied as soon as drawn)",
    "여러 개 지정 가능": "Multiple ROIs allowed",
    "[ROI 지정] {title}": "[Set ROI] {title}",
    "완료": "Done",
    "새 ROI {n}  ({w}×{h})": "New ROI {n}  ({w}×{h})",
}

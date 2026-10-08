"""영어 번역 – 의견 에이전트(advisor)·LLM 연결 (원문 한국어 → 영어)."""

EN = {
    # 의견 패널
    "  활동 · 로그  ": "  Activity · Log  ",
    "  💡 의견  ": "  💡 Advisor  ",
    "  💡 의견 {n}  ": "  💡 Advisor {n}  ",
    "⟳ 다시 분석": "⟳ Re-analyze",
    "🤖 LLM 종합 의견": "🤖 LLM summary",
    "묻기": "Ask",
    "마지막 분석 {when} · 검출 기록·샘플·설정 기반": "Last analysis {when} · based on detection history, samples and settings",
    "규칙 분석 + LLM ({model})": "Rule analysis + LLM ({model})",
    "규칙 분석 · LLM 미연결": "Rule analysis · LLM not connected",
    "✔ 지금은 개선 의견이 없습니다": "✔ No recommendations right now",
    "검출 기록·샘플·설정에서 문제를 찾지 못했습니다. 5분마다 다시 분석합니다.":
        "No issues found in detection history, samples or settings. Re-analyzing every 5 minutes.",
    "🤖 LLM 연결 시 (예시)": "🤖 With an LLM connected (example)",
    "설정 → LLM 연결에서 이 PC 또는 사내 서버의 LLM(Ollama·LM Studio 등)을 켜면 위 같은 종합 의견과 질문 답변을 받을 수 있습니다. 화면·이미지는 보내지 않습니다.":
        "Enable an LLM on this PC or an in-house server (Ollama, LM Studio, etc.) in Settings → LLM connection to get "
        "summaries and answers like the above. Screens and images are never sent.",
    "숨긴 의견 {n}개": "{n} hidden",
    "다시 보기": "Show again",
    "숨기기": "Hide",
    "샘플 열기": "Open samples",
    "ROI 편집": "Edit ROI",
    "설정 열기": "Open settings",
    # gui
    " 외 {n}건": " and {n} more",
    "의견 에이전트: {title}{more} – [💡 의견] 탭에서 확인": "Advisor: {title}{more} – see the [💡 Advisor] tab",
    "의견 분석 오류": "Advisor analysis error",
    "LLM이 연결되어 있지 않아 규칙 분석 결과로 답합니다. (설정 → LLM 연결에서 켜면 자연어로 답합니다)":
        "No LLM is connected, so this answer comes from the rule analysis. "
        "(Enable Settings → LLM connection for natural-language answers)",
    "관련된 개선 의견이 없습니다.": "No related recommendations.",
    "현재 상태를 종합해서 우선순위가 높은 운영 의견을 주세요.":
        "Summarize the current state and give the highest-priority operating recommendations.",
    # advisor 규칙
    "감시할 ROI가 없습니다": "No ROIs to monitor",
    "[＋ ROI 추가]로 FMVS 화면에서 감시할 카메라 영역을 지정하세요.":
        "Use [+ Add ROI] to select the camera areas to monitor on the FMVS screen.",
    "[{name}] OK 샘플이 없어 판정하지 못합니다": "[{name}] No OK samples – cannot judge",
    "정상 제품 화면을 [샘플/기준 이미지]에서 OK로 1장 이상 등록하세요. 위치·밝기 편차가 있으면 3장 이상이 좋습니다.":
        "Register at least one good-product screen as OK in [Samples]. If position or brightness varies, 3 or more is better.",
    "[{name}] OK 샘플 {n}장 – 오탐 위험": "[{name}] Only {n} OK sample(s) – false-alarm risk",
    "정상품도 위치·밝기가 조금씩 달라 OK가 적으면 정상을 NG로 판정하기 쉽습니다. 서로 다른 순간의 OK 화면을 {n}장 이상 등록하세요.":
        "Good products vary slightly in position and brightness, so with few OK samples good parts are easily judged NG. "
        "Register {n} or more OK screens from different moments.",
    "[{name}] 샘플 자체 검증에서 틀린 판정이 있습니다": "[{name}] Sample self-check found wrong judgments",
    "– 잘못 분류된 샘플이 없는지 확인하고(끌어서 다른 칸으로 이동), 헷갈리는 유형의 샘플을 더 등록하세요.":
        "– Check for misclassified samples (drag them to the right section) and add more samples of the confusing type.",
    "[{name}] '무시' 샘플이 없습니다": "[{name}] No 'Ignore' samples",
    "셀이 없을 때·이동 중 화면을 '무시'로 1장 등록하면 빈 화면을 NG로 오인하지 않습니다.":
        "Register one empty/moving screen as 'Ignore' so empty frames are not mistaken for NG.",
    "[{name}] 대상 프로그램 미지정 – 가림 확인 꺼짐": "[{name}] No target program – cover check off",
    "다른 창이 ROI를 덮어도 그대로 판정해 오탐이 날 수 있습니다. ROI 편집에서 대상 프로그램(FMVS 뷰어 실행 파일)을 지정하세요.":
        "If another window covers the ROI it is still judged, which can cause false alarms. "
        "Set the target program (FMVS viewer executable) in Edit ROI.",
    "[{name}] {pct}% 시간 동안 가려져 판정하지 못했습니다": "[{name}] Covered {pct}% of the time – not judged",
    "최근 원인: {detail}. 대시보드·팝업 창을 ROI 밖으로 옮기거나 FMVS 화면을 맨 앞에 두세요.":
        "Latest cause: {detail}. Move the dashboard/popups off the ROI or keep the FMVS screen in front.",
    "가림": "covered",
    "[{name}] 정지를 한 번도 감지하지 못했습니다": "[{name}] Never detected a stop",
    "화면 변화량이 계속 정지 기준({diff})보다 큽니다. 화면 잡음이 큰 카메라라면 ROI 편집에서 정지 기준 값을 올리세요 (현재 상태: {detail}).":
        "Screen change stays above the stop threshold ({diff}). For a noisy camera, raise the stop threshold in Edit ROI "
        "(current: {detail}).",
    "[{name}] 검사 오류가 반복됩니다 ({n}회)": "[{name}] Repeated inspection errors ({n}×)",
    "최근 내용: {detail}. ROI 위치가 화면 밖이거나 샘플 파일이 손상되었을 수 있습니다.":
        "Latest: {detail}. The ROI may be off-screen or a sample file may be damaged.",
    "[{name}] NG 비율 {pct}% ({ng}/{n})": "[{name}] NG rate {pct}% ({ng}/{n})",
    "실제 불량이면 해당 공정 점검이 필요합니다. 오탐이면 팝업의 [OK로 등록(오탐)]으로 알려 주세요 – 다음 판정부터 반영됩니다.":
        "If these are real defects, check the process. If false alarms, use [Register as OK (false alarm)] in the popup – "
        "it applies from the next judgment.",
    "[{name}] 최근 1시간 NG 급증: {last}건 (이전 평균 {avg}건)": "[{name}] NG surge in the last hour: {last} (previous avg {avg})",
    "같은 시간대에 설비 조건(장력·위치·조명) 변화가 있었는지 확인하세요. 스냅샷 폴더의 확대 이미지로 불량 유형을 비교할 수 있습니다.":
        "Check whether equipment conditions (tension, position, lighting) changed at that time. "
        "Compare defect types using the enlarged images in the snapshots folder.",
    "[{name}] 담당자 미지정": "[{name}] No assignee",
    "NG가 발생한 ROI입니다. 담당자와 Teams 이메일을 지정하면 알림이 바로 전달됩니다.":
        "This ROI has NG results. Set an assignee and Teams email so alerts reach them directly.",
    "Teams 알림이 꺼져 있습니다": "Teams alerts are off",
    "NG가 발생하고 있지만 담당자에게 알림이 가지 않습니다. 설정에서 Teams 알림을 켜세요.":
        "NG results are occurring but nobody is notified. Turn on Teams alerts in Settings.",
    "에이전트가 정지 상태입니다": "The agent is stopped",
    "[▶ 에이전트 시작]을 누르면 실시간 판정과 분석을 시작합니다.":
        "Press [▶ Start agent] to start live judgment and analysis.",
    # LLM
    "LLM 서버 주소를 입력하세요": "Enter the LLM server address",
    "보안: 이 PC(localhost) 또는 사내망 주소만 사용할 수 있습니다":
        "Security: only this PC (localhost) or in-house network addresses are allowed",
    "모델 이름을 입력하세요 (예: qwen2.5:7b)": "Enter a model name (e.g. qwen2.5:7b)",
    "LLM 서버 오류 {code}: {msg}": "LLM server error {code}: {msg}",
    "LLM 서버에 연결할 수 없습니다: {msg}": "Cannot connect to the LLM server: {msg}",
    "LLM 서버 응답을 해석할 수 없습니다": "Cannot parse the LLM server response",
    # 설정 창
    "LLM 연결 (선택 · 의견 에이전트 자연어 답변)": "LLM connection (optional · natural-language advisor answers)",
    "LLM 사용 (이 PC 또는 사내 서버만)": "Use LLM (this PC or in-house server only)",
    "서버 주소 (OpenAI 호환)": "Server address (OpenAI-compatible)",
    "모델 이름": "Model name",
    "API 키 (필요할 때만)": "API key (only if required)",
    "연결 테스트": "Test connection",
    "연결 중…": "Connecting…",
    "연결 테스트입니다. 'OK' 한 단어로만 답하세요.": "This is a connection test. Reply with the single word 'OK'.",
    "✔ 연결됨 – 응답: {answer}": "✔ Connected – reply: {answer}",
    "예: Ollama → http://127.0.0.1:11434/v1 · 모델 qwen2.5:7b\nLM Studio → http://127.0.0.1:1234/v1\n보내는 내용: ROI별 판정 통계·의견 목록(텍스트)만. 화면·이미지는 보내지 않습니다.\n외부 인터넷 주소는 보안상 사용할 수 없습니다.":
        "e.g. Ollama → http://127.0.0.1:11434/v1 · model qwen2.5:7b\nLM Studio → http://127.0.0.1:1234/v1\n"
        "Sent: per-ROI judgment statistics and the recommendation list (text) only. Screens and images are never sent.\n"
        "External internet addresses are blocked for security.",
}

"""영어 번역 (원문 한국어 → 영어)."""

EN = {
    # ---- detectors.py: 검출 유형 / 파라미터 / 선택값 ----
    "흑화면 (검은 화면)": "Black screen",
    "어두운 픽셀이 일정 비율 이상이면 이상으로 판단합니다.":
        "Abnormal when the share of dark pixels reaches the set ratio.",
    "밝기 기준 (0~255, 이 값 이하 = 어두움)": "Brightness threshold (0~255, at or below = dark)",
    "어두운 픽셀 비율 (0~1, 이 값 이상이면 이상)": "Dark pixel ratio (0~1, at or above = abnormal)",
    "백화면 (하얀/과노출 화면)": "White screen (white/overexposed)",
    "밝은 픽셀이 일정 비율 이상이면 이상으로 판단합니다.":
        "Abnormal when the share of bright pixels reaches the set ratio.",
    "밝기 기준 (0~255, 이 값 이상 = 밝음)": "Brightness threshold (0~255, at or above = bright)",
    "밝은 픽셀 비율 (0~1, 이 값 이상이면 이상)": "Bright pixel ratio (0~1, at or above = abnormal)",
    "단색 화면 (No Signal / 파란 화면 등)": "Solid-color screen (No Signal / blue screen, etc.)",
    "화면 전체가 거의 한 가지 색이면(밝기 표준편차가 작으면) 이상으로 판단합니다.":
        "Abnormal when the whole area is nearly one color (low brightness standard deviation).",
    "밝기 표준편차 기준 (이 값 이하면 이상)": "Brightness std. dev. threshold (at or below = abnormal)",
    "화면 정지 (영상 멈춤)": "Frozen screen (video stopped)",
    "직전 검사 대비 변화량이 기준 이하로 지속되면 이상으로 판단합니다.\n"
    "ROI에 시계/날짜 표시가 들어가면 항상 변하므로 제외하고 지정하세요.\n"
    "움직임이 없는 장면은 정상인데도 정지로 보일 수 있으니 지속 시간을 길게(60초 이상) 두세요.":
        "Abnormal when the change from the previous check stays at or below the threshold.\n"
        "Exclude clock/date overlays from the ROI, since they always change.\n"
        "Static scenes can look frozen even when OK, so set a long duration (60 s or more).",
    "프레임 변화량 기준 (이 값 이하면 정지)": "Frame change threshold (at or below = frozen)",
    "특정 색상 감지": "Specific color detection",
    "지정한 색과 비슷한 픽셀이 일정 비율 이상이면 이상으로 판단합니다.\n"
    "예: 'No Video' 파란 화면, 빨간 경고 아이콘 등.":
        "Abnormal when pixels similar to the chosen color reach the set ratio.\n"
        "e.g. a 'No Video' blue screen, a red warning icon.",
    "대상 색상 R,G,B": "Target color R,G,B",
    "색상 허용 오차 (0~255)": "Color tolerance (0~255)",
    "해당 색 픽셀 비율 (0~1, 이 값 이상이면 이상)": "Matching color pixel ratio (0~1, at or above = abnormal)",
    "기준 화면과 다름 (화면 구성 변경)": "Differs from reference screen (layout changed)",
    "정상일 때 저장한 기준 이미지와 차이가 기준 이상이면 이상으로 판단합니다.\n"
    "[기준 이미지 저장]으로 정상 화면을 먼저 저장해야 합니다.\n"
    "레이아웃 변경, 카메라 방향 틀어짐 등 감지용입니다.":
        "Abnormal when the difference from the reference image saved while OK reaches the threshold.\n"
        "Save an OK screen first with [Save reference image].\n"
        "Detects layout changes, camera misalignment, etc.",
    "평균 차이 기준 (0~255, 이 값 이상이면 이상)": "Mean difference threshold (0~255, at or above = abnormal)",
    "자동 판단": "Auto",
    "대상(탭)이 배경보다 밝음": "Target (tab) brighter than background",
    "대상(탭)이 배경보다 어두움": "Target (tab) darker than background",
    "형상 검사 (탭 접힘·찍힘·휨)": "Shape inspection (tab fold/dent/bend)",
    "정상 제품 화면을 [기준 이미지 저장]으로 저장해 두면, 대상(탭)의 윤곽을 기준과 겹쳐 비교합니다.\n"
    "접힘·휨·찢어짐·찍힘으로 모양이 달라진 면적이 기준 이상이면 불량으로 판단합니다.\n"
    "· 위치가 조금 어긋나도 자동으로 맞춰 비교합니다 (회전은 소폭만 허용).\n"
    "· OK(정상품) 여러 장, NG(불량품), 무시(제품 없음) 샘플을 등록하면 가장 비슷한 쪽으로 판정합니다.\n"
    "· 제품이 흘러가는 라인이면 '이상 지속 시간'을 0~1초로, 제품 감지 최소 면적을 설정하세요.":
        "Save an OK product screen with [Save reference image]; the target (tab) outline is overlaid on the reference and compared.\n"
        "NG when the area changed by folds, bends, tears or dents reaches the threshold.\n"
        "· Small position offsets are aligned automatically (only slight rotation allowed).\n"
        "· Register several OK samples, NG samples and Ignore (no product) samples to judge by the closest match.\n"
        "· On a moving line, set 'Abnormal duration' to 0~1 s and set the minimum product area.",
    "대상(탭) 밝기": "Target (tab) brightness",
    "형상 차이 기준 (%, 이 값 이상이면 불량)": "Shape difference threshold (%, at or above = NG)",
    "위치 허용 범위 (ROI 크기 대비 %, 상하좌우 이동)": "Position tolerance (% of ROI size, any direction)",
    "경계 허용 오차 (픽셀, 0~3)": "Edge tolerance (pixels, 0~3)",
    "표면 차이 기준 (구김·긁힘, 0 = 사용 안 함)": "Surface difference threshold (wrinkles/scratches, 0 = off)",
    "제품 감지 최소 면적 (기준 대비 %, 이보다 작으면 제품 없음)":
        "Minimum product area (% of reference, below = no product)",
    "OK/NG 이미지 매칭 (분류)": "OK/NG image matching (classification)",
    "ROI별로 등록한 OK·NG·무시 샘플 이미지 중 현재 화면과 가장 비슷한 쪽으로 판정합니다.\n"
    "· NG 샘플과 가장 비슷하면 → 불량\n"
    "· OK 샘플과 비슷해도 'OK 허용 거리'보다 멀면 → 처음 보는 이상으로 보고 불량\n"
    "· 무시 샘플(제품 없음/이동 중 등)과 가장 비슷하면 → 판정 보류\n"
    "[샘플 이미지] 버튼으로 현재 화면이나 파일(NG 사진)에서 샘플을 등록하세요.\n"
    "OK 허용 거리를 0으로 두면 샘플들로 자동 계산합니다. 흐르는 라인은 이상 지속 시간 0초를 권장합니다.":
        "Judges by whichever OK, NG or Ignore sample registered for the ROI is closest to the current screen.\n"
        "· Closest to an NG sample → NG\n"
        "· Close to OK but farther than 'OK distance limit' → unseen abnormality, NG\n"
        "· Closest to an Ignore sample (no product/moving, etc.) → judgment on hold\n"
        "Register samples from the current screen or a file (NG photo) with the [Sample images] button.\n"
        "With OK distance limit 0, it is calculated from the samples. For moving lines, an abnormal duration of 0 s is recommended.",
    "OK 허용 거리 (0 = 샘플로 자동 계산)": "OK distance limit (0 = auto from samples)",
    "OK (정상)": "OK (good)",
    "NG (불량)": "NG (defect)",
    "무시 (제품 없음·이동 중)": "Ignore (no product/moving)",

    # ---- detectors.py: 판정 상세 ----
    "알 수 없는 검출 유형: {kind}": "Unknown detector type: {kind}",
    "캡처 영역이 비어 있음": "Capture area is empty",
    "어두운 픽셀 {pct}% (기준 ≥{ref}%)": "Dark pixels {pct}% (limit ≥{ref}%)",
    "밝은 픽셀 {pct}% (기준 ≥{ref}%)": "Bright pixels {pct}% (limit ≥{ref}%)",
    "밝기 표준편차 {std} (기준 ≤{ref})": "Brightness std. dev. {std} (limit ≤{ref})",
    "비교할 이전 프레임 수집 중": "Collecting previous frame for comparison",
    "프레임 변화량 {diff} (기준 ≤{ref})": "Frame change {diff} (limit ≤{ref})",
    "색상({r},{g},{b}) 픽셀 {pct}% (기준 ≥{ref}%)": "Color({r},{g},{b}) pixels {pct}% (limit ≥{ref}%)",
    "기준(OK) 이미지 없음 – [샘플/기준 이미지]에서 정상품을 등록하세요":
        "No reference (OK) image – register an OK product in [Sample/Reference images]",
    "ROI 크기가 바뀜 – 샘플/기준 이미지를 다시 등록하세요":
        "ROI size changed – register sample/reference images again",
    "제품 없음 – 무시 샘플과 가장 비슷 (판정 보류 · 무시 {skip} / OK {ok})":
        "No product – closest to Ignore sample (on hold · Ignore {skip} / OK {ok})",
    "NG 샘플과 가장 비슷 (NG 차이 {ng} < OK 차이 {ok})": "Closest to NG sample (NG diff {ng} < OK diff {ok})",
    " · 기준 {n}장 중 최소": " · min of {n} references",
    "기준 대비 차이 {diff} (기준 ≥{ref})": "Difference from reference {diff} (limit ≥{ref})",
    "기준 이미지에서 대상 형상을 구분할 수 없음 – ROI를 탭 주변으로 좁히거나 '대상(탭) 밝기'를 지정하세요":
        "Cannot separate the target shape in the reference image – narrow the ROI around the tab or set 'Target (tab) brightness'",
    "제품 없음 (대상 면적 {pct}% < {min}%) – 판정 보류": "No product (target area {pct}% < {min}%) – on hold",
    "NG 샘플과 형상 일치 (NG 차이 {ng}% < OK 차이 {ok}%)": "Shape matches NG sample (NG diff {ng}% < OK diff {ok}%)",
    "형상 차이 {pct}% (기준 ≥{ref}%)": "Shape difference {pct}% (limit ≥{ref}%)",
    "표면 차이 {tex} (기준 ≥{ref})": "Surface difference {tex} (limit ≥{ref})",
    "위치 보정 {dx},{dy}px": "Position offset {dx},{dy}px",
    "기준 {n}장 중 최근접": "closest of {n} references",
    "OK 샘플이 1장이라 자동 기준이 부정확합니다 – OK 샘플을 3장 이상 등록하세요":
        "Only 1 OK sample, so the auto threshold is inaccurate – register 3 or more OK samples",
    "OK 편차 최대 {ok_max} – NG 샘플을 등록하면 더 정확해집니다":
        "OK spread max {ok_max} – registering NG samples improves accuracy",
    "분리 양호: OK 편차 최대 {ok_max} < NG 거리 최소 {ng_min}":
        "Good separation: OK spread max {ok_max} < NG distance min {ng_min}",
    "⚠ OK/NG가 겹침: OK 편차 최대 {ok_max} ≥ NG 거리 최소 {ng_min} – ROI를 대상에 맞게 좁히거나 샘플을 추가하세요":
        "⚠ OK/NG overlap: OK spread max {ok_max} ≥ NG distance min {ng_min} – narrow the ROI to the target or add samples",
    "OK 샘플 이미지 없음 – [샘플 이미지]에서 OK 이미지를 등록하세요":
        "No OK sample images – register OK images in [Sample images]",
    "ROI 크기가 바뀜 – 샘플 이미지를 다시 등록하세요": "ROI size changed – register sample images again",
    " · 무시 {d}": " · Ignore {d}",
    "자동": "auto",
    "수동": "manual",
    "무시 샘플과 가장 비슷 – 판정 보류 ({dist})": "Closest to Ignore sample – on hold ({dist})",
    "NG 샘플과 가장 비슷 ({dist})": "Closest to NG sample ({dist})",
    "OK와 다름: 거리 {d} > 허용 {th}({auto}) ({dist})": "Differs from OK: distance {d} > limit {th}({auto}) ({dist})",
    "OK와 일치: 거리 {d} ≤ 허용 {th}({auto}) ({dist})": "Matches OK: distance {d} ≤ limit {th}({auto}) ({dist})",
    "오탐": "false alarms",
    "놓침": "missed",
    "무시": "Ignore",
    "판정함": "judged",
    "{name} {ok}/{n} 맞춤": "{name} {ok}/{n} correct",
    "자체 검증: OK 샘플을 2장 이상 등록하면 판정 정확도를 스스로 검증합니다":
        "Self-check: register 2 or more OK samples to verify judgment accuracy automatically",
    "✔ 자체 검증 통과: ": "✔ Self-check passed: ",
    "⚠ 자체 검증: ": "⚠ Self-check: ",
    " – 샘플을 추가하거나 기준값을 조정하세요": " – add samples or adjust the threshold",

    # ---- occlusion.py ----
    "FMVS 창(대시보드·팝업)": "FMVS window (dashboard/popup)",
    " · ROI 위치: {name}": " · at ROI: {name}",
    "대상 프로그램({expected}) 화면이 ROI 위치에 없음": "Target program ({expected}) not shown at ROI position",
    "ROI 일부가 대상 프로그램 창 밖 ({pct}%)": "Part of ROI outside target program window ({pct}%)",
    " 외": " and others",
    " – 창을 ROI 밖으로 옮기세요": " – move the window off the ROI",
    "다른 창이 ROI를 가림: {who} {pct}%": "Another window covers the ROI: {who} {pct}%",

    # ---- notifier.py ----
    "{s}초": "{s}s",
    "{m}분 {s}초": "{m}m {s}s",
    "{h}시간 {m}분": "{h}h {m}m",
    "🚨 FMVS 화면 이상 감지": "🚨 FMVS screen abnormality detected",
    "🚨 FMVS 화면 이상 지속 (재알림)": "🚨 FMVS screen abnormality continues (reminder)",
    "✅ FMVS 화면 정상 복구": "✅ FMVS screen recovered",
    "🔔 FMVS 검출기 테스트 알림": "🔔 FMVS detector test notification",
    "미지정": "Unassigned",
    "[{roi}] 화면이 정상으로 돌아왔습니다.": "[{roi}] The screen is back to OK.",
    "Teams 알림 연결 테스트입니다. 이 메시지가 보이면 설정이 완료된 것입니다.":
        "This is a Teams notification connection test. If you see this message, setup is complete.",
    "[{roi}] 화면에서 '{detector}' 이상이 감지되었습니다. 확인 부탁드립니다.":
        "'{detector}' abnormality detected on [{roi}]. Please check.",
    "검출 유형": "Detector type",
    "측정값": "Measurement",
    "지속 시간": "Duration",
    "담당자": "Assignee",
    "시각": "Time",
    "🧠 FMVS 비전 에이전트 – {title}": "🧠 FMVS Vision Agent – {title}",
    "Webhook URL이 비어 있습니다.": "Webhook URL is empty.",
    "Webhook URL은 https:// 로 시작해야 합니다.": "Webhook URL must start with https://.",
    "Teams 전송 건너뜀 ({label}): {err}": "Teams send skipped ({label}): {err}",
    "Teams 전송 완료: {label}": "Teams sent: {label}",
    "Teams 전송 실패: {label} – {error}": "Teams send failed: {label} – {error}",

    # ---- worker.py ----
    "사용자 중지": "Stopped by user",
    "오류로 중지됨: {e}": "Stopped due to error: {e}",
    "사용 안 함": "Disabled",
    "[{roi}] 검사 오류: {msg}": "[{roi}] Inspection error: {msg}",
    "화면 잠금 상태 – 판정 안 함": "Screen locked – not judging",
    "다른 화면: {proc}": "Other screen: {proc}",
    "확인 불가(화면 잠금 등)": "unknown (screen locked, etc.)",
    " · {elapsed}/{total}초": " · {elapsed}/{total}s",
    " · {dur} 지속": " · lasted {dur}",
    "움직임 – 정지 대기 (변화량 {amount} > {limit})": "Moving – waiting for stop (change {amount} > {limit})",
    "정지 확인 중 {n}/{total} (변화량 {motion})": "Confirming stop {n}/{total} (change {motion})",
    "[정지 판정 {time}] ": "[Inspected at stop {time}] ",
    "이상 감지": "Abnormal detected",
    "재알림": "Reminder",
    "복구": "Recovered",

    # ---- config.py ----
    "새 ROI": "New ROI",

    # ---- main.py ----
    "이미 실행 중입니다.\n작업 표시줄에서 기존 창을 확인하세요.":
        "Already running.\nCheck the existing window on the taskbar.",
}

"""Teams 알림 (Power Automate Workflows 웹훅).

Teams 앱 화면을 조작하는 방식은 업데이트·화면 잠금·포커스 변경 시 조용히 실패하므로,
HTTP POST 한 번으로 끝나는 웹훅 방식을 사용한다. 전송은 백그라운드 스레드에서
순서대로 처리하며 실패 시 재시도한다."""
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

log = logging.getLogger(__name__)

RETRY_DELAYS = (2, 5, 15)
TIMEOUT_SEC = 10


def _card(title: str, color: str, facts, text: str) -> dict:
    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "contentUrl": None,
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": [
                {"type": "TextBlock", "text": title, "size": "Large", "weight": "Bolder",
                 "color": color, "wrap": True},
                {"type": "TextBlock", "text": text, "wrap": True},
                {"type": "FactSet", "facts": [{"title": k, "value": v} for k, v in facts]},
            ],
        },
    }


def fmt_duration(sec: Optional[float]) -> str:
    if sec is None:
        return "-"
    sec = int(sec)
    if sec < 60:
        return f"{sec}초"
    if sec < 3600:
        return f"{sec // 60}분 {sec % 60}초"
    return f"{sec // 3600}시간 {sec % 3600 // 60}분"


def build_payload(kind: str, *, roi_name: str, detector_label: str, detail: str,
                  assignee: str, assignee_email: str, pc_label: str, when: str,
                  elapsed_sec: Optional[float] = None) -> dict:
    """kind: 'alert' | 'repeat' | 'recover' | 'test'.

    상위 필드(assignee_email 등)는 사용자 지정 흐름에서 담당자별 개인 채팅 전송에 쓰고,
    attachments(적응형 카드)는 Teams 기본 템플릿 'Webhook 경고를 채팅/채널에 보내기'가 그대로 게시한다."""
    titles = {
        "alert": ("🚨 FMVS 화면 이상 감지", "Attention"),
        "repeat": ("🚨 FMVS 화면 이상 지속 (재알림)", "Attention"),
        "recover": ("✅ FMVS 화면 정상 복구", "Good"),
        "test": ("🔔 FMVS 검출기 테스트 알림", "Accent"),
    }
    title, color = titles.get(kind, titles["alert"])
    who = assignee or "미지정"
    if assignee_email:
        who = f"{who} ({assignee_email})"
    if kind == "recover":
        text = f"[{roi_name}] 화면이 정상으로 돌아왔습니다."
    elif kind == "test":
        text = "Teams 알림 연결 테스트입니다. 이 메시지가 보이면 설정이 완료된 것입니다."
    else:
        text = f"[{roi_name}] 화면에서 '{detector_label}' 이상이 감지되었습니다. 확인 부탁드립니다."
    facts = [
        ("ROI", roi_name),
        ("검출 유형", detector_label),
        ("측정값", detail or "-"),
        ("지속 시간", fmt_duration(elapsed_sec)),
        ("담당자", who),
        ("PC", pc_label),
        ("시각", when),
    ]
    return {
        "event": kind,
        "title": title,
        "message": text,
        "roi_name": roi_name,
        "detector": detector_label,
        "detail": detail,
        "assignee": assignee,
        "assignee_email": assignee_email,
        "pc": pc_label,
        "time": when,
        "elapsed_sec": None if elapsed_sec is None else int(elapsed_sec),
        "type": "message",
        "attachments": [_card(title, color, facts, text)],
    }


def build_agent_payload(title: str, message: str, *, pc_label: str, when: str) -> dict:
    """에이전트 판단(동시다발 이상·연속 불량·반복 장애)과 근무 리포트 요약용 메시지."""
    full_title = f"🧠 FMVS 비전 에이전트 – {title}"
    facts = [("PC", pc_label), ("시각", when)]
    return {
        "event": "agent",
        "title": full_title,
        "message": message,
        "roi_name": "",
        "detector": "",
        "detail": message,
        "assignee": "",
        "assignee_email": "",
        "pc": pc_label,
        "time": when,
        "elapsed_sec": None,
        "type": "message",
        "attachments": [_card(full_title, "Warning", facts, message)],
    }


def post_json(url: str, payload: dict, timeout: float = TIMEOUT_SEC) -> int:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def validate_url(url: str) -> Optional[str]:
    """문제가 있으면 오류 메시지, 정상이면 None."""
    url = (url or "").strip()
    if not url:
        return "Webhook URL이 비어 있습니다."
    if not url.lower().startswith("https://"):
        return "Webhook URL은 https:// 로 시작해야 합니다."
    return None


class TeamsNotifier:
    def __init__(self, report: Callable[[str, str], None]):
        """report(level, message): GUI 로그 창으로 결과를 전달하는 콜백 (스레드 안전해야 함)."""
        self._report = report
        self._queue: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="TeamsNotifier", daemon=True)
        self._thread.start()

    def send(self, url: str, payload: dict, label: str) -> None:
        err = validate_url(url)
        if err:
            self._report("warning", f"Teams 전송 건너뜀 ({label}): {err}")
            return
        self._queue.put((url.strip(), payload, label))

    def _run(self):
        while True:
            url, payload, label = self._queue.get()
            try:
                self._deliver(url, payload, label)
            except Exception:
                log.exception("Teams 전송 처리 중 예외")

    def _deliver(self, url, payload, label):
        last_error = ""
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                status = post_json(url, payload)
                if 200 <= status < 300:
                    self._report("info", f"Teams 전송 완료: {label}")
                    return
                last_error = f"HTTP {status}"
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code} {e.reason}"
                if 400 <= e.code < 500 and e.code != 429:
                    break  # URL/흐름 설정 오류는 재시도해도 실패
            except Exception as e:
                last_error = str(e) or e.__class__.__name__
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
        self._report("error", f"Teams 전송 실패: {label} – {last_error}")

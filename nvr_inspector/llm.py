"""로컬/사내 LLM 연결 (선택 기능 – 기본 꺼짐).

OpenAI 호환 Chat Completions API(POST {주소}/chat/completions)를 쓰는 서버에 연결한다.
Ollama(http://127.0.0.1:11434/v1), LM Studio(http://127.0.0.1:1234/v1), vLLM, llama.cpp server 등이 지원한다.
보안을 위해 이 PC(localhost) 또는 사내망 주소(10.x, 172.16~31.x, 192.168.x)만 허용하고,
보내는 내용은 텍스트 분석 자료뿐이다 (화면·이미지는 보내지 않음). 추가 패키지 없이 표준 라이브러리만 쓴다."""
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from i18n import language, tr

DEFAULT_URL = "http://127.0.0.1:11434/v1"
TIMEOUT = 90.0


class LLMError(Exception):
    pass


def is_local_url(url: str) -> bool:
    """이 PC 또는 사내망(사설 IP) 주소인지. 호스트 이름은 IP로 풀어서 확인한다."""
    try:
        parsed = urlparse(url.strip())
        host = parsed.hostname
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not host:
        return False
    if host == "localhost":
        return True
    try:
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, None)]
        except (socket.gaierror, UnicodeError, ValueError):
            return False
    return bool(addrs) and all(a.is_loopback or a.is_private for a in addrs)


_THINK = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)


def strip_thinking(text: str) -> str:
    """추론형 모델(Qwen3·DeepSeek-R1 등)이 붙이는 <think>…</think> 생각 과정을 빼고 답만 남긴다."""
    return _THINK.sub("", text).strip()


def system_prompt() -> str:
    if language() == "en":
        return ("You are the quality-monitoring advisor inside FMVS Vision Agent, a program that watches many "
                "production-line camera views (battery cell tabs etc.) and judges OK/NG per ROI. "
                "Use ONLY the data provided. Give concise, prioritized, practical recommendations "
                "(at most 5 bullets), say which ROI each one is about, and say when the data is insufficient. "
                "Never invent numbers.")
    return ("당신은 FMVS Vision Agent의 품질 관제 의견 에이전트입니다. 이 프로그램은 생산 라인 카메라 화면(배터리 셀 탭 등)을 "  # i18n: skip
            "ROI별로 감시해 OK/NG를 판정합니다. 주어진 자료만 근거로, 우선순위가 높은 실행 가능한 의견을 "  # i18n: skip
            "최대 5개 항목으로 간결하게 한국어로 답하세요. 각 항목이 어느 ROI에 관한 것인지 밝히고, "  # i18n: skip
            "자료가 부족하면 부족하다고 말하세요. 숫자를 지어내지 마세요.")  # i18n: skip


def ng_system_prompt() -> str:
    """NG 1건 자동 분석용 지시문."""
    if language() == "en":
        return ("You analyze a single NG (defect) event from FMVS Vision Agent, which watches battery-cell production "
                "camera views. Using ONLY the given data (and the image if attached), answer in this exact format, "
                "each item at most 2 short lines:\n1) Symptom\n2) Likely causes (most likely first)\n"
                "3) What to check / do now\n4) False-alarm possibility\nNever invent numbers.")
    return ("당신은 배터리 셀 생산 라인 카메라 화면을 감시하는 FMVS Vision Agent의 NG 분석 담당입니다. "  # i18n: skip
            "NG 1건에 대해 주어진 자료(이미지가 있으면 이미지 포함)만 근거로 아래 형식 그대로, 항목당 2줄 이내 한국어로 답하세요.\n"  # i18n: skip
            "1) 현상\n2) 추정 원인 (가능성 높은 순)\n3) 지금 확인·조치할 것\n4) 오탐 가능성\n"  # i18n: skip
            "숫자를 지어내지 마세요.")  # i18n: skip


def jpeg_bytes(path: str, max_side: int = 768) -> Optional[bytes]:
    """스냅샷 파일 → LLM 전송용 JPEG (긴 변 max_side 이하)."""
    try:
        import io
        from PIL import Image
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            return buf.getvalue()
    except Exception:
        return None


class LocalLLM:
    def __init__(self, url: str, model: str, api_key: str = "", timeout: float = TIMEOUT):
        self.url = url.strip().rstrip("/")
        self.model = model.strip()
        self.api_key = api_key.strip()
        self.timeout = timeout

    def check(self) -> Optional[str]:
        """설정 오류 메시지, 문제없으면 None."""
        if not self.url:
            return tr("LLM 서버 주소를 입력하세요")
        if not is_local_url(self.url):
            return tr("보안: 이 PC(localhost) 또는 사내망 주소만 사용할 수 있습니다")
        if not self.model:
            return tr("모델 이름을 입력하세요 (예: qwen3:4b-instruct)")
        return None

    def chat(self, user: str, system: Optional[str] = None, image_jpeg: Optional[bytes] = None) -> str:
        """image_jpeg: 함께 보낼 이미지 (비전 모델용, OpenAI 호환 image_url 형식)."""
        error = self.check()
        if error:
            raise LLMError(error)
        content = user
        if image_jpeg:
            import base64
            content = [{"type": "text", "text": user},
                       {"type": "image_url", "image_url": {
                           "url": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")}}]
        body = {"model": self.model, "temperature": 0.2, "stream": False,
                "messages": [{"role": "system", "content": system or system_prompt()},
                             {"role": "user", "content": content}]}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        # 프록시 설정을 무시하고 사내/로컬 서버에 직접 연결 (자료가 외부 프록시를 거치지 않도록)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise LLMError(tr("LLM 서버 오류 {code}: {msg}", code=e.code, msg=e.reason))
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            raise LLMError(tr("LLM 서버에 연결할 수 없습니다: {msg}", msg=getattr(e, "reason", e)))
        except ValueError:
            raise LLMError(tr("LLM 서버 응답을 해석할 수 없습니다"))
        try:
            return strip_thinking(str(data["choices"][0]["message"]["content"]))
        except (KeyError, IndexError, TypeError):
            raise LLMError(tr("LLM 서버 응답을 해석할 수 없습니다"))


def from_config(cfg) -> Optional[LocalLLM]:
    """설정에서 LLM 연결 (꺼져 있으면 None)."""
    if not getattr(cfg, "llm_enabled", False):
        return None
    return LocalLLM(cfg.llm_url, cfg.llm_model, getattr(cfg, "llm_api_key", ""))


EXAMPLE_KO = ("예시 – LLM을 연결하면 이렇게 답합니다:\n"  # i18n: skip
              "1. [2라인 와인딩] 최근 3시간 NG가 평소의 3배입니다. 스냅샷 대부분이 탭 상단 접힘이라 "  # i18n: skip
              "와인딩 장력·가이드 위치 점검을 우선 권합니다.\n"  # i18n: skip
              "2. [1라인 탭 B] OK 샘플이 2장뿐이고 거리값이 허용치에 가깝습니다. 조명 변화가 있는 시간대의 OK 화면을 "  # i18n: skip
              "2~3장 더 등록하면 오탐이 줄어듭니다.\n"  # i18n: skip
              "3. [3라인 탭 A] 35% 시간 동안 대시보드 창에 가려졌습니다. 대시보드를 보조 모니터로 옮기세요.")  # i18n: skip
EXAMPLE_EN = ("Example – with an LLM connected, answers look like this:\n"
              "1. [Line 2 winding] NG in the last 3 hours is 3× normal. Most snapshots show a folded tab top, "
              "so check winding tension and guide position first.\n"
              "2. [Line 1 tab B] Only 2 OK samples and distances are close to the limit. Register 2–3 more OK "
              "screens from times with different lighting to cut false alarms.\n"
              "3. [Line 3 tab A] Covered by the dashboard 35% of the time. Move the dashboard to another monitor.")


def example_answer() -> str:
    return EXAMPLE_EN if language() == "en" else EXAMPLE_KO

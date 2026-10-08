"""화면 언어 (한국어/영어).

화면에 보이는 문자열은 한국어 원문을 키로 tr()에 넘긴다. 영어 모드면 lang/ 사전에서 찾아 바꾸고,
사전에 없으면 원문을 그대로 쓴다. 값이 들어가는 문장은 {이름} 자리표시자를 쓴 원문 + 키워드 인자:
    tr("ROI {n}개 감시 중", n=3)  →  "ROI 3개 감시 중" / "Monitoring 3 ROIs"
모듈 상수(상태 이름 등)는 import 시점이 아니라 화면에 표시할 때 tr()로 감싼다 (실행 중 언어 전환)."""
from typing import Dict

LANGUAGES = {"ko": "한국어", "en": "English"}
_lang = "ko"
_en: Dict[str, str] = {}


def _load() -> Dict[str, str]:
    from lang import en_agent, en_dialogs, en_engine, en_gui
    table: Dict[str, str] = {}
    for mod in (en_engine, en_agent, en_gui, en_dialogs):
        table.update(mod.EN)
    return table


def set_language(lang: str) -> None:
    global _lang, _en
    _lang = lang if lang in LANGUAGES else "ko"
    if _lang == "en" and not _en:
        _en = _load()


def language() -> str:
    return _lang


def tr(text: str, **values) -> str:
    out = _en.get(text, text) if _lang == "en" else text
    if values:
        try:
            return out.format(**values)
        except (KeyError, IndexError, ValueError):
            return text.format(**values)
    return out

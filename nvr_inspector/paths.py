"""실행 위치 기준 경로. EXE로 배포해도 설정/로그가 EXE 옆에 생성되도록 한다."""
import glob
import os
import re
import sys


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = app_dir()
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
REF_DIR = os.path.join(BASE_DIR, "refs")
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
REPORT_DIR = os.path.join(BASE_DIR, "reports")


def ensure_dirs() -> None:
    for d in (LOG_DIR, REF_DIR, SNAPSHOT_DIR, REPORT_DIR):
        os.makedirs(d, exist_ok=True)


# 샘플/기준 이미지 파일 이름 규칙 (OK는 기존 기준 이미지와 호환)
#   OK  : {id}.png, {id}_2.png, {id}_3.png …
#   NG  : {id}_ng_1.png, {id}_ng_2.png …
#   무시: {id}_skip_1.png …
_CLASS_PATTERN = {"ok": r"_(\d+)", "ng": r"_ng_(\d+)", "skip": r"_skip_(\d+)"}


def reference_path(roi_id: str) -> str:
    return os.path.join(REF_DIR, f"{roi_id}.png")


def reference_paths(roi_id: str, cls: str = "ok") -> list:
    """ROI의 클래스별 샘플 이미지 경로 (번호 순)."""
    found = []
    if cls == "ok" and os.path.exists(reference_path(roi_id)):
        found.append((1, reference_path(roi_id)))
    pattern = re.escape(roi_id) + _CLASS_PATTERN[cls] + r"\.png"
    for path in glob.glob(os.path.join(REF_DIR, f"{roi_id}_*.png")):
        m = re.fullmatch(pattern, os.path.basename(path))
        if m:
            found.append((int(m.group(1)), path))
    return [path for _n, path in sorted(found)]


def new_reference_path(roi_id: str, cls: str = "ok") -> str:
    """샘플 이미지를 추가할 다음 파일 경로."""
    if cls == "ok":
        if not reference_paths(roi_id, "ok"):
            return reference_path(roi_id)
        n, fmt = 2, f"{roi_id}_{{}}.png"
    else:
        n, fmt = 1, f"{roi_id}_{cls}_{{}}.png"
    while os.path.exists(os.path.join(REF_DIR, fmt.format(n))):
        n += 1
    return os.path.join(REF_DIR, fmt.format(n))


def delete_references(roi_id: str, cls: str = None) -> None:
    """cls=None이면 모든 클래스 삭제."""
    for c in ([cls] if cls else list(_CLASS_PATTERN)):
        for path in reference_paths(roi_id, c):
            try:
                os.remove(path)
            except OSError:
                pass

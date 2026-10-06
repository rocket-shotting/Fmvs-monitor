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


def ensure_dirs() -> None:
    for d in (LOG_DIR, REF_DIR, SNAPSHOT_DIR):
        os.makedirs(d, exist_ok=True)


def reference_path(roi_id: str) -> str:
    return os.path.join(REF_DIR, f"{roi_id}.png")


def reference_paths(roi_id: str) -> list:
    """ROI의 기준 이미지 전체 ({id}.png, {id}_2.png, {id}_3.png …)."""
    found = []
    first = reference_path(roi_id)
    if os.path.exists(first):
        found.append((1, first))
    for path in glob.glob(os.path.join(REF_DIR, f"{roi_id}_*.png")):
        m = re.fullmatch(re.escape(roi_id) + r"_(\d+)\.png", os.path.basename(path))
        if m:
            found.append((int(m.group(1)), path))
    return [path for _n, path in sorted(found)]


def new_reference_path(roi_id: str) -> str:
    """기준 이미지를 추가할 다음 파일 경로."""
    existing = reference_paths(roi_id)
    if not existing:
        return reference_path(roi_id)
    n = 2
    while os.path.exists(os.path.join(REF_DIR, f"{roi_id}_{n}.png")):
        n += 1
    return os.path.join(REF_DIR, f"{roi_id}_{n}.png")


def delete_references(roi_id: str) -> None:
    for path in reference_paths(roi_id):
        try:
            os.remove(path)
        except OSError:
            pass

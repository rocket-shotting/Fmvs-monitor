"""실행 위치 기준 경로. EXE로 배포해도 설정/로그가 EXE 옆에 생성되도록 한다."""
import os
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

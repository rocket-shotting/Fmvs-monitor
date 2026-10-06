"""NVR 화면 이상 검출기 진입점."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# PyInstaller/직접 실행 모두 같은 폴더의 모듈을 import 하도록
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402
import winutil  # noqa: E402


def setup_logging() -> None:
    paths.ensure_dirs()
    handler = RotatingFileHandler(os.path.join(paths.LOG_DIR, "nvr_inspector.log"),
                                  maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    def excepthook(exc_type, exc, tb):
        logging.getLogger("main").critical("처리되지 않은 예외", exc_info=(exc_type, exc, tb))
    sys.excepthook = excepthook


def main() -> int:
    winutil.enable_dpi_awareness()   # Tk 창 생성 전에 호출해야 좌표가 정확함
    setup_logging()
    if not winutil.acquire_single_instance():
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showwarning("NVR 화면 이상 검출기", "이미 실행 중입니다.\n작업 표시줄에서 기존 창을 확인하세요.")
        r.destroy()
        return 1
    logging.getLogger("main").info("프로그램 시작 (경로: %s)", paths.BASE_DIR)
    from gui import App
    App().run()
    logging.getLogger("main").info("프로그램 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())

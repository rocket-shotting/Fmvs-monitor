"""Windows CI용 GUI 스모크 테스트: 모든 창을 실제로 만들고 주요 동작을 호출한 뒤 닫는다.
(tkinter가 없는 환경에서는 실행하지 않음 – unittest discover 대상 아님)"""
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "nvr_inspector"))

import paths  # noqa: E402

TMP = tempfile.mkdtemp()
paths.REF_DIR = os.path.join(TMP, "refs")
paths.SNAPSHOT_DIR = os.path.join(TMP, "snapshots")
paths.LOG_DIR = os.path.join(TMP, "logs")
paths.ensure_dirs()

import config  # noqa: E402
import detectors  # noqa: E402
import worker  # noqa: E402

config.load = lambda path=None: config.AppConfig()     # 실제 settings.json 건드리지 않음
config.save = lambda cfg, path=None: None

import gui  # noqa: E402
import roi_dialog  # noqa: E402
import samples_dialog  # noqa: E402
import settings_dialog  # noqa: E402


def main():
    app = gui.App()
    root = app.root
    root.update()

    roi = config.ROI(name="스모크", x=0, y=0, w=160, h=120, detector="match")
    app.cfg.rois.append(roi)
    rgb = np.zeros((120, 160, 3), dtype=np.uint8)
    rgb[20:90, 60:90] = 200
    worker.save_png(rgb, paths.new_reference_path(roi.id, "ok"))
    worker.save_png(rgb, paths.new_reference_path(roi.id, "ok"))
    app._refresh_tree()

    # ROI 설정 창: 모든 검출 유형으로 바꿔 보고 값 수집
    dlg = roi_dialog.RoiDialog(root, roi, "스모크")
    for kind in detectors.DETECTOR_ORDER:
        dlg.v_kind.set(detectors.DETECTORS[kind]["label"])
        dlg._on_kind_changed()
        collected = dlg._collect()
        assert collected.detector == kind, (collected.detector, kind)
    dlg._show_preview(detectors.overlay_defects(rgb, np.ones((120, 160), dtype=bool)))
    root.update()
    dlg.top.destroy()

    # 샘플 이미지 창 (매칭 / 형상)
    sd = samples_dialog.SamplesDialog(root, roi)
    root.update()
    assert "2장" in sd.sections["ok"]["count"].cget("text")
    sd.top.destroy()
    shape_roi = config.ROI(name="형상", w=160, h=120, detector="shape")
    sd = samples_dialog.SamplesDialog(root, shape_roi)
    root.update()
    sd.top.destroy()

    # 설정 창
    st = settings_dialog.SettingsDialog(root, app.cfg)
    root.update()
    st.top.destroy()

    # 경보 팝업 + 'NG로 등록' 버튼
    raw = os.path.join(paths.SNAPSHOT_DIR, "raw.png")
    worker.save_png(rgb, raw)
    info = {"kind": "alert", "roi_id": roi.id, "roi_name": roi.name, "detector": roi.detector_label(),
            "detail": "테스트", "elapsed": 3, "assignee": "홍길동", "assignee_email": "", "time": "now",
            "snapshot": raw, "raw_snapshot": raw, "roi_detector": "match"}
    app.alerts.alert(info)
    root.update()
    popup = app.alerts.popups[roi.id]
    popup._register("ng")
    assert popup.ng_btn.cget("text") == "등록됨 ✔", popup.ng_btn.cget("text")
    assert len(paths.reference_paths(roi.id, "ng")) == 1
    app.alerts.recover(dict(info, kind="recover"))
    root.update()
    app.alerts.close_all()

    # 상태 이벤트 처리 + 로그
    app.monitor = object.__new__(worker.Monitor)   # 실행 중인 것처럼 상태 표시만 확인
    app.events.put(("status", roi.id, "alarm", "테스트 상세"))
    app.events.put(("log", "info", "로그 테스트"))
    app._poll_events()
    assert app.tree.set(roi.id, "state") == gui.STATE_TEXT["alarm"]
    app.monitor = None

    root.destroy()
    print("GUI smoke test OK")


if __name__ == "__main__":
    main()

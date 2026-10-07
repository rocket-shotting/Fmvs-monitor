"""Windows CI용 GUI 스모크 테스트: 모든 창을 실제로 만들고 주요 동작을 호출한 뒤 닫는다.
(tkinter가 없는 환경에서는 실행하지 않음 – unittest discover 대상 아님)"""
import os
import sys
import tempfile

import numpy as np

if hasattr(sys.stdout, "reconfigure"):          # Windows 콘솔(cp1252)에서도 한글 출력
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

import alert  # noqa: E402
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
    dlg.v_kind.set(detectors.DETECTORS["match"]["label"])
    dlg.v_duration.set("5")
    dlg._on_kind_changed()
    assert dlg.v_still.get() is True                    # 매칭 유형 선택 시 '정지 시에만 판정' 자동 켜짐
    dlg.v_still_diff.set("2.5")
    collected = dlg._collect()
    assert collected.still_only and collected.still_diff == 2.5
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
    assert set(sd.sections) == {"ok", "ng", "skip"}, "형상 검사에서도 OK/NG/무시 등록 가능해야 함"
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
    assert popup.reg_buttons["ng"].cget("text") == "등록됨 ✔", popup.reg_buttons["ng"].cget("text")
    assert len(paths.reference_paths(roi.id, "ng")) == 1
    popup._register("skip")
    assert len(paths.reference_paths(roi.id, "skip")) == 1
    assert popup.when_label.cget("text") == "now"            # 탐지 시각 표시
    app.alerts.alert(dict(info, time="2026-10-07 10:00:05"))
    assert "탐지 2회" in popup.history_label.cget("text"), popup.history_label.cget("text")

    # 팝업은 감시 ROI 좌표를 피해서 배치
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    blockers = [config.ROI(name=f"b{i}", x=520, y=i * 160, w=sw - 520, h=150) for i in range(sh // 160)]
    app.cfg.rois.extend(blockers)
    app.alerts.close_all()
    app.alerts.alert(dict(info, roi_id="pp"))
    root.update()
    px, py, pw, ph = app.alerts.popups["pp"].rect()
    for b in blockers + [roi]:
        overlap = alert._overlap((px, py, pw, ph), (b.x, b.y, b.w, b.h))
        assert overlap == 0, f"팝업이 ROI {b.name}를 가림: popup={(px, py, pw, ph)}"
    print(f"팝업 위치 {px},{py} – ROI와 겹치지 않음")
    for b in blockers:
        app.cfg.rois.remove(b)
    assert alert.find_free_spot(100, 50, (0, 0, 1000, 800), [(0, 0, 1000, 800)]) is not None
    app.alerts.recover(dict(info, kind="recover"))
    root.update()
    app.alerts.close_all()

    # 검출 중 화면 표시 오버레이: 클릭 통과 + 프로그램 확인에서 제외 + 캡처 제외
    import winutil
    from capture import Grabber
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    probe = config.ROI(name="표시", x=sw - 260, y=sh - 260, w=100, h=100)
    app.cfg.rois.append(probe)
    app.monitor = object.__new__(worker.Monitor)
    app.states[probe.id] = ("alarm", "테스트")
    app._sync_overlay()
    root.update()
    ov = app.overlay
    assert ov.visible()
    assert winutil.overlay_style_ok(ov.win.winfo_id()), "오버레이가 클릭 통과 상태가 아님"
    root.withdraw()                     # 메인 창이 측정 지점을 가리지 않게 (CI 화면이 작음)
    root.update()
    px, py = probe.x + 50, probe.y + 50
    hwnd = winutil.window_at(px, py)
    proc = winutil.process_name_at(px, py) or ""
    print(f"오버레이 아래 창: {hwnd}, 프로그램: {proc!r}, 오버레이로 판정됨: {winutil.is_passthrough(hwnd)}, "
          f"캡처 제외: {ov.capture_excluded}")
    assert not winutil.is_passthrough(hwnd), "프로그램 확인이 오버레이 창을 대상으로 판단함"
    own = os.path.basename(sys.executable).lower()
    assert proc.lower() != own, f"측정 지점에 우리 프로그램 창이 있음: {proc}"
    root.deiconify()
    ov.heartbeat(True, 2, 1)
    ov.heartbeat(False, 2, 1)
    root.update()
    if ov.capture_excluded:
        with Grabber() as g:
            shot = g.grab(probe.x - 10, probe.y - 10, 120, 120).astype(int)
        red = (np.abs(shot - np.array([0xd5, 0, 0])).max(axis=2) < 40).mean()
        print(f"캡처에 찍힌 테두리 색 비율: {red:.3f}")
        assert red < 0.01, "오버레이가 화면 캡처에 찍힘"
    app.monitor = None
    app._sync_overlay()
    assert not ov.visible()
    app.cfg.rois.remove(probe)

    # 상태 이벤트 처리 + 로그
    app.monitor = object.__new__(worker.Monitor)   # 실행 중인 것처럼 상태 표시만 확인
    app.events.put(("status", roi.id, "alarm", "테스트 상세"))
    app.events.put(("log", "info", "로그 테스트"))
    app._poll_events()
    assert app.tree.set(roi.id, "state") == gui.STATE_TEXT["alarm"]
    app.events.put(("status", roi.id, "moving", "움직임 – 정지 대기"))
    app._poll_events()
    assert app.tree.set(roi.id, "state") == gui.STATE_TEXT["moving"]
    app.monitor = None

    # ---- 대시보드 + 에이전트: 데모 데이터로 화면을 채우고 캡처 (CI 아티팩트로 확인) ----
    demo_dashboard(app)

    root.destroy()
    print("GUI smoke test OK")


def _tab(h, w, x, fold=0.0, bend=0, seed=0, bg=40, fg=190):
    rng = np.random.default_rng(seed)
    img = np.full((h, w), bg, dtype=np.float32)
    tw, th, y = w // 6, int(h * 0.6), int(h * 0.2)
    img[y + int(th * fold):y + th, x:x + tw] = fg
    if bend:
        img[y:y + th // 2, :] = bg
        img[y:y + th // 2, x + bend:x + bend + tw] = fg
    img += rng.normal(0, 5, img.shape)
    g = np.clip(img, 0, 255).astype(np.uint8)
    return np.stack([g, g, np.clip(g.astype(int) + 12, 0, 255).astype(np.uint8)], axis=2)


def demo_dashboard(app):
    import time as _time
    root = app.root
    root.deiconify()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{min(1560, sw)}x{min(940, sh - 40)}+0+0")   # CI 화면 크기에 맞춤
    app.cfg.rois[:] = []
    names = ["1라인 탭 A", "1라인 탭 B", "2라인 노칭", "2라인 와인딩", "3라인 탭 A", "3라인 탭 B", "검사기 HMI", "4라인 컨베이어"]
    kinds = ["match", "match", "shape", "match", "match", "shape", "black", "match"]
    for i, (name, kind) in enumerate(zip(names, kinds)):
        app.cfg.rois.append(config.ROI(name=name, x=100 + i * 10, y=100, w=320, h=180, detector=kind,
                                       still_only=kind != "black", assignee="홍길동" if i % 2 else "김담당"))
    app.monitor = object.__new__(worker.Monitor)
    app.agent.boot(app.cfg.rois, {r.id: 6 for r in app.cfg.rois})
    app._update_running_ui()
    states = [("ok", "[정지 판정 10:41:07] OK와 일치: 거리 0.08 ≤ 허용 0.41(자동)"),
              ("ok", "[정지 판정 10:41:09] OK와 일치: 거리 0.11 ≤ 허용 0.43(자동)"),
              ("moving", "움직임 – 정지 대기 (변화량 18.4 > 3)"),
              ("alarm", "[정지 판정 10:41:10] NG 샘플과 가장 비슷 (OK 0.71 · NG 0.18)"),
              ("ok", "[정지 판정 10:41:02] OK와 일치: 거리 0.06 ≤ 허용 0.39(자동)"),
              ("ok", "[정지 판정 10:40:58] 형상 차이 0.4% (기준 ≥5%)"),
              ("ok", "어두운 픽셀 2.1% (기준 ≥95%)"),
              ("skip", "다른 화면: explorer.exe")]
    for i, (roi, (state, detail)) in enumerate(zip(app.cfg.rois, states)):
        frame = _tab(180, 320, 120 + (i * 13) % 60, fold=0.4 if state == "alarm" else 0.0, seed=i)
        app.events.put(("frame", roi.id, frame))
        for _ in range(3 + i * 7):
            app.agent.on_status(roi.id, "ok", "x")
        app.events.put(("status", roi.id, state, detail))
    now = _time.time()
    for k, h in enumerate((9, 7, 5, 3, 1)):
        app.agent.clock = lambda t=now - h * 3600: t
        for _ in range(k % 3 + 1):
            app.agent.on_alert({"roi_id": app.cfg.rois[3].id, "roi_name": app.cfg.rois[3].name,
                                "kind": "alert", "detail": "NG 샘플과 가장 비슷"})
    app.agent.clock = _time.time
    app.agent.started_at = now - 3 * 3600 - 17 * 60
    app.agent.on_feedback(app.cfg.rois[0].name, "ok", 0.41, 0.44)
    for r in app.cfg.rois[:4]:
        app.agent.on_alert({"roi_id": r.id, "roi_name": r.name, "kind": "alert", "detail": "NG"})
    app._poll_events()
    assert app.wall.cards[app.cfg.rois[0].id].has_frame, "카메라 월 썸네일 미표시"
    app.trend.draw(app.agent.hourly_series(12))
    app._refresh_kpis()
    for _ in range(4):
        app._heartbeat()
    root.update()
    _time.sleep(0.5)
    root.update()
    feed_text = app.feed.text.get("1.0", "end")
    assert "비전 에이전트 기동" in feed_text and "판단" in feed_text, feed_text[:300]
    report = app.generate_report(auto=True)
    assert report and os.path.exists(report)

    out = os.path.join(ROOT, "ci_artifacts")
    os.makedirs(out, exist_ok=True)
    try:
        from capture import Grabber
        root.lift()
        root.attributes("-topmost", True)
        root.update()
        _time.sleep(0.5)
        x, y, w, h = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
        with Grabber() as g:
            shot = g.grab(x, y, w, h)
        from PIL import Image
        Image.fromarray(shot).save(os.path.join(out, "dashboard_preview.png"))
        print(f"대시보드 캡처 저장: {w}x{h}")
    except Exception as e:      # 캡처는 참고용 – 실패해도 테스트는 통과
        print(f"대시보드 캡처 실패: {e}")
    import shutil
    shutil.copy(report, os.path.join(out, "report_preview.html"))
    app.monitor = None


if __name__ == "__main__":
    main()

"""Windows CI용 GUI 스모크 테스트: 모든 창을 실제로 만들고 주요 동작을 호출한 뒤 닫는다.
(tkinter가 없는 환경에서는 실행하지 않음 – unittest discover 대상 아님)"""
import os
import sys
import tempfile
import types

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
    # 잘못 등록한 이미지 옮기기: 우클릭 메뉴 경로(_move) + 끌어 놓기
    sd._move(paths.reference_paths(roi.id, "ok")[-1], "ng")
    assert len(paths.reference_paths(roi.id, "ok")) == 1 and len(paths.reference_paths(roi.id, "ng")) == 1
    sd.top.update()
    ok_box = sd.sections["ok"]["box"]
    tx, ty = ok_box.winfo_rootx() + ok_box.winfo_width() // 2, ok_box.winfo_rooty() + ok_box.winfo_height() // 2
    assert sd._section_at(tx, ty) == "ok", sd._section_at(tx, ty)
    ev = lambda x, y: types.SimpleNamespace(x_root=x, y_root=y)       # noqa: E731
    sd._drag_start(ev(0, 0), paths.reference_paths(roi.id, "ng")[0], "ng", None)
    sd._drag_move(ev(tx, ty))
    sd._drag_end(ev(tx, ty))
    assert len(paths.reference_paths(roi.id, "ok")) == 2 and not paths.reference_paths(roi.id, "ng"), \
        "NG 칸의 이미지를 OK 칸으로 끌어 놓았는데 옮겨지지 않음"
    print("샘플 이미지 이동(우클릭·끌어 놓기) 확인")
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

    # 연속 NG 팝업 조건: 3회부터 팝업, OK 판정이 나오면 초기화
    app.alerts.close_all()
    app.cfg.popup_consecutive = 3
    app.monitor = object.__new__(worker.Monitor)
    for i in range(2):
        app.events.put(("alert", dict(info, roi_id=roi.id, time=f"t{i}")))
        app._poll_events()
    assert roi.id not in app.alerts.popups, "연속 2회인데 팝업이 뜸"
    app.events.put(("alert", dict(info, roi_id=roi.id, time="t3")))
    app._poll_events()
    assert roi.id in app.alerts.popups and "연속 NG 3회" in app.alerts.popups[roi.id].body.cget("text")
    app.events.put(("status", roi.id, "ok", "OK"))
    app._poll_events()
    assert app.consecutive[roi.id] == 0
    app.alerts.close_all()
    app.cfg.popup_consecutive = 1
    app.monitor = None

    # 미니 모니터 (화면 하단 ROI 트렌드): 표시·캡처 제외·대상 프로그램 확인에서 제외
    app.mini.show(app.agent.roi_trends(app.cfg.rois), "auto", [])
    app.mini.update(app.agent.roi_trends(app.cfg.rois), "● 실시간 감시 중", True)
    root.update()
    assert app.mini.visible()
    mx, my = app.mini.win.winfo_x(), app.mini.win.winfo_y()
    assert my > root.winfo_screenheight() // 2, f"미니 모니터가 하단에 있지 않음: y={my}"
    print(f"미니 모니터 위치 {mx},{my} · 캡처 제외 {app.mini.capture_excluded}")
    hid = winutil.window_at(mx + 30, my + 40)
    assert not hid or not winutil.is_passthrough(hid)
    app.mini.hide()
    app.roi_trend.draw(app.agent.roi_trends(app.cfg.rois))
    root.update()

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

    # ---- 화면 언어 전환: 영어로 모든 창을 열어 보고 다시 한국어로 ----
    language_check(app, roi)

    # ---- ROI 모양·회전: 편집기·설정 창·화면 표시·캡처 ----
    shape_check(app)

    # ---- 의견 에이전트: 분석 → 의견 카드, LLM 없이 질문, 가짜 로컬 LLM 서버로 질문 ----
    advisor_check(app, roi)

    # ---- 카메라 월: 카드 끌어서 이동 / 크기 조절 / 자동 정렬 ----
    wall_drag_check(app, roi)

    # ---- ROI 가림 판정: 실제로 덮은 창이 있을 때만 건너뜀 ----
    occlusion_check(app)

    # ---- 대시보드 + 에이전트: 데모 데이터로 화면을 채우고 캡처 (CI 아티팩트로 확인) ----
    demo_dashboard(app)

    root.destroy()
    print("GUI smoke test OK")


def occlusion_check(app):
    """다른 프로세스(pythonw.exe) 창으로 ROI를 덮었을 때만 건너뛰고, 옆에 붙어 있을 때는 판정하는지 확인."""
    import subprocess
    import time

    import occlusion
    import winutil
    root = app.root
    own = os.path.basename(sys.executable)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        print("pythonw.exe 없음 – 가림 판정 확인 생략")
        return
    # 대상 프로그램 역할: 이 프로세스의 창으로 ROI 주변을 채움
    target = tk_toplevel(root, 100, 100, 700, 500)
    roi = (300, 250, 200, 150)                      # x 300~500, y 250~400

    def visibility():
        root.update()
        return occlusion.roi_visibility(roi, winutil.visible_windows(), own)

    def spawn(x, y, w, h, decorated):
        code = ("import tkinter as tk;r=tk.Tk();r.overrideredirect(%d);r.geometry('%dx%d+%d+%d');"
                "r.configure(bg='#ff00ff');r.attributes('-topmost',1);r.after(20000,r.destroy);r.mainloop()"
                % (0 if decorated else 1, w, h, x, y))
        proc = subprocess.Popen([pythonw, "-c", code])
        for _ in range(60):
            root.update()
            wins = [win for win in winutil.visible_windows() if win.process.lower() == "pythonw.exe"]
            if wins:
                time.sleep(0.3)
                return proc, [win for win in winutil.visible_windows() if win.process.lower() == "pythonw.exe"]
            time.sleep(0.2)
        proc.kill()
        raise AssertionError("pythonw 창이 뜨지 않음")

    try:
        res = visibility()
        print(f"가림 없음: {res}")
        assert res.ok, f"아무것도 안 가렸는데 건너뜀: {res.detail}"

        proc, wins = spawn(400, 300, 300, 200, decorated=False)     # ROI 오른쪽 아래 절반을 덮음
        res = visibility()
        print(f"덮은 창 {wins[0].rect}: {res}")
        assert not res.ok and "pythonw.exe" in res.detail, res
        proc.kill()
        proc.wait()

        # 테두리 있는 일반 창을 ROI 오른쪽에 바짝 붙임 (보이지 않는 크기 조절 테두리가 ROI에 걸치는 상황)
        proc, wins = spawn(500 - 6, 200, 300, 250, decorated=True)
        frame = wins[0].rect
        res = visibility()
        print(f"옆에 붙은 창 (보이는 영역 {frame}): {res}")
        if frame[0] >= 500 - 2:
            assert res.ok, f"ROI를 가리지 않는 옆 창 때문에 건너뜀: {res.detail}"
        else:
            assert not res.ok, res
        proc.kill()
        proc.wait()
        print("가림 판정 확인 완료")
    finally:
        target.destroy()
        root.update()


def drag_card(app, roi, dx, dy, grip=False):
    """카메라 월 카드를 (dx, dy)만큼 끈다 (grip=True면 크기 조절)."""
    ev = lambda x, y: types.SimpleNamespace(x_root=x, y_root=y)       # noqa: E731
    wall = app.wall
    wall._press(roi.id, ev(500, 500), "resize" if grip else "move")
    wall._motion(ev(500 + dx // 2, 500 + dy // 2))
    wall._motion(ev(500 + dx, 500 + dy))
    wall._release(ev(500 + dx, 500 + dy))
    app.root.update()


def wall_drag_check(app, roi):
    card = app.wall.cards[roi.id]
    x0, y0 = app.wall.canvas.coords(app.wall.items[roi.id])
    drag_card(app, roi, 96, 40)
    x1, y1 = app.wall.canvas.coords(app.wall.items[roi.id])
    import dashboard
    assert (x1, y1) == (dashboard._snap(x0 + 96, 8), dashboard._snap(y0 + 40, 8)), ((x0, y0), (x1, y1))
    assert roi.wall[:2] == [int(x1), int(y1)], roi.wall
    drag_card(app, roi, 160, 88, grip=True)
    assert (card.vw, card.vh) == (256 + 160, 144 + 88), (card.vw, card.vh)
    assert roi.wall[2:] == [416, 232], roi.wall
    app.monitor = object.__new__(worker.Monitor)
    app._sync_thumb_sizes()
    assert app.monitor.thumb_sides[roi.id] == 416
    app.monitor = None
    app.wall._press(roi.id, types.SimpleNamespace(x_root=1, y_root=1), "move")    # 클릭 = 선택 (이동 없음)
    app.wall._release(None)
    assert app.tree.selection() == (roi.id,)
    app.reset_wall_layout()
    assert roi.wall == [] and (card.vw, card.vh) == (256, 144)
    print("카메라 월 끌어서 이동·크기 조절·자동 정렬 확인")


def tk_toplevel(root, x, y, w, h):
    import tkinter as tk
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.configure(bg="#203040")
    win.attributes("-topmost", True)
    win.update()
    return win


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
    # 첫 카드를 왼쪽 위로 옮기고 크게 – 나머지 카드는 빈 자리에 자동 배치
    root.update()
    first = app.cfg.rois[0]
    fx, fy = app.wall.canvas.coords(app.wall.items[first.id])
    drag_card(app, first, int(12 - fx), int(12 - fy))
    drag_card(app, first, 176, 96, grip=True)
    assert first.wall[0] <= 16 and first.wall[1] <= 16 and first.wall[2:] == [432, 240], first.wall
    first_rect = (*first.wall[:2], *app.wall._card_size(app.wall.cards[first.id]))
    for r in app.cfg.rois[1:]:
        cx, cy = app.wall.canvas.coords(app.wall.items[r.id])
        other = (cx, cy, *app.wall._card_size(app.wall.cards[r.id]))
        assert not db_overlap(first_rect, other), f"자동 배치 카드가 직접 배치한 카드와 겹침: {r.name}"
    app.trend.draw(app.agent.hourly_series(12))
    app._refresh_kpis()
    for _ in range(4):
        app._heartbeat()
    root.update()
    _time.sleep(0.5)
    root.update()
    app.log("warning", "시스템 로그 통합 확인")
    feed_text = app.feed.text.get("1.0", "end")
    assert "비전 에이전트 기동" in feed_text and "판단" in feed_text, feed_text[:300]
    assert "시스템 로그 통합 확인" in feed_text
    app._sync_mini()
    app._refresh_trends()
    root.update()
    report = app.generate_report(auto=True)
    assert report and os.path.exists(report)
    assert "data:image/jpeg;base64," in open(report, encoding="utf-8").read(), "리포트에 이미지 없음"

    out = os.path.join(ROOT, "ci_artifacts")
    os.makedirs(out, exist_ok=True)
    try:
        capture_previews(app, out)
    except Exception as e:      # 캡처는 참고용 – 실패해도 테스트는 통과
        import traceback
        traceback.print_exc()
        print(f"대시보드 캡처 실패: {e}")
    import shutil
    shutil.copy(report, os.path.join(out, "report_preview.html"))
    app.monitor = None


def db_overlap(a, b):
    import dashboard
    return dashboard._overlap(a, b)


def check_layout(app):
    """화면 분할: 위 = 카메라 월 | 활동·로그, 아래 = ROI 목록 | ROI 모니터링."""
    wall, feed, tree, mon = app.wall, app.feed, app.tree, app.roi_trend
    assert feed.winfo_rootx() > wall.winfo_rootx(), "활동·로그가 카메라 월 오른쪽에 있지 않음"
    assert tree.winfo_rooty() > wall.winfo_rooty() + wall.winfo_height() - 5, "ROI 목록이 아래에 있지 않음"
    assert mon.winfo_rooty() > feed.winfo_rooty() + feed.winfo_height() - 5, "ROI 모니터링이 아래에 있지 않음"
    assert mon.winfo_rootx() > tree.winfo_rootx(), "ROI 모니터링이 ROI 목록 오른쪽에 있지 않음"
    assert tree.winfo_height() > 60 and mon.winfo_height() > 100, (tree.winfo_height(), mon.winfo_height())


def capture_previews(app, out):
    """여러 모니터 크기에서 대시보드를 캡처하고, 미니 모니터·팝업이 뜬 전체 화면도 캡처한다."""
    import time as _time
    import winutil
    from capture import Grabber
    from PIL import Image
    root = app.root
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    print(f"CI 화면 해상도: {sw}x{sh}")
    root.attributes("-topmost", True)
    for w, h in ((1920, 1040), (1600, 900), (1366, 728)):
        if w > sw or h > sh:
            continue
        root.state("normal")
        root.geometry(f"{w}x{h}+0+0")
        for _ in range(6):
            root.update()
            _time.sleep(0.15)
        app._refresh_trends()
        app.trend.draw(app.agent.hourly_series(12))
        root.update()
        _time.sleep(0.4)
        app._place_sash()
        for _ in range(4):
            root.update()
            _time.sleep(0.1)
        x, y = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        check_layout(app)
        top_h = app.wall.winfo_height()
        print(f"  카메라 월 높이 {top_h}px / 창 {rh}px, 카드 열 수 {app.wall._cols}")
        assert top_h >= rh * 0.4, f"{w}x{h}: 카메라 월이 너무 작음 ({top_h}px)"
        with Grabber() as g:
            shot = g.grab(x, y, rw, rh)
        Image.fromarray(shot).save(os.path.join(out, f"dashboard_{w}x{h}.png"))
        print(f"대시보드 캡처: 요청 {w}x{h} → 실제 창 {rw}x{rh}")
    # 의견 탭 캡처
    root.geometry("1920x1040+0+0" if sw >= 1920 else f"{sw}x{sh - 40}+0+0")
    root.update()
    app._place_sash()
    app._advice = None
    app._run_advisor(force=True)
    wait_event(app, lambda: app._advice is not None)
    app.side_tabs.select(app.advisor_panel)
    for _ in range(4):
        root.update()
        _time.sleep(0.1)
    with Grabber() as g:
        shot = g.grab(root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height())
    Image.fromarray(shot).save(os.path.join(out, "dashboard_advisor.png"))
    app.side_tabs.select(app.feed)
    root.update()
    # 전체 화면: 메인 창 최소화 + 미니 모니터 + 탐지 팝업
    root.attributes("-topmost", False)
    root.iconify()
    app._sync_mini()
    root.update()
    if app.mini.win is not None:
        winutil.set_capture_visible(app.mini.win.winfo_id(), True)   # 미리보기용으로만 캡처 허용
    roi = app.cfg.rois[3]
    app.alerts.alert({"kind": "alert", "roi_id": roi.id, "roi_name": roi.name, "detector": roi.detector_label(),
                      "detail": "NG 샘플과 가장 비슷 (OK 0.71 · NG 0.18)", "elapsed": None, "assignee": "홍길동",
                      "assignee_email": "", "time": "2026-10-07 10:41:10", "snapshot": None,
                      "raw_snapshot": None, "roi_detector": "match", "consecutive": 2})
    for _ in range(6):
        root.update()
        _time.sleep(0.15)
    popup_rect = app.alerts.popups[roi.id].rect()
    mini_rect = app.mini.rect()
    print(f"팝업 {popup_rect} · 미니 모니터 {mini_rect}")
    if mini_rect:
        assert alert._overlap(popup_rect, mini_rect) == 0, "탐지 팝업이 미니 모니터를 가림"
    with Grabber() as g:
        img, _l, _t = g.grab_virtual_screen()
    img.save(os.path.join(out, "screen_running.png"))
    print("전체 화면(미니 모니터·팝업) 캡처 완료")
    app.alerts.close_all()
    app.mini.hide()
    root.deiconify()

    # 영어 화면 미리보기
    app.set_language("en")
    root.state("normal")
    root.geometry("1920x1040+0+0" if sw >= 1920 else f"{sw}x{sh - 40}+0+0")
    for _ in range(6):
        root.update()
        _time.sleep(0.15)
    app._place_sash()
    app.trend.draw(app.agent.hourly_series(12))
    for _ in range(4):
        root.update()
        _time.sleep(0.1)
    check_layout(app)
    root.attributes("-topmost", True)
    root.update()
    with Grabber() as g:
        shot = g.grab(root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height())
    Image.fromarray(shot).save(os.path.join(out, "dashboard_en.png"))
    root.attributes("-topmost", False)
    print("영어 대시보드 캡처 완료")
    app.set_language("ko")


def shape_check(app):
    import geometry
    import roi_editor
    from capture import Grabber
    from PIL import Image
    root = app.root
    other = config.ROI(name="기존 타원", x=500, y=300, w=160, h=90, shape="ellipse", angle=30)
    img = Image.new("RGB", (root.winfo_screenwidth(), root.winfo_screenheight()), (30, 30, 40))
    sel = roi_editor.RegionSelector(root, img, 0, 0, existing=[other], single=False)
    root.update()
    # 안내 막대: 끌어서 이동 · 아래로 전환 · 숨기기 (가린 곳에도 ROI를 지정할 수 있어야 함)
    bx, by = sel.canvas.coords(sel.banner)
    drag = lambda x, y: types.SimpleNamespace(x_root=x, y_root=y)   # noqa: E731
    sel._banner_press(drag(100, 100))
    sel._banner_move(drag(160, 400))
    sel._banner_release(drag(160, 400))
    nx, ny = sel.canvas.coords(sel.banner)
    assert ny > by + 200, (by, ny)
    sel.move_banner(-5000, -5000)                        # 화면 밖으로 나가지 않음
    mx, my = sel.canvas.coords(sel.banner)
    assert mx > 0 and my == 0, (mx, my)
    sel.flip_banner()
    assert sel.banner_at_bottom and sel.canvas.coords(sel.banner)[1] > root.winfo_screenheight() / 2
    sel.flip_banner()
    assert not sel.banner_at_bottom
    sel.toggle_banner()
    assert sel.canvas.itemcget(sel.banner, "state") == "hidden"
    assert sel.canvas.itemcget(sel.banner_hint, "state") == "normal"
    sel.toggle_banner()
    assert sel.canvas.itemcget(sel.banner, "state") == "normal"
    root.update()
    # 실제 마우스 동작(누르기 → 끌기 → 놓기)으로 그리기 – 놓을 때 오류가 났던 경로
    ev = lambda x, y, state=0: types.SimpleNamespace(x=x, y=y, state=state, delta=0)   # noqa: E731
    sel._on_press(ev(700, 300))
    sel._on_drag(ev(760, 340))
    sel._on_release(ev(780, 350))
    assert len(sel.regions) == 1 and (sel.regions[0]["w"], sel.regions[0]["h"]) == (80, 50), sel.regions
    sel._on_press(ev(900, 300))
    sel._on_release(ev(960, 330, state=0x0001))          # Shift: 정사각형
    assert (sel.regions[1]["w"], sel.regions[1]["h"]) == (60, 60), sel.regions[1]
    sel._undo()
    sel._undo()
    sel.add_region(100, 120, 200, 80)                    # 사각형
    sel.rotate_by(10)
    sel.rotate_by(-25)
    assert sel.regions[0]["angle"] == 345.0, sel.regions[0]["angle"]
    sel.set_mode("ellipse")
    sel.add_region(400, 500, 120, 120)                   # 원
    cx, cy = 460, 560
    sel.rotate_to_point(cx + 100, cy, snap=15)           # 오른쪽 = 90°
    assert sel.regions[1]["angle"] == 90.0, sel.regions[1]["angle"]
    assert sel._hit(460, 560) == 1 and sel._hit(5, 5) is None
    sel._finish()
    res = sel.result
    assert [(r.shape, r.angle) for r in res] == [("rect", 345.0), ("ellipse", 90.0)], res
    # 1개 모드: 기존 ROI를 불러와 새로 그리면 대신하되 각도는 유지
    sel = roi_editor.RegionSelector(root, img, 0, 0, single=True,
                                    initial=roi_editor.Region(50, 60, 100, 50, "ellipse", 20.0))
    root.update()
    sel.add_region(300, 300, 80, 40)
    sel.set_mode("rect")                                 # 1개 모드: 지금 영역의 모양도 바뀜
    sel._finish()
    assert len(sel.result) == 1 and sel.result[0].angle == 20.0 and sel.result[0].shape == "rect", sel.result

    # 설정 창: 모양·각도 입력
    roi = config.ROI(name="타원", x=200, y=200, w=120, h=80, shape="ellipse", angle=15)
    dlg = roi_dialog.RoiDialog(root, roi, "ROI")
    collected = dlg._collect()
    assert (collected.shape, collected.angle) == ("ellipse", 15.0)
    dlg.v_angle.set("-30")
    dlg.v_shape.set(i18n_tr("사각형"))
    collected = dlg._collect()
    assert (collected.shape, collected.angle) == ("rect", 330.0), (collected.shape, collected.angle)
    dlg.top.destroy()

    # 화면 표시(오버레이)와 실제 캡처
    app.cfg.rois.append(roi)
    app.monitor = object.__new__(worker.Monitor)
    app._sync_overlay()
    root.update()
    app.monitor = None
    app._sync_overlay()
    app.cfg.rois.remove(roi)
    with Grabber() as g:
        frame = geometry.grab(g, roi)
    assert frame.shape == (80, 120, 3), frame.shape
    print("ROI 모양·회전 확인: 편집기·설정 창·화면 표시·캡처")


def i18n_tr(text):
    import i18n
    return i18n.tr(text)


def wait_event(app, cond, timeout=15.0):
    import time
    end = time.time() + timeout
    while time.time() < end:
        app._poll_events()
        app.root.update()
        if cond():
            return True
        time.sleep(0.1)
    return False


def advisor_check(app, roi):
    import http.server
    import json as _json
    import threading
    app._advice = None
    app._run_advisor(force=True)
    assert wait_event(app, lambda: app._advice is not None), "의견 분석 결과가 오지 않음"
    items = app._advice[0]
    print(f"의견 {len(items)}건: " + " | ".join(a.title for a in items[:4]))
    assert app.advisor_panel.inner.winfo_children(), "의견 카드가 표시되지 않음"
    app.side_tabs.select(app.advisor_panel)
    app.root.update()
    # LLM 없이 질문 → 규칙 분석으로 답
    app._ask_llm("무엇을 먼저 해야 하나요?")
    assert "LLM이 연결되어 있지 않아" in app.advisor_panel.answers[0][1]

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert "분석 자료" in body["messages"][1]["content"] or "ROI" in body["messages"][1]["content"]
            out = _json.dumps({"choices": [{"message": {"content": "1. 테스트 LLM 의견"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        app.cfg.llm_enabled = True
        app.cfg.llm_url = f"http://127.0.0.1:{server.server_port}/v1"
        app.cfg.llm_model = "test-model"
        app._show_advice()
        app._llm_summary()
        assert wait_event(app, lambda: app.advisor_panel.answers[0][1] == "1. 테스트 LLM 의견"), \
            app.advisor_panel.answers[:1]
        print("LLM(가짜 로컬 서버) 종합 의견 수신 확인")
    finally:
        server.shutdown()
        app.cfg.llm_enabled = False
        app._show_advice()
    app.side_tabs.select(app.feed)
    app.root.update()


def language_check(app, roi):
    import re
    import i18n
    root = app.root
    hangul = re.compile("[가-힣]")
    app.log("info", "언어 전환 전 기록")
    app.set_language("en")
    root.update()
    assert i18n.language() == "en" and app.cfg.language == "en"
    heads = [app.tree.heading(c[0])["text"] for c in gui.COLUMNS]
    assert not any(hangul.search(h) for h in heads), heads
    assert not hangul.search(app.status_pill.cget("text")), app.status_pill.cget("text")
    assert "언어 전환 전 기록" in app.feed.text.get("1.0", "end"), "언어 전환 후 이전 기록이 사라짐"
    # 영어로 모든 창 열기 (오류 없이 열리고 주요 글자가 영어인지)
    dlg = roi_dialog.RoiDialog(root, roi, "ROI")
    for kind in detectors.DETECTOR_ORDER:
        dlg.v_kind.set(i18n.tr(detectors.DETECTORS[kind]["label"]))
        dlg._on_kind_changed()
        assert dlg._collect().detector == kind
    root.update()
    dlg.top.destroy()
    sd = samples_dialog.SamplesDialog(root, roi)
    root.update()
    assert not hangul.search(sd.top.title().replace(roi.name, "")), sd.top.title()
    sd.top.destroy()
    st = settings_dialog.SettingsDialog(root, app.cfg)
    root.update()
    st.top.destroy()
    info = {"kind": "alert", "roi_id": roi.id, "roi_name": roi.name, "detector": roi.detector_label(),
            "detail": "x", "elapsed": None, "assignee": "", "assignee_email": "", "time": "2026-01-01 00:00:00",
            "snapshot": None, "raw_snapshot": None, "roi_detector": roi.detector, "consecutive": 2}
    app.alerts.alert(info)
    root.update()
    popup = app.alerts.popups[roi.id]
    assert not hangul.search(popup.title_label.cget("text").replace(roi.name, "")), popup.title_label.cget("text")
    app.alerts.close_all()
    app.set_language("ko")
    root.update()
    assert app.tree.heading("name")["text"] == "이름" and i18n.language() == "ko"
    print("한국어 ↔ English 전환 확인")


if __name__ == "__main__":
    main()

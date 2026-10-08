"""GUI/Windows 없이 검증 가능한 핵심 로직 테스트.  실행: python -m unittest discover -s tests"""
import json
import os
import queue
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nvr_inspector"))

import agent  # noqa: E402
import config  # noqa: E402
import detectors  # noqa: E402
import notifier  # noqa: E402
import occlusion  # noqa: E402
import worker  # noqa: E402


def solid(rgb, h=90, w=160):
    return np.full((h, w, 3), rgb, dtype=np.uint8)


def noise(h=90, w=160, seed=0):
    return np.random.default_rng(seed).integers(0, 256, (h, w, 3), dtype=np.uint8)


class DetectorTests(unittest.TestCase):
    def ev(self, kind, frame, params=None, state=None, ref=None):
        return detectors.evaluate(kind, params or {}, frame, {} if state is None else state, reference=ref)

    def test_black(self):
        self.assertTrue(self.ev("black", solid(5)).abnormal)
        self.assertFalse(self.ev("black", noise()).abnormal)
        frame = solid(5)
        frame[:, :20] = 200   # 12.5% 밝음 → 어두운 비율 87.5% < 95%
        self.assertFalse(self.ev("black", frame).abnormal)
        self.assertTrue(self.ev("black", frame, {"ratio": 0.8}).abnormal)

    def test_white(self):
        self.assertTrue(self.ev("white", solid(250)).abnormal)
        self.assertFalse(self.ev("white", solid(5)).abnormal)

    def test_uniform(self):
        self.assertTrue(self.ev("uniform", solid((20, 40, 200))).abnormal)
        self.assertFalse(self.ev("uniform", noise()).abnormal)

    def test_frozen(self):
        state = {}
        self.assertIsNone(self.ev("frozen", noise(seed=1), state=state).abnormal)
        self.assertTrue(self.ev("frozen", noise(seed=1), state=state).abnormal)
        self.assertFalse(self.ev("frozen", noise(seed=2), state=state).abnormal)

    def test_color(self):
        blue = solid((10, 20, 230))
        self.assertTrue(self.ev("color", blue, {"rgb": [0, 0, 255]}).abnormal)
        self.assertFalse(self.ev("color", solid((200, 30, 30)), {"rgb": [0, 0, 255]}).abnormal)
        self.assertEqual(detectors.mean_color(blue), [10, 20, 230])

    def test_reference(self):
        ref = noise(seed=3)
        self.assertIsNone(self.ev("reference", ref).abnormal)                        # 기준 없음
        self.assertFalse(self.ev("reference", ref.copy(), ref=ref).abnormal)          # 같음
        self.assertTrue(self.ev("reference", 255 - ref, {"max_diff": 20}, ref=ref).abnormal)
        self.assertIsNone(self.ev("reference", noise(50, 50), ref=ref).abnormal)      # 크기 다름

    def test_large_and_tiny_frames(self):
        self.assertTrue(self.ev("black", solid(0, 1080, 1920)).abnormal)
        self.assertTrue(self.ev("black", solid(0, 5, 5)).abnormal)
        self.assertFalse(self.ev("reference", noise(5, 7, seed=4), ref=noise(5, 7, seed=4)).abnormal)

    def test_normalize_params(self):
        p = detectors.normalize_params("black", {"threshold": "999", "ratio": "x", "junk": 1})
        self.assertEqual(p, {"threshold": 255.0, "ratio": 0.95})
        p = detectors.normalize_params("color", {"rgb": [300, -5, "10"]})
        self.assertEqual(p["rgb"], [255, 0, 10])


def tab_image(h=240, w=320, x=130, y=40, tw=60, th=150, bg=30, fg=200, seed=0, fold=0.0,
              bend=0, notch=None):
    """합성 탭 이미지: 어두운 배경 위 밝은 직사각형 탭.
    fold: 위쪽 비율만큼 접혀 사라짐, bend: 위쪽 절반을 옆으로 휨(px), notch: (y,x,h,w) 찍힘."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w), bg, dtype=np.float32)
    top = y + int(th * fold)
    img[top:y + th, x:x + tw] = fg
    if bend:
        mid = y + th // 2
        img[y:mid, :] = bg
        img[y:mid, x + bend:x + bend + tw] = fg
    if notch:
        ny, nx, nh, nw = notch
        img[ny:ny + nh, nx:nx + nw] = bg
    img += rng.normal(0, 4, img.shape)
    gray = np.clip(img, 0, 255).astype(np.uint8)
    return np.repeat(gray[:, :, None], 3, axis=2)


class ShapeDetectorTests(unittest.TestCase):
    """형상 검사(탭 접힘·찍힘·휨)."""

    def ev(self, frame, refs, **params):
        return detectors.evaluate("shape", params, frame, {}, reference=refs)

    def test_normal_same_and_shifted_and_lighting(self):
        ref = tab_image(seed=1)
        self.assertFalse(self.ev(tab_image(seed=2), ref).abnormal)
        shifted = self.ev(tab_image(x=142, y=33, seed=3), ref)
        self.assertFalse(shifted.abnormal, shifted.detail)
        self.assertIn("위치 보정", shifted.detail)
        brighter = tab_image(bg=70, fg=250, seed=4)        # 조명 밝기 변화
        self.assertFalse(self.ev(brighter, ref).abnormal)

    def test_fold_bend_notch_detected(self):
        ref = tab_image(seed=1)
        for name, frame in (("접힘", tab_image(fold=0.35, seed=5)),
                            ("휨", tab_image(bend=25, seed=6)),
                            ("찍힘", tab_image(notch=(120, 130, 25, 25), seed=7))):
            res = self.ev(frame, ref)
            self.assertTrue(res.abnormal, f"{name}: {res.detail}")
            self.assertIsNotNone(res.mask)
            self.assertEqual(res.mask.shape, frame.shape[:2])

    def test_defect_mask_location(self):
        ref = tab_image(seed=1)
        res = self.ev(tab_image(notch=(120, 130, 25, 25), seed=8), ref)
        ys, xs = np.nonzero(res.mask)
        self.assertTrue(110 <= ys.mean() <= 150 and 125 <= xs.mean() <= 160)
        over = detectors.overlay_defects(tab_image(seed=8), res.mask)
        self.assertGreater(int(over[ys[0], xs[0], 0]), int(over[ys[0], xs[0], 1]))

    def test_dark_tab_on_bright_background_auto(self):
        ref = tab_image(bg=220, fg=40, seed=1)
        self.assertFalse(self.ev(tab_image(bg=220, fg=40, x=136, seed=2), ref).abnormal)
        self.assertTrue(self.ev(tab_image(bg=220, fg=40, fold=0.4, seed=3), ref).abnormal)

    def test_multiple_references_pick_closest(self):
        straight, bent = tab_image(seed=1), tab_image(bend=25, seed=2)
        frame = tab_image(bend=25, seed=3)
        self.assertTrue(self.ev(frame, [straight]).abnormal)
        res = self.ev(frame, [straight, bent])
        self.assertFalse(res.abnormal, res.detail)
        self.assertIn("기준 2장", res.detail)

    def test_presence_gate_and_bad_reference(self):
        ref = tab_image(seed=1)
        empty = tab_image(th=0, seed=2)
        self.assertIsNone(self.ev(empty, ref, min_presence=50).abnormal)
        self.assertIsNone(self.ev(empty, ref).abnormal)        # 제품(셀)이 없으면 항상 판정 보류
        flat = np.full((240, 320, 3), 90, dtype=np.uint8)
        self.assertIsNone(self.ev(tab_image(seed=2), flat).abnormal)
        self.assertIsNone(self.ev(tab_image(seed=2), None).abnormal)

    def test_ng_and_skip_samples(self):
        ok = [tab_image(seed=1), tab_image(x=140, seed=2)]
        ng_bend = tab_image(bend=12, seed=3)
        empty = tab_image(th=0, seed=4)
        samples = {"ok": ok, "ng": [ng_bend], "skip": [empty]}
        same_ng = self.ev(tab_image(bend=12, x=134, seed=5), samples, max_defect=30)   # 기준이 느슨해도
        self.assertTrue(same_ng.abnormal, same_ng.detail)                              # 등록 NG와 일치 → 불량
        self.assertIn("NG 샘플", same_ng.detail)
        self.assertFalse(self.ev(tab_image(x=136, seed=6), samples).abnormal)
        held = self.ev(tab_image(th=0, bg=36, seed=7), samples)
        self.assertIsNone(held.abnormal)
        self.assertIn("제품 없음", held.detail)

    def test_self_check(self):
        samples = {"ok": [tab_image(seed=i, x=128 + i * 4) for i in range(3)],
                   "ng": [tab_image(fold=0.4, seed=10), tab_image(bend=20, seed=11)],
                   "skip": [tab_image(th=0, seed=12), tab_image(th=0, seed=13)]}
        r = detectors.self_check("shape", {}, samples)
        self.assertTrue(r["passed"], r["summary"])
        self.assertEqual(r["ng"], (0, 2))
        bad = detectors.self_check("shape", {"max_defect": 90}, samples)
        self.assertFalse(bad["passed"])
        self.assertIn("놓침", bad["summary"])

    def test_texture_option(self):
        ref = tab_image(seed=1)
        frame = tab_image(seed=2)
        rng = np.random.default_rng(9)
        frame[60:170, 132:188] = np.clip(frame[60:170, 132:188].astype(int)
                                         + rng.integers(-60, 60, (110, 56, 1)), 0, 255).astype(np.uint8)
        self.assertFalse(self.ev(frame, ref).abnormal)                     # 윤곽은 그대로
        self.assertTrue(self.ev(frame, ref, max_texture=0.5).abnormal)     # 표면 구김 감지

    def test_choice_param_normalize(self):
        self.assertEqual(detectors.normalize_params("shape", {"polarity": "bad"})["polarity"], "auto")
        self.assertEqual(detectors.normalize_params("shape", {"polarity": "dark"})["polarity"], "dark")


class MatchDetectorTests(unittest.TestCase):
    """OK/NG 이미지 매칭 (흐르는 라인: 탭 위치가 매번 다름)."""

    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(0)
        cls.ok = staticmethod(lambda seed: tab_image(h=120, w=160, x=int(rng.integers(50, 75)),
                                                     y=int(rng.integers(15, 30)),
                                                     tw=30, th=70, seed=seed))
        cls.samples = {
            "ok": [cls.ok(i) for i in range(5)],
            "ng": [tab_image(h=120, w=160, x=60, y=20, tw=30, th=70, fold=0.4, seed=10),
                   tab_image(h=120, w=160, x=58, y=20, tw=30, th=70, bend=14, seed=11)],
            "skip": [tab_image(h=120, w=160, th=0, seed=20)],
        }

    def ev(self, frame, samples=None, state=None, **params):
        return detectors.evaluate("match", params, frame, {} if state is None else state,
                                  reference=self.samples if samples is None else samples)

    def test_classification(self):
        self.assertFalse(self.ev(self.ok(30)).abnormal)
        self.assertFalse(self.ev(tab_image(h=120, w=160, x=62, y=22, tw=30, th=70, bg=70, fg=240, seed=31)).abnormal)
        ng = self.ev(tab_image(h=120, w=160, x=66, y=20, tw=30, th=70, fold=0.4, seed=32))
        self.assertTrue(ng.abnormal)
        self.assertIn("NG 샘플", ng.detail)
        novel = self.ev(tab_image(h=120, w=160, x=60, y=20, tw=30, th=70, notch=(45, 60, 25, 18), seed=33))
        self.assertTrue(novel.abnormal, novel.detail)                       # NG 샘플에 없는 불량
        self.assertIn("OK와 다름", novel.detail)
        self.assertIsNotNone(novel.mask)
        self.assertIsNone(self.ev(tab_image(h=120, w=160, th=0, bg=60, seed=34)).abnormal)  # 빈 화면 → 보류

    def test_manual_threshold_and_missing_samples(self):
        self.assertTrue(self.ev(self.ok(40), ok_threshold=0.001).abnormal)
        self.assertIsNone(self.ev(self.ok(41), samples={"ok": []}).abnormal)
        wrong = {"ok": [tab_image(h=60, w=80, seed=1)]}
        self.assertIsNone(self.ev(self.ok(42), samples=wrong).abnormal)

    def test_calibration_and_cache(self):
        calib = detectors.match_calibration(self.samples, (120, 160), 15)
        self.assertLess(calib["ok_max"], calib["ng_min"])
        self.assertTrue(calib["ok_max"] < calib["threshold"] < calib["ng_min"])
        state = {}
        self.ev(self.ok(50), state=state)
        cached = state["match_cache"]
        self.ev(self.ok(51), state=state)
        self.assertIs(state["match_cache"], cached)                         # 샘플 그대로면 재계산 안 함

    def test_shift_direction(self):
        ref = tab_image(h=120, w=160, x=60, y=20, tw=30, th=70, seed=1)
        cur = tab_image(h=120, w=160, x=70, y=26, tw=30, th=70, seed=2)
        a = detectors._Spectra(detectors._match_gray(cur), detectors._fft_shape((60, 80)))
        b = detectors._Spectra(detectors._match_gray(ref), detectors._fft_shape((60, 80)))
        d, dy, dx = detectors.match_distance(a, b, 20)
        self.assertEqual((dy, dx), (3, 5))                                  # 분석 해상도(1/2) 기준


class SamplePathTests(unittest.TestCase):
    def test_classes(self):
        import paths
        with tempfile.TemporaryDirectory() as d, mock.patch.object(paths, "REF_DIR", d):
            for cls in ("ok", "ok", "ng", "skip"):
                open(paths.new_reference_path("ab12cd34", cls), "w").close()
            self.assertEqual([os.path.basename(p) for p in paths.reference_paths("ab12cd34", "ok")],
                             ["ab12cd34.png", "ab12cd34_2.png"])
            self.assertEqual(len(paths.reference_paths("ab12cd34", "ng")), 1)
            paths.delete_references("ab12cd34", "ng")
            self.assertEqual(paths.reference_paths("ab12cd34", "ng"), [])
            paths.delete_references("ab12cd34")
            self.assertEqual(os.listdir(d), [])


class FakeClock:
    def __init__(self, t=1_760_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.ag = agent.VisionAgent(clock=self.clock)
        self.rois = [config.ROI(name=f"cam{i}") for i in range(4)]
        self.ag.boot(self.rois, {r.id: 2 for r in self.rois})

    def alert(self, roi, kind="alert"):
        return self.ag.on_alert({"roi_id": roi.id, "roi_name": roi.name, "kind": kind, "detail": "NG"})

    def kinds(self):
        return [f.kind for f in self.ag.feed]

    def test_boot_feed(self):
        self.assertEqual(self.kinds()[0], "boot")
        self.assertIn("ROI 4개", self.ag.feed[0].text)

    def test_mass_alarm_inferred_once(self):
        self.assertEqual(self.alert(self.rois[0]), [])
        self.clock.t += 3
        self.assertEqual(self.alert(self.rois[1]), [])
        self.clock.t += 3
        actions = self.alert(self.rois[2])                       # 15초 안에 3/4개
        self.assertEqual([a.kind for a in actions], ["teams"])
        self.assertIn("화면 전체", actions[0].title)
        self.clock.t += 2
        self.assertEqual(self.alert(self.rois[3]), [])            # 쿨다운
        self.assertIn("think", self.kinds())

    def test_trend_escalation(self):
        roi = self.rois[0]
        self.assertEqual(self.alert(roi), [])
        self.clock.t += 120
        self.assertEqual(self.alert(roi), [])
        self.clock.t += 120
        actions = self.alert(roi)                                 # 10분 안에 3회
        self.assertEqual(len(actions), 1)
        self.assertIn("설비 점검", actions[0].title)
        self.assertEqual(self.ag.stats[roi.id].ng, 3)
        self.assertEqual(sum(c for _h, c in self.ag.hourly_series()), 3)

    def test_skip_persistence_diagnosis(self):
        roi = self.rois[0]
        self.ag.on_status(roi.id, "skip", "다른 화면: explorer.exe")
        self.clock.t += 61
        self.ag.on_status(roi.id, "skip", "다른 화면: explorer.exe")
        self.assertTrue(any("가려졌거나" in f.text for f in self.ag.feed))

    def test_inspection_counting(self):
        roi = self.rois[0]
        for _ in range(3):
            self.ag.on_status(roi.id, "ok", "어두운 픽셀 1%")         # 연속 판정: 매번 1회
        self.ag.on_status(roi.id, "ok", "[정지 판정 10:00:00] OK")
        self.ag.on_status(roi.id, "ok", "[정지 판정 10:00:00] OK")  # 같은 정지 결과 유지: 안 셈
        self.ag.on_status(roi.id, "moving", "움직임")
        self.assertEqual(self.ag.stats[roi.id].inspections, 4)
        self.alert(roi)
        k = self.ag.kpis()
        self.assertEqual((k["inspections"], k["ng"]), (4, 1))
        self.assertAlmostEqual(k["ok_rate"], 75.0)

    def test_auto_restart_limited(self):
        for i in range(agent.RESTART_LIMIT):
            self.clock.t += 60
            self.assertEqual([a.kind for a in self.ag.on_monitor_stopped("오류로 중지됨: x", True)], ["restart"])
        self.clock.t += 60
        self.assertEqual([a.kind for a in self.ag.on_monitor_stopped("오류로 중지됨: x", True)], ["teams"])
        self.assertEqual(self.ag.on_monitor_stopped("사용자 중지", True), [])
        self.clock.t += 3600 * 2
        self.assertEqual([a.kind for a in self.ag.on_monitor_stopped("오류로 중지됨: x", True)], ["restart"])
        self.assertEqual(self.ag.on_monitor_stopped("오류로 중지됨: x", False), [])

    def test_shift_due_once(self):
        from datetime import datetime
        self.clock.t = datetime(2026, 10, 7, 8, 0, 30).timestamp()
        self.assertEqual(self.ag.due_shift("08:00, 20:00"), "2026-10-07 08:00")
        self.assertIsNone(self.ag.due_shift("08:00,20:00"))
        self.clock.t = datetime(2026, 10, 7, 9, 0, 0).timestamp()
        self.assertIsNone(self.ag.due_shift("08:00,20:00,bad,25:99"))

    def test_report_and_feedback(self):
        self.ag.on_status(self.rois[0].id, "ok", "x")
        self.alert(self.rois[1])
        self.ag.on_feedback("cam1", "ok", 0.42, 0.47)
        html_text = self.ag.report_html("리포트 <테스트>", self.rois)
        self.assertIn("&lt;테스트&gt;", html_text)
        self.assertIn("cam1", html_text)
        self.assertIn("재보정 0.42 ↑ 0.47", html_text)
        self.assertIn("NG 1건", self.ag.report_summary())


class HousekeepingAndTrendTests(unittest.TestCase):
    def test_purge_old_files(self):
        import housekeeping
        with tempfile.TemporaryDirectory() as d:
            old, new = os.path.join(d, "old.png"), os.path.join(d, "new.png")
            for p in (old, new):
                open(p, "w").close()
            now = 1_760_000_000.0
            os.utime(old, (now - 16 * 86400, now - 16 * 86400))
            os.utime(new, (now - 14 * 86400, now - 14 * 86400))
            self.assertEqual(housekeeping.purge_old_files([d, os.path.join(d, "none")], 15, now=now), 1)
            self.assertEqual(os.listdir(d), ["new.png"])

    def test_roi_trends_and_report_images(self):
        clock = FakeClock()
        ag = agent.VisionAgent(clock=clock)
        rois = [config.ROI(name="A"), config.ROI(name="B")]
        ag.boot(rois, {})
        with tempfile.TemporaryDirectory() as d:
            snap = os.path.join(d, "ng.png")
            worker.save_png(solid((200, 0, 0), 60, 80), snap)
            ag.on_alert({"roi_id": rois[0].id, "roi_name": "A", "kind": "alert", "detail": "NG", "snapshot": snap})
            clock.t += 3600
            ag.on_alert({"roi_id": rois[0].id, "roi_name": "A", "kind": "alert", "detail": "NG", "snapshot": snap})
            trends = {t["name"]: t for t in ag.roi_trends(rois)}
            self.assertEqual((trends["A"]["recent"], trends["B"]["recent"]), (2, 0))
            self.assertEqual([c for _h, c in trends["A"]["series"]][-2:], [1, 1])
            html_text = ag.report_html("리포트", rois, frames={rois[1].id: solid(90, 40, 60)})
            self.assertEqual(html_text.count("data:image/jpeg;base64,"), 3)   # NG 2장 + 현재 화면 1장
            self.assertIn("NG 탐지 이미지 (2장", html_text)
        # 스냅샷이 지워져도 리포트 생성은 실패하지 않음
        self.assertIn("NG 탐지 이미지 (0장", ag.report_html("리포트", rois))

    def test_resize_samples_keeps_files(self):
        import paths
        with tempfile.TemporaryDirectory() as d, mock.patch.object(paths, "REF_DIR", d):
            for cls in ("ok", "ng", "skip"):
                worker.save_png(noise(100, 200), paths.new_reference_path("r1", cls))
            self.assertEqual(worker.resize_samples("r1", 150, 80), 3)
            samples = worker.load_samples("r1")
            self.assertEqual({a.shape[:2] for v in samples.values() for a in v}, {(80, 150)})
            self.assertEqual(worker.resize_samples("r1", 150, 80), 0)

    def test_new_settings_clamped(self):
        cfg = config.config_from_dict({"version": 2, "popup_consecutive": 0, "retention_days": 40,
                                       "mini_position": "top"})
        self.assertEqual((cfg.popup_consecutive, cfg.retention_days, cfg.mini_position), (1, 15, "auto"))
        cfg = config.config_from_dict({"version": 2, "popup_consecutive": 3, "retention_days": 7,
                                       "mini_position": "left"})
        self.assertEqual((cfg.popup_consecutive, cfg.retention_days, cfg.mini_position), (3, 7, "left"))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "settings.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        cfg = config.AppConfig(webhook_url="https://example.com/hook", teams_enabled=True)
        cfg.rois.append(config.ROI(name="1번", x=-1920, y=10, w=320, h=180, detector="color",
                                   params={"rgb": [0, 0, 255], "tolerance": 30, "ratio": 0.4},
                                   assignee="홍길동", assignee_email="hong@example.com"))
        config.save(cfg, self.path)
        loaded = config.load(self.path)
        self.assertEqual(loaded.rois[0].x, -1920)
        self.assertEqual(loaded.rois[0].params["tolerance"], 30.0)
        self.assertEqual(loaded.rois[0].assignee, "홍길동")
        self.assertTrue(loaded.teams_enabled)

    def test_migrate_v1_single_roi(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"roi": {"left": 100, "top": 200, "width": 300, "height": 150},
                       "black_threshold": 25, "dark_ratio": 0.9, "process_name": "NVR_VIEWER.exe"}, f)
        cfg = config.load(self.path)
        self.assertEqual(len(cfg.rois), 1)
        r = cfg.rois[0]
        self.assertEqual((r.x, r.y, r.w, r.h), (100, 200, 300, 150))
        self.assertEqual(r.params, {"threshold": 25.0, "ratio": 0.9})
        self.assertEqual(r.expected_process, "NVR_VIEWER.exe")
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "settings.v1.bak.json")))
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], config.CONFIG_VERSION)

    def test_broken_file(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertEqual(config.load(self.path).rois, [])

    def test_still_fields_roundtrip(self):
        cfg = config.AppConfig()
        cfg.rois.append(config.ROI(still_only=True, still_diff=4.5, still_frames=3))
        config.save(cfg, self.path)
        r = config.load(self.path).rois[0]
        self.assertEqual((r.still_only, r.still_diff, r.still_frames), (True, 4.5, 3))
        old = config.roi_from_dict({"name": "x", "still_frames": 99})
        self.assertEqual((old.still_only, old.still_frames), (False, 20))

    def test_webhook_override(self):
        cfg = config.AppConfig(webhook_url="https://common")
        self.assertEqual(cfg.webhook_for(config.ROI()), "https://common")
        self.assertEqual(cfg.webhook_for(config.ROI(webhook_url="https://own")), "https://own")


class FakeGrabber:
    def __init__(self, frames):
        self.frames = frames

    def grab(self, x, y, w, h):
        return self.frames.pop(0)


class WorkerFlowTests(unittest.TestCase):
    """지속 시간 → 경보 1회 → 복구 흐름과 Teams 전송 여부."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(worker.paths, "SNAPSHOT_DIR", self.tmp.name)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def run_ticks(self, cfg, frames, times):
        events = queue.Queue()
        teams = mock.Mock()
        mon = worker.Monitor(cfg, events, teams)
        grabber = FakeGrabber(frames)
        mon._clock = iter(times).__next__
        for _ in times:
            mon._tick(cfg, grabber)
        out = []
        while not events.empty():
            out.append(events.get())
        return out, teams

    def test_alert_once_then_recover(self):
        roi = config.ROI(name="cam1", duration_sec=5, assignee="담당", assignee_email="a@b.c")
        cfg = config.AppConfig(teams_enabled=True, webhook_url="https://hook")
        cfg.rois.append(roi)
        dark, normal = solid(0), noise()
        events, teams = self.run_ticks(cfg, [dark, dark, dark, dark, normal],
                                       [100.0, 103.0, 106.0, 110.0, 111.0])
        states = [e[2] for e in events if e[0] == "status"]
        self.assertEqual(states, ["pending", "pending", "alarm", "alarm", "ok"])
        kinds = [e[0] for e in events if e[0] in ("alert", "recover")]
        self.assertEqual(kinds, ["alert", "recover"])
        self.assertEqual(teams.send.call_count, 2)
        url, payload, _label = teams.send.call_args_list[0].args
        self.assertEqual(url, "https://hook")
        self.assertEqual(payload["assignee_email"], "a@b.c")
        self.assertEqual(payload["event"], "alert")
        alert_info = next(e[1] for e in events if e[0] == "alert")
        self.assertTrue(os.path.exists(alert_info["snapshot"]))
        self.assertTrue(os.path.exists(alert_info["raw_snapshot"]))
        self.assertEqual(alert_info["roi_detector"], "black")

    def test_repeat_and_teams_disabled(self):
        roi = config.ROI(name="cam2", duration_sec=0, repeat_min=1)
        cfg = config.AppConfig(teams_enabled=False)
        cfg.rois.append(roi)
        dark = solid(0)
        events, teams = self.run_ticks(cfg, [dark] * 3, [0.0, 30.0, 61.0])
        alerts = [e[1]["kind"] for e in events if e[0] == "alert"]
        self.assertEqual(alerts, ["alert", "repeat"])
        teams.send.assert_not_called()

    def test_union_capture_for_many_rois(self):
        cfg = config.AppConfig()
        for i in range(5):
            cfg.rois.append(config.ROI(name=f"cam{i}", x=10 + i * 50, y=20, w=40, h=30, duration_sec=99))
        screen = noise(100, 400)
        screen[20:50, 60:100] = 0                      # cam1 위치만 검은 화면

        class Recorder:
            calls = []

            def grab(self, x, y, w, h):
                self.calls.append((x, y, w, h))
                return screen[y:y + h, x:x + w]

        events = queue.Queue()
        mon = worker.Monitor(cfg, events, mock.Mock())
        grabber = Recorder()
        mon._tick(cfg, grabber)
        self.assertEqual(grabber.calls, [(10, 20, 240, 30)])   # 한 번만 캡처
        states = {}
        while not events.empty():
            e = events.get()
            if e[0] == "status":
                states[e[1]] = e[2]
        self.assertEqual(states[cfg.rois[1].id], "pending")
        self.assertEqual(states[cfg.rois[0].id], "ok")

    def test_still_only_inspects_once_per_stop(self):
        roi = config.ROI(name="line", still_only=True, still_diff=3.0, still_frames=1, duration_sec=99)
        cfg = config.AppConfig()
        cfg.rois.append(roi)
        dark = solid(0)
        good1, good2 = noise(seed=7), noise(seed=8)
        frames = [noise(seed=1), noise(seed=2),          # 움직임 (판정 안 함)
                  dark, dark, dark,                       # 정지(NG): 첫 정지 확인 시 1회만 경보
                  noise(seed=3), good1, good1,            # 움직임 → 정지(OK): 복구
                  noise(seed=4), dark, dark]              # 다시 NG 정지 → 새 경보
        events, _ = self.run_ticks(cfg, frames, [float(i) for i in range(len(frames))])
        states = [e[2] for e in events if e[0] == "status"]
        self.assertEqual(states, ["moving", "moving", "moving", "alarm", "alarm", "moving", "moving", "ok",
                                  "moving", "moving", "alarm"])
        kinds = [e[0] for e in events if e[0] in ("alert", "recover")]
        self.assertEqual(kinds, ["alert", "recover", "alert"])

    def test_still_empty_screen_not_judged(self):
        """셀이 없는 정지 화면은 판정하지 않고, 셀이 들어와 멈추면 판정."""
        roi = config.ROI(name="cell", detector="shape", w=320, h=240, still_only=True, still_frames=1)
        cfg = config.AppConfig()
        cfg.rois.append(roi)
        empty, cell, folded = tab_image(th=0, seed=1), tab_image(seed=2), tab_image(fold=0.4, seed=3)
        with mock.patch.object(worker.Monitor, "_references",
                               return_value={"ok": [tab_image(seed=9)], "ng": [], "skip": []}):
            events, _ = self.run_ticks(cfg, [empty, empty, empty, cell, cell, empty, folded, folded],
                                       [float(i) for i in range(8)])
        states = [e[2] for e in events if e[0] == "status"]
        self.assertEqual(states, ["moving", "wait", "wait", "moving", "ok", "moving", "moving", "alarm"])
        self.assertEqual([e[0] for e in events if e[0] in ("alert", "recover")], ["alert"])

    def test_still_frames_requires_consecutive_stillness(self):
        roi = config.ROI(name="line", still_only=True, still_diff=3.0, still_frames=3)
        cfg = config.AppConfig()
        cfg.rois.append(roi)
        dark = solid(0)
        events, _ = self.run_ticks(cfg, [noise(seed=1), dark, dark, dark, dark], [0.0, 1.0, 2.0, 3.0, 4.0])
        states = [e[2] for e in events if e[0] == "status"]
        self.assertEqual(states, ["moving", "moving", "moving", "moving", "alarm"])

    def test_thumbnails_sent_when_enabled(self):
        cfg = config.AppConfig()
        cfg.rois.append(config.ROI(name="cam", w=640, h=480))
        events = queue.Queue()
        mon = worker.Monitor(cfg, events, mock.Mock())
        mon.send_frames = True
        grabber = FakeGrabber([noise(480, 640), noise(480, 640)])
        mon._tick(cfg, grabber)
        mon._tick(cfg, grabber)                                  # 1초 안 → 다시 보내지 않음
        frames = [e for e in list(events.queue) if e[0] == "frame"]
        self.assertEqual(len(frames), 1)
        self.assertLessEqual(max(frames[0][2].shape[:2]), worker.THUMB_MAX_SIDE)

    def test_disabled_roi_not_captured(self):
        cfg = config.AppConfig()
        cfg.rois.append(config.ROI(enabled=False))
        events, _ = self.run_ticks(cfg, [], [0.0])
        self.assertEqual(events[0][2], "off")


class WallLayoutTests(unittest.TestCase):
    def test_parse_wall(self):
        self.assertEqual(config.parse_wall([10, 20, 400, 300]), [10, 20, 400, 300])
        self.assertEqual(config.parse_wall([-5, 3.6, 10, 99999]), [0, 4, config.WALL_MIN[0], config.WALL_MAX[1]])
        for bad in (None, [], [1, 2, 3], "x", [1, 2, "a", 4]):
            self.assertEqual(config.parse_wall(bad), [])

    def test_roundtrip_and_signature(self):
        roi = config.ROI(name="A", wall=[8, 16, 320, 180])
        back = config.roi_from_dict(json.loads(json.dumps(config.asdict(roi))))
        self.assertEqual(back.wall, [8, 16, 320, 180])
        moved = config.roi_from_dict(dict(config.asdict(roi), wall=[100, 100, 400, 240]))
        self.assertEqual(moved.signature(), back.signature())     # 카드 배치는 판정 상태를 초기화하지 않음
        self.assertEqual(config.roi_from_dict({"name": "old"}).wall, [])


def occlusion_window(process, rect, own=False):
    return mock.Mock(process=process, rect=rect, own=own)


class OcclusionTests(unittest.TestCase):
    """ROI를 실제로 덮은 창이 있을 때만 건너뛴다."""
    ROI = (200, 200, 100, 80)                       # x 200~300, y 200~280

    @staticmethod
    def win(process, rect, own=False):
        return occlusion_window(process, rect, own)

    def check(self, *windows):
        return occlusion.roi_visibility(self.ROI, list(windows), "NVR.exe")

    def test_visible_when_dashboard_does_not_overlap(self):
        dash = self.win("FMVS_Vision_Agent.exe", (300, 0, 1200, 900), own=True)    # ROI 오른쪽에 딱 붙음
        res = self.check(dash, self.win("nvr.EXE", (0, 0, 1920, 1080)))
        self.assertTrue(res.ok, res.detail)

    def test_edge_rounding_is_not_cover(self):
        near = self.win("chrome.exe", (298, 0, 900, 900))                           # 2px 겹침 = 테두리 오차
        self.assertTrue(self.check(near, self.win("NVR.exe", (0, 0, 1920, 1080))).ok)

    def test_partial_cover_by_dashboard_skips(self):
        dash = self.win("FMVS_Vision_Agent.exe", (250, 0, 1200, 900), own=True)
        res = self.check(dash, self.win("NVR.exe", (0, 0, 1920, 1080)))
        self.assertFalse(res.ok)
        self.assertIn(occlusion.OWN_LABEL, res.detail)
        self.assertAlmostEqual(res.covered_pct, 50, delta=4)

    def test_window_below_target_is_ignored(self):
        res = self.check(self.win("NVR.exe", (0, 0, 1920, 1080)), self.win("explorer.exe", (0, 0, 1920, 1080)))
        self.assertTrue(res.ok)

    def test_target_child_windows_count_as_target(self):
        res = self.check(self.win("NVR.exe", (210, 210, 260, 260)), self.win("NVR.exe", (0, 0, 1920, 1080)))
        self.assertTrue(res.ok)

    def test_target_missing(self):
        res = self.check(self.win("notepad.exe", (0, 0, 1920, 1080)))
        self.assertFalse(res.ok)
        self.assertIn("notepad.exe", res.detail)

    def test_roi_outside_target_window(self):
        res = self.check(self.win("NVR.exe", (0, 0, 250, 1080)))
        self.assertFalse(res.ok)
        self.assertIn("창 밖", res.detail)

    def test_large_roi_uses_coarse_grid(self):
        roi = (0, 0, 3000, 2000)
        wins = [self.win("a.exe", (0, 0, 1500, 2000)), self.win("NVR.exe", (0, 0, 3000, 2000))]
        res = occlusion.roi_visibility(roi, wins, "nvr.exe")
        self.assertFalse(res.ok)
        self.assertAlmostEqual(res.covered_pct, 50, delta=1)

    def test_worker_skips_only_when_covered(self):
        cfg = config.AppConfig()
        roi = config.ROI(name="A", x=200, y=200, w=100, h=80, detector="black", expected_process="NVR.exe")
        cfg.rois = [roi]
        events = queue.Queue()
        mon = worker.Monitor(cfg, events, mock.Mock())
        windows = [self.win("FMVS.exe", (400, 0, 900, 900), own=True), self.win("NVR.exe", (0, 0, 1920, 1080))]
        with mock.patch.object(worker.winutil, "IS_WINDOWS", True), \
                mock.patch.object(worker.winutil, "visible_windows", return_value=windows):
            mon._tick(cfg, FakeGrabber([solid((200, 200, 200), 80, 100)]))
            windows.insert(0, self.win("FMVS.exe", (150, 150, 260, 260), own=True))
            mon._tick(cfg, FakeGrabber([solid((200, 200, 200), 80, 100)]))
        states = [e[2] for e in list(events.queue) if e[0] == "status"]
        self.assertNotEqual(states[0], "skip")
        self.assertEqual(states[-1], "skip")


class NotifierTests(unittest.TestCase):
    def test_payload(self):
        p = notifier.build_payload("alert", roi_name="1번", detector_label="흑화면", detail="99%",
                                   assignee="홍길동", assignee_email="hong@example.com",
                                   pc_label="PC1", when="2026-10-06 12:00:00", elapsed_sec=75)
        json.dumps(p, ensure_ascii=False)
        card = p["attachments"][0]
        self.assertEqual(card["contentType"], "application/vnd.microsoft.card.adaptive")
        facts = {f["title"]: f["value"] for f in card["content"]["body"][2]["facts"]}
        self.assertEqual(facts["지속 시간"], "1분 15초")
        self.assertIn("hong@example.com", facts["담당자"])

    def test_validate_url(self):
        self.assertIsNotNone(notifier.validate_url(""))
        self.assertIsNotNone(notifier.validate_url("http://x"))
        self.assertIsNone(notifier.validate_url("https://x"))

    def test_retry_then_fail_reports(self):
        reports = []
        n = notifier.TeamsNotifier(lambda lvl, msg: reports.append((lvl, msg)))
        with mock.patch.object(notifier, "RETRY_DELAYS", (0, 0)), \
                mock.patch.object(notifier, "post_json", side_effect=OSError("timeout")) as post:
            n._deliver("https://x", {}, "t")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(reports[-1][0], "error")


if __name__ == "__main__":
    unittest.main()

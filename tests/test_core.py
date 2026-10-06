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

import config  # noqa: E402
import detectors  # noqa: E402
import notifier  # noqa: E402
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
        self.assertTrue(self.ev(empty, ref).abnormal)          # 감지 조건 없으면 '없음'도 불량
        flat = np.full((240, 320, 3), 90, dtype=np.uint8)
        self.assertIsNone(self.ev(tab_image(seed=2), flat).abnormal)
        self.assertIsNone(self.ev(tab_image(seed=2), None).abnormal)

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

    def test_disabled_roi_not_captured(self):
        cfg = config.AppConfig()
        cfg.rois.append(config.ROI(enabled=False))
        events, _ = self.run_ticks(cfg, [], [0.0])
        self.assertEqual(events[0][2], "off")


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

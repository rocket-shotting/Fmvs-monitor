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

    def test_repeat_and_teams_disabled(self):
        roi = config.ROI(name="cam2", duration_sec=0, repeat_min=1)
        cfg = config.AppConfig(teams_enabled=False)
        cfg.rois.append(roi)
        dark = solid(0)
        events, teams = self.run_ticks(cfg, [dark] * 3, [0.0, 30.0, 61.0])
        alerts = [e[1]["kind"] for e in events if e[0] == "alert"]
        self.assertEqual(alerts, ["alert", "repeat"])
        teams.send.assert_not_called()

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

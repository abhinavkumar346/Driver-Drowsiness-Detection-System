"""
Tests that need NO camera and NO Arduino.
Run from the project folder:   python -m unittest discover -s tests -v

A FakeBoard pretends to be the Arduino (same replies as pan_tilt_serial.ino)
and a FakeClock lets the tests jump forward in time instantly.
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import serial

from pages import Arduino
from pages.alert import DrowsinessAlert
from pages.pantilt import PanTilt
from pages.processing_info import FaceMetrics, PanTiltCalculator


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeBoard:
    """Stands in for serial.Serial. Records every line it receives."""
    plugged_in = True
    log = []

    def __init__(self, port, baud, timeout=None, write_timeout=None):
        if not FakeBoard.plugged_in:
            raise serial.SerialException("port not found")
        self.is_open = True
        self._out = [b"READY\n"]

    def readline(self):
        return self._out.pop(0) if self._out else b""

    def reset_input_buffer(self):
        self._out.clear()

    def write(self, data):
        if not FakeBoard.plugged_in:
            raise serial.SerialException("device disconnected")
        line = data.decode().strip()
        FakeBoard.log.append(line)
        parts = line.split(",")
        ok = len(parts) == 3 and all(p.lstrip("-").isdigit() for p in parts)
        self._out.append(b"OK\n" if ok else b"ERR\n")

    def close(self):
        self.is_open = False


class ArduinoLinkTests(unittest.TestCase):
    def setUp(self):
        FakeBoard.plugged_in = True
        FakeBoard.log = []
        Arduino.close_all()
        self.clock = FakeClock()
        patches = [
            mock.patch("pages.Arduino.serial.Serial", FakeBoard),
            mock.patch("time.monotonic", self.clock.monotonic),
            mock.patch("time.sleep", lambda s: None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(Arduino.close_all)

    def test_message_format_rounding_and_clamping(self):
        self.assertEqual(Arduino.send_state("X", 95.4, 79.6, True, read_reply=True), "OK")
        Arduino.send_state("X", 999, -50, 0)
        self.assertEqual(FakeBoard.log, ["95,80,1", "180,0,0"])

    def test_connects_and_tracks_with_limited_steps(self):
        pt = PanTilt(port="X")
        self.assertTrue(pt.connected)
        # Face far to the right and below centre -> big error, but each update is capped.
        self.clock.advance(0.2)
        pt.update(300, 200, 640, 480, False)
        self.assertLessEqual(pt.pan - 90, PanTiltCalculator.MAX_STEP_DEG + 1)
        self.assertGreater(pt.pan, 90)
        self.assertGreater(pt.tilt, 90)
        self.assertEqual(FakeBoard.log[-1].split(",")[2], "0")

    def test_deadband_and_no_face_hold_position(self):
        pt = PanTilt(port="X")
        self.clock.advance(0.2)
        pt.update(10, -10, 640, 480, False)          # inside deadband
        self.assertEqual((pt.pan, pt.tilt), (90, 90))
        self.clock.advance(0.2)
        pt.update(None, None, 640, 480, False)       # no face
        self.assertEqual((pt.pan, pt.tilt), (90, 90))

    def test_updates_are_rate_limited(self):
        pt = PanTilt(port="X")
        self.clock.advance(0.2)
        pt.update(300, 0, 640, 480, False)
        sent = len(FakeBoard.log)
        pt.update(300, 0, 640, 480, False)           # same instant: ignored
        self.assertEqual(len(FakeBoard.log), sent)

    def test_buzzer_on_and_heartbeat(self):
        pt = PanTilt(port="X")
        self.clock.advance(0.2)
        pt.update(None, None, 640, 480, True)
        self.assertEqual(FakeBoard.log[-1], "90,90,1")
        count = len(FakeBoard.log)
        self.clock.advance(0.3)
        pt.update(None, None, 640, 480, True)        # unchanged, not due yet
        self.assertEqual(len(FakeBoard.log), count)
        self.clock.advance(1.0)
        pt.update(None, None, 640, 480, True)        # heartbeat keeps the Arduino from timing out
        self.assertEqual(len(FakeBoard.log), count + 1)

    def test_unplug_then_replug_recovers(self):
        pt = PanTilt(port="X")
        FakeBoard.plugged_in = False
        self.clock.advance(0.2)
        pt.update(300, 0, 640, 480, True)
        self.assertFalse(pt.connected)
        self.clock.advance(1.0)
        pt.update(300, 0, 640, 480, True)            # too soon to retry
        self.assertFalse(pt.connected)
        FakeBoard.plugged_in = True
        self.clock.advance(6.0)
        pt.update(300, 0, 640, 480, True)
        self.assertTrue(pt.connected)

    def test_missing_arduino_does_not_crash(self):
        FakeBoard.plugged_in = False
        pt = PanTilt(port="X")
        self.assertFalse(pt.connected)
        pt.update(300, 0, 640, 480, True)
        pt.close()

    def test_close_recentres_and_silences(self):
        pt = PanTilt(port="X")
        pt.close()
        self.assertEqual(FakeBoard.log[-1], "90,90,0")


class AlertAndMetricsTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        p = mock.patch("time.monotonic", self.clock.monotonic)
        p.start()
        self.addCleanup(p.stop)

    def test_long_eye_closure_triggers_and_holds_ten_seconds(self):
        alert = DrowsinessAlert()
        self.assertFalse(alert.update(0.0, True, True))
        self.clock.advance(2.1)
        self.assertTrue(alert.update(0.0, True, True))
        self.clock.advance(5.0)
        self.assertTrue(alert.update(0.0, False, True))   # eyes open, still held
        self.clock.advance(6.0)
        self.assertFalse(alert.update(0.0, False, True))  # hold expired

    def test_blink_does_not_trigger(self):
        alert = DrowsinessAlert()
        alert.update(0.0, True, True)
        self.clock.advance(0.3)
        self.assertFalse(alert.update(0.0, False, True))

    def test_perclos_trigger(self):
        self.assertTrue(DrowsinessAlert().update(0.35, False, True))

    def test_losing_the_face_resets_the_closure_timer(self):
        alert = DrowsinessAlert()
        alert.update(0.0, True, True)
        self.clock.advance(1.5)
        alert.update(0.0, True, False)
        self.clock.advance(1.0)
        self.assertFalse(alert.update(0.0, True, True))

    def test_perclos_ignores_frames_without_a_face(self):
        m = FaceMetrics()
        for _ in range(100):                       # 20 s of closed eyes at 5 fps
            m.update_perclos(True)
            self.clock.advance(0.2)
        self.assertGreater(m.get_perclos(), 0.9)
        before = m.get_perclos()
        self.clock.advance(5.0)                    # face gone for 5 s: no fake "open" frames
        self.assertAlmostEqual(m.get_perclos(), before)

    def test_perclos_warmup_returns_zero(self):
        m = FaceMetrics()
        m.update_perclos(True)
        self.clock.advance(2.0)
        self.assertEqual(m.update_perclos(True), 0.0)

    def test_ear_math(self):
        def lm(x, y):
            return SimpleNamespace(x=x, y=y)
        pts = {i: lm(0, 0) for i in range(500)}
        # open eye: width 0.1, height 0.04 -> EAR 0.4
        for idx, (x, y) in zip(FaceMetrics.LEFT_EYE,
                               [(0.0, 0.5), (0.03, 0.48), (0.07, 0.48),
                                (0.1, 0.5), (0.07, 0.52), (0.03, 0.52)]):
            pts[idx] = lm(x, y)
        ear = FaceMetrics().eye_aspect_ratio(pts, FaceMetrics.LEFT_EYE, 100, 100)
        self.assertAlmostEqual(ear, 0.4, places=3)


if __name__ == "__main__":
    unittest.main()

import time
from collections import deque

import numpy as np


class FaceMetrics:
    LEFT_EYE = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [263, 387, 385, 362, 380, 373]
    MOUTH = [61, 39, 269, 291, 405, 181]
    EAR_THRESHOLD = 0.21
    MAR_THRESHOLD = 0.6
    PERCLOS_WINDOW_SECONDS = 60
    PERCLOS_WARMUP_SECONDS = 10

    def __init__(self):
        self.perclos_window = deque()   # (timestamp, eye_closed) for every frame with a face

    # Optional: not used by the main code. Kept in case we want to test
    # running the face mesh on a cropped face instead of the full frame.
    def crop_face(self, frame, face_coordinates):
        x, y, w, h = face_coordinates
        frame_h, frame_w = frame.shape[:2]
        x, y = max(0, x), max(0, y)
        x2, y2 = min(frame_w, x + w), min(frame_h, y + h)
        if x2 <= x or y2 <= y:
            return None
        return frame[y:y2, x:x2]

    def eye_aspect_ratio(self, landmarks, eye_indices, frame_w, frame_h):
        pts = []
        for idx in eye_indices:
            lm = landmarks[idx]
            pts.append(np.array([lm.x * frame_w, lm.y * frame_h]))
        p1, p2, p3, p4, p5, p6 = pts
        vertical_1 = np.linalg.norm(p2 - p6)
        vertical_2 = np.linalg.norm(p3 - p5)
        horizontal = np.linalg.norm(p1 - p4)
        if horizontal == 0:
            return 0.0
        return (vertical_1 + vertical_2) / (2.0 * horizontal)

    def mouth_aspect_ratio(self, landmarks, frame_w, frame_h):
        pts = []
        for idx in self.MOUTH:
            lm = landmarks[idx]
            pts.append(np.array([lm.x * frame_w, lm.y * frame_h]))
        p1, p2, p3, p4, p5, p6 = pts
        vertical_1 = np.linalg.norm(p2 - p6)
        vertical_2 = np.linalg.norm(p3 - p5)
        horizontal = np.linalg.norm(p1 - p4)
        if horizontal == 0:
            return 0.0
        return (vertical_1 + vertical_2) / (2.0 * horizontal)

    def process(self, results, frame_w, frame_h):
        """Returns (avg_ear, mar, eye_closed, yawning). avg_ear is None when no face is found."""
        if not results.multi_face_landmarks:
            return None, None, False, False

        landmarks = results.multi_face_landmarks[0].landmark

        left_ear = self.eye_aspect_ratio(landmarks, self.LEFT_EYE, frame_w, frame_h)
        right_ear = self.eye_aspect_ratio(landmarks, self.RIGHT_EYE, frame_w, frame_h)
        avg_ear = (left_ear + right_ear) / 2.0
        eye_closed = avg_ear < self.EAR_THRESHOLD

        mar = self.mouth_aspect_ratio(landmarks, frame_w, frame_h)
        yawning = mar > self.MAR_THRESHOLD

        return avg_ear, mar, eye_closed, yawning

    def update_perclos(self, eye_closed):
        """Record one frame that HAS a face, then return the current PERCLOS (0.0 to 1.0)."""
        self.perclos_window.append((time.monotonic(), eye_closed))
        return self.get_perclos()

    def get_perclos(self):
        """
        Current PERCLOS: fraction of recent frames with the eyes closed.
        Safe to call on frames with no face (they are simply not counted,
        so looking away never lowers PERCLOS by adding fake 'eyes open' frames).
        """
        now = time.monotonic()

        while self.perclos_window and now - self.perclos_window[0][0] > self.PERCLOS_WINDOW_SECONDS:
            self.perclos_window.popleft()

        if not self.perclos_window:
            return 0.0

        # not enough history yet: a single blink would look like 100% PERCLOS
        if now - self.perclos_window[0][0] < self.PERCLOS_WARMUP_SECONDS:
            return 0.0

        closed_count = sum(1 for _, closed in self.perclos_window if closed)
        return closed_count / len(self.perclos_window)

    def reset_perclos(self):
        self.perclos_window.clear()


class PanTiltCalculator:
    # ---------- SETTINGS (change these to match your hardware) ----------
    HFOV_DEG = 60.0              # camera horizontal field of view in degrees (check your camera)
    VFOV_DEG = 40.0              # camera vertical field of view in degrees
    KP = 0.4                     # correction strength: 0.1 = slow and smooth, 1.0 = aggressive
    DEADBAND_PX = 25             # ignore offsets smaller than this many pixels (stops jitter)
    MAX_STEP_DEG = 4.0           # biggest angle change per update. The sketch moves 1 degree every
                                 # 15 ms (about 66 deg/s), so 4 deg per 0.1 s update never outruns it.
                                 # Without this limit the target races ahead of the servo and overshoots.
    PAN_DIR = -1                  # change to -1 if the mount pans the wrong way
    TILT_DIR = -1                 # change to -1 if the mount tilts the wrong way
    PAN_MIN, PAN_MAX = 0, 180    # same as the Arduino sketch
    TILT_MIN, TILT_MAX = 40, 140 # same as the Arduino sketch

    def __init__(self):
        self.pan = 90.0          # current pan angle (start centered)
        self.tilt = 90.0         # current tilt angle (start centered)

    @staticmethod
    def _clamp(value, low, high):
        """Force a number to stay between low and high."""
        return max(low, min(high, value))

    def pixel_to_angle(self, offset_px, frame_size_px, fov_deg):
        """Pixels -> degrees: fraction of the frame size times the field of view."""
        return offset_px / frame_size_px * fov_deg

    def _step(self, offset_px, frame_size_px, fov_deg):
        """Angle change for one axis: proportional, then limited to +/- MAX_STEP_DEG."""
        error_deg = self.pixel_to_angle(offset_px, frame_size_px, fov_deg)
        return self._clamp(self.KP * error_deg, -self.MAX_STEP_DEG, self.MAX_STEP_DEG)

    def update(self, dx, dy, frame_w, frame_h):
        """
        dx, dy   : face center minus frame center in pixels (None when no face)
        frame_w/h: frame size in pixels
        Returns the new (pan, tilt) as whole numbers. With no face, the mount holds its position.
        """
        if dx is not None and dy is not None:
            if abs(dx) > self.DEADBAND_PX:     # big enough offset to bother correcting
                step = self._step(dx, frame_w, self.HFOV_DEG)
                self.pan = self._clamp(self.pan + self.PAN_DIR * step,
                                       self.PAN_MIN, self.PAN_MAX)
            if abs(dy) > self.DEADBAND_PX:
                step = self._step(dy, frame_h, self.VFOV_DEG)
                self.tilt = self._clamp(self.tilt + self.TILT_DIR * step,
                                        self.TILT_MIN, self.TILT_MAX)

        return int(round(self.pan)), int(round(self.tilt))

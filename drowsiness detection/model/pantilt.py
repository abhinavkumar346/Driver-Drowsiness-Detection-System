"""
model/pantilt.py
Turns the face offset (dx, dy) and the drowsiness alert into messages for the Arduino.

Used from main.py like this:
    pantilt = PanTilt()                                   # once, before the loop
    pantilt.update(dx, dy, frame_w, frame_h, alert)       # once per frame
    pantilt.close()                                       # once, at the end
"""

import time

import serial                              # only needed for its error type

from model.ArduinoConnect import send_state, close_all

# ---------- SETTINGS (change these to match your hardware) ----------
PORT = "COM4"                # default port if none is given (Tools > Port in the Arduino IDE)
USE_HARDWARE = True          # False = run the vision code with no Arduino connected

HFOV_DEG = 60.0              # camera horizontal field of view in degrees (check your camera)
VFOV_DEG = 40.0              # camera vertical field of view in degrees
KP = 0.4                     # correction strength: 0.1 = slow and smooth, 1.0 = aggressive
DEADBAND_PX = 25             # ignore offsets smaller than this many pixels (stops jitter)

PAN_DIR = 1                  # change to -1 if the mount pans the wrong way
TILT_DIR = 1                 # change to -1 if the mount tilts the wrong way

PAN_MIN, PAN_MAX = 0, 180    # same as the Arduino sketch
TILT_MIN, TILT_MAX = 40, 140 # same as the Arduino sketch

SEND_INTERVAL = 0.1          # seconds between messages (0.1 = at most 10 per second)
HEARTBEAT = 1.0              # resend the same state at least this often (seconds); the Arduino
                             # switches the buzzer off after 5 s of silence


def _clamp(value, low, high):
    """Force a number to stay between low and high."""
    return max(low, min(high, value))


class PanTilt:
    def __init__(self, port=PORT):
        self.port = port                   # the COM port to use (None = run without the Arduino)
        self.pan = 90.0                    # current pan angle (start centered)
        self.tilt = 90.0                   # current tilt angle (start centered)
        self.last_sent = None              # last (pan, tilt, buzzer) sent to the board
        self.last_time = 0.0               # when the last message was sent
        self.enabled = USE_HARDWARE and port is not None   # becomes False if the Arduino cannot be reached

        if self.enabled:
            try:
                send_state(self.port, self.pan, self.tilt, False)   # open port, go to center
                self.last_sent = (90, 90, 0)
                self.last_time = time.time()
                print(f"[PanTilt] Connected to the Arduino on {self.port}")
            except (ConnectionError, serial.SerialException) as err:
                print(f"[PanTilt] Arduino not available, running without it: {err}")
                self.enabled = False

    def update(self, dx, dy, frame_w, frame_h, alert):
        """
        dx, dy   : face center minus frame center in pixels (None when no face)
        frame_w/h: frame size in pixels
        alert    : True while the drowsiness alert is active
        """
        # --- 1. Work out the new angles (only when a face is locked) ---
        if dx is not None and dy is not None:
            if abs(dx) > DEADBAND_PX:      # big enough offset to bother correcting
                # pixels -> degrees: fraction of the frame width times the field of view
                error_deg = dx / frame_w * HFOV_DEG
                self.pan = _clamp(self.pan + PAN_DIR * KP * error_deg, PAN_MIN, PAN_MAX)
            if abs(dy) > DEADBAND_PX:
                error_deg = dy / frame_h * VFOV_DEG
                self.tilt = _clamp(self.tilt + TILT_DIR * KP * error_deg, TILT_MIN, TILT_MAX)

        # --- 2. Send when something changed (and every second as a keep-alive) ---
        now = time.time()
        state = (int(round(self.pan)), int(round(self.tilt)), 1 if alert else 0)
        if not self.enabled:
            return
        changed = state != self.last_sent                  # angles or buzzer differ from last message
        heartbeat_due = now - self.last_time >= HEARTBEAT  # nothing sent for a while: repeat it
        if not (changed or heartbeat_due):
            return
        if now - self.last_time < SEND_INTERVAL:           # never faster than 10 messages per second
            return

        try:
            send_state(self.port, state[0], state[1], state[2])
            self.last_sent = state
            self.last_time = now
        except (ConnectionError, serial.SerialException) as err:
            print(f"[PanTilt] Lost the Arduino, continuing without it: {err}")
            self.enabled = False           # keep the detection running even if USB drops

    def close(self):
        """Re-center, switch the buzzer off and release the port."""
        if self.enabled:
            try:
                send_state(self.port, 90, 90, False)
            except (ConnectionError, serial.SerialException):
                pass
        close_all()

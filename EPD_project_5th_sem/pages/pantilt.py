"""
pantilt.py
Connects the vision code to the Arduino: keeps the pan-tilt mount pointed at the
face and switches the buzzer on and off.

The angle maths lives in PanTiltCalculator (processing_info.py). This file only
decides WHEN to send and handles the USB connection.

Used from main.py like this:
    pantilt = PanTilt()                                   # once, before the loop
    pantilt.update(dx, dy, frame_w, frame_h, alert)       # once per frame
    pantilt.close()                                       # once, at the end
"""

import time

import serial                              # only needed for its error type

from .Arduino import send_state, close_all, find_arduino_port
from .processing_info import PanTiltCalculator

CONNECTION_ERRORS = (ConnectionError, serial.SerialException, OSError)


class PanTilt:
    # ---------- SETTINGS ----------
    SEND_INTERVAL = 0.1          # seconds between angle updates (0.1 = at most 10 per second)
    HEARTBEAT = 1.0              # resend the same state at least this often (seconds); the Arduino
                                 # switches the buzzer off after 5 s of silence
    RECONNECT_INTERVAL = 5.0     # seconds between attempts to find the Arduino again after a failure

    def __init__(self, port=None, use_hardware=True):
        """
        port         : COM port name, or None to auto-detect the Arduino
        use_hardware : False = run the vision code with no Arduino connected
        """
        self.calculator = PanTiltCalculator()
        self.use_hardware = use_hardware
        self.port = port
        self.connected = False             # True only while the Arduino is answering
        self.last_sent = None              # last (pan, tilt, buzzer) sent to the board
        self.last_send_time = 0.0          # when the last message was sent
        self.last_update_time = 0.0        # when the angles were last recalculated
        self.last_connect_try = 0.0        # when we last tried to reach the Arduino

        if self.use_hardware:
            self.connect()

    @property
    def pan(self):
        return int(round(self.calculator.pan))

    @property
    def tilt(self):
        return int(round(self.calculator.tilt))

    @property
    def status_text(self):
        """Short text for the on-screen display."""
        if not self.use_hardware:
            return "Arduino: disabled"
        if self.connected:
            return f"Arduino: {self.port}"
        return "Arduino: NOT CONNECTED"

    def connect(self):
        """Try to open the port and check that our sketch answers. Returns True on success."""
        self.last_connect_try = time.monotonic()

        port = self.port or find_arduino_port()
        if port is None:
            print("[PanTilt] No Arduino found. Plug it in (or pass --port COM4).")
            return False

        try:
            # Send the current angles so a re-plugged board slides back to where we were.
            reply = send_state(port, self.calculator.pan, self.calculator.tilt,
                               False, read_reply=True)
        except CONNECTION_ERRORS as err:
            print(f"[PanTilt] Arduino not available: {err}")
            return False

        if reply != "OK":
            print(f"[PanTilt] {port} opened but the sketch did not answer 'OK' "
                  f"(got {reply!r}). Is pan_tilt_serial.ino uploaded, at 115200 baud?")
            close_all()
            return False

        self.port = port
        self.connected = True
        self.last_sent = (self.pan, self.tilt, 0)
        self.last_send_time = time.monotonic()
        print(f"[PanTilt] Connected to the Arduino on {self.port}")
        return True

    def update(self, dx, dy, frame_w, frame_h, alert):
        """
        dx, dy   : face center minus frame center in pixels (None when no face)
        frame_w/h: frame size in pixels
        alert    : True while the drowsiness alert is active
        Call it every frame; it only does real work every SEND_INTERVAL seconds.
        """
        now = time.monotonic()

        # --- 1. Slow down to the update rate (also keeps the correction steps small) ---
        if now - self.last_update_time < self.SEND_INTERVAL:
            return
        self.last_update_time = now

        # --- 2. Work out the new angles (the mount holds still if there is no face) ---
        pan, tilt = self.calculator.update(dx, dy, frame_w, frame_h)

        if not self.use_hardware:
            return

        # --- 3. Lost the Arduino? Try again now and then, without freezing the video ---
        if not self.connected:
            if now - self.last_connect_try >= self.RECONNECT_INTERVAL:
                self.connect()
            return

        # --- 4. Send when something changed (and every second as a keep-alive) ---
        state = (pan, tilt, 1 if alert else 0)
        changed = state != self.last_sent
        heartbeat_due = now - self.last_send_time >= self.HEARTBEAT
        if not (changed or heartbeat_due):
            return

        try:
            send_state(self.port, *state)
            self.last_sent = state
            self.last_send_time = now
        except CONNECTION_ERRORS as err:
            print(f"[PanTilt] Lost the Arduino, will keep retrying: {err}")
            self.connected = False
            self.last_connect_try = now

    def close(self):
        """Re-center, switch the buzzer off and release the port."""
        if self.connected:
            try:
                send_state(self.port, 90, 90, False)
            except CONNECTION_ERRORS:
                pass
            time.sleep(0.2)                # let the line leave the PC before the port closes
        close_all()
        self.connected = False

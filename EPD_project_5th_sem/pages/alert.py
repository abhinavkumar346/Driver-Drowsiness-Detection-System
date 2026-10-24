"""
alert.py
Decides WHEN the drowsiness alert (and so the buzzer) should be on.

The Arduino does the actual beeping; this file only answers "alert: yes or no?".
Used from main.py like this:
    alert = DrowsinessAlert()                                  # once, before the loop
    alert_on = alert.update(perclos, eye_closed, face_found)   # once per frame
"""

import time


class DrowsinessAlert:
    # ---------- SETTINGS ----------
    PERCLOS_THRESHOLD = 0.3      # alert when more than 30 % of the last minute had closed eyes
    EYES_CLOSED_SECONDS = 2.0    # ...or when the eyes stay closed this long without a break.
                                 # (PERCLOS alone needs ~18 s of closed eyes to reach 30 % of a
                                 # minute, far too slow for a driver.) Use None to turn this off.
    HOLD_SECONDS = 10.0          # once triggered, keep the alert on for at least this long

    def __init__(self):
        self.closed_since = None     # when the current run of closed eyes began (None = eyes open)
        self.active_until = 0.0      # alert stays on until this time

    def update(self, perclos, eye_closed, face_found):
        """
        perclos    : current PERCLOS, 0.0 to 1.0
        eye_closed : True if the eyes are closed in this frame
        face_found : False when no face was seen this frame
        Returns True while the alert should be on.
        """
        now = time.monotonic()

        # --- 1. Track how long the eyes have been closed in a row ---
        if face_found and eye_closed:
            if self.closed_since is None:
                self.closed_since = now          # a new run of closed eyes starts
        else:
            self.closed_since = None             # eyes open, or no face to judge

        # --- 2. Is there a reason to alert right now? ---
        triggered = perclos > self.PERCLOS_THRESHOLD
        if self.EYES_CLOSED_SECONDS is not None and self.closed_since is not None:
            if now - self.closed_since >= self.EYES_CLOSED_SECONDS:
                triggered = True

        # --- 3. Every trigger restarts the hold timer ---
        if triggered:
            self.active_until = now + self.HOLD_SECONDS

        return now < self.active_until

    def reset(self):
        """Switch the alert off immediately."""
        self.closed_since = None
        self.active_until = 0.0

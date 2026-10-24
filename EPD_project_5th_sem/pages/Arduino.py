"""
Arduino.py
Sends pan angle, tilt angle and buzzer state to an Arduino over USB serial.

Message format (one text line, ends with a newline):  pan,tilt,buzzer
Example: "95,80,1"  ->  pan 95, tilt 80, buzzer ON

The Arduino answers every valid line with "OK" (and "ERR" for a bad line).
Pairs with pan_tilt_serial/pan_tilt_serial.ino

Requires pyserial:  pip install pyserial
"""

import sys
import time

import serial                              # pyserial: talks to the COM port
from serial.tools import list_ports        # helper that lists connected ports

# ---------- SETTINGS ----------
DEFAULT_BAUD = 115200                      # must match Serial.begin(115200) in the sketch
PAN_MIN, PAN_MAX = 0, 180                  # allowed pan range sent to the Arduino
TILT_MIN, TILT_MAX = 0, 180                # allowed tilt range sent to the Arduino
                                           # (the sketch narrows tilt further to 40-140)
BOOT_WAIT_SECONDS = 4.0                    # max time to wait for "READY" after the port opens

# USB vendor IDs that usually mean "this is an Arduino (or a clone)".
ARDUINO_VIDS = {
    0x2341, 0x2A03,                        # Arduino LLC / Arduino.org
    0x1A86,                                # CH340 (most Nano / Uno clones)
    0x0403,                                # FTDI
    0x10C4,                                # CP210x
}

# Remembers every open port so each one is opened only once.
# (Opening resets the Arduino, so re-opening for every message would be slow.)
_connections = {}


def find_ports():
    """Return a list of (port name, description) for every serial port found."""
    return [(p.device, p.description) for p in list_ports.comports()]


def find_arduino_port():
    """Return the name of the first port that looks like an Arduino, or None."""
    for p in list_ports.comports():
        looks_like_arduino = (
            (p.vid in ARDUINO_VIDS)
            or "arduino" in (p.description or "").lower()
        )
        if looks_like_arduino:
            return p.device
    return None


def _wait_for_ready(arduino, timeout):
    """
    Read lines until the sketch prints "READY" or `timeout` seconds pass.
    Returns True if READY was seen. (Boards that do not auto-reset never
    print it, so a False result is a warning, not an error.)
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = arduino.readline().decode(errors="ignore").strip()
        if line == "READY":
            return True
    return False


def _get_port(port, baud):
    """Return an open connection for `port`, opening it first if needed."""
    arduino = _connections.get(port)
    if arduino is not None and arduino.is_open:    # already open: reuse it
        return arduino

    try:
        # timeout=0.5 only affects reading; write_timeout stops a stuck write
        arduino = serial.Serial(port, baud, timeout=0.5, write_timeout=1)
    except serial.SerialException as err:
        raise ConnectionError(
            f"Could not open {port}. Check the port name, that the Arduino is "
            f"plugged in, and that the Serial Monitor / Arduino IDE is closed."
        ) from err

    try:
        _wait_for_ready(arduino, BOOT_WAIT_SECONDS)   # the Arduino restarts when the port opens
        arduino.reset_input_buffer()                  # throw away anything left over
    except BaseException:
        arduino.close()                               # never leave a half-open port behind
        raise

    _connections[port] = arduino                      # save it for next time
    return arduino


def arduinoconnect(port, msg, baud=DEFAULT_BAUD, read_reply=False):
    """
    Send any text message to the Arduino.
    read_reply=True waits for one reply line (for example "OK") and returns it.
    Otherwise it returns None straight away.
    """
    arduino = _get_port(port, baud)
    try:
        arduino.reset_input_buffer()               # drop old unread replies ("OK") so they never pile up
        arduino.write((str(msg).strip() + "\n").encode())   # text -> bytes + line end
        if read_reply:
            return arduino.readline().decode(errors="ignore").strip()
    except (serial.SerialException, OSError):
        close_port(port)                           # connection broke: forget it
        raise
    return None


def _clamp(value, low, high):
    """Force a number to stay between low and high."""
    return max(low, min(high, value))


def send_state(port, pan, tilt, buzzer=False, baud=DEFAULT_BAUD, read_reply=False):
    """
    Send pan angle, tilt angle and buzzer state as one message.
    pan, tilt : angles in degrees (rounded to whole numbers and clamped)
    buzzer    : True/1 = on, False/0 = off
    """
    pan = _clamp(int(round(pan)), PAN_MIN, PAN_MAX)       # whole number, in range
    tilt = _clamp(int(round(tilt)), TILT_MIN, TILT_MAX)
    buzzer = 1 if buzzer else 0                           # always exactly 0 or 1
    return arduinoconnect(port, f"{pan},{tilt},{buzzer}", baud, read_reply)


def close_port(port):
    """Close one port and forget it."""
    arduino = _connections.pop(port, None)
    if arduino is not None and arduino.is_open:
        arduino.close()


def close_all():
    """Close every open port (call this when your program ends)."""
    for name in list(_connections):
        close_port(name)


# ---------- QUICK TEST (no camera needed) ----------
# Run from the project folder:  python pages/Arduino.py COM4
# With no port given, the first Arduino-looking port is used.
if __name__ == "__main__":
    PORT = sys.argv[1] if len(sys.argv) > 1 else find_arduino_port()
    print("Ports found:", find_ports())
    if PORT is None:
        raise SystemExit("No Arduino found. Plug it in, or pass the port: python pages/Arduino.py COM4")

    print(f"Testing {PORT} (takes a few seconds to connect)...")
    try:
        print("Center, buzzer off :", send_state(PORT, 90, 90, False, read_reply=True))
        time.sleep(1.5)
        print("Pan 120, tilt 70   :", send_state(PORT, 120, 70, False, read_reply=True))
        time.sleep(1.5)
        print("Buzzer on          :", send_state(PORT, 120, 70, True, read_reply=True))
        time.sleep(1.5)
        print("Back to center     :", send_state(PORT, 90, 90, False, read_reply=True))
    except (ConnectionError, serial.SerialException, OSError) as err:
        print(err)
    finally:
        close_all()

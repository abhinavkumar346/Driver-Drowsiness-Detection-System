// =====================================================
//  PAN-TILT + BUZZER, CONTROLLED OVER USB SERIAL
//  Board: Arduino Uno / Nano
//  Pairs with pages/Arduino.py (send_state(port, pan, tilt, buzzer))
//
//  Message the board expects (one line, ends with a newline):
//      pan,tilt,buzzer
//  Example:  95,80,1  -> pan 95, tilt 80, buzzer ON
//
//  Replies:  "READY" once after boot, then "OK" for every valid
//  line and "ERR" for a line it cannot read.
//
//  You can also test it by hand in the Arduino Serial Monitor:
//  set 115200 baud and "Newline" line ending, then type  90,90,0
// =====================================================

#include <Servo.h>                 // Built-in library that makes the servo control signal

// ---------- PIN SETTINGS (change to match your wiring) ----------
const int PAN_PIN    = 9;          // Signal wire of the PAN servo (left-right)
const int TILT_PIN   = 10;         // Signal wire of the TILT servo (up-down)
const int BUZZER_PIN = 11;         // Buzzer + (or LED + 220 ohm resistor); other leg to GND

// ---------- BUZZER TYPE ----------
// ACTIVE buzzer  (has its own tone circuit, beeps when given power): false
// PASSIVE buzzer (a bare speaker, needs a frequency to make sound):  true
// If your buzzer only "clicks" when it should beep, it is passive: set this to true.
const bool BUZZER_IS_PASSIVE = false;
const unsigned int BUZZER_FREQ_HZ = 2000;   // tone pitch, used only for a passive buzzer

// ---------- ANGLE LIMITS ----------
// Protect the mount from hitting its mechanical stops.
const int PAN_MIN  = 0;
const int PAN_MAX  = 180;
const int TILT_MIN = 40;           // Tilt usually has a smaller range; adjust after testing
const int TILT_MAX = 140;

// ---------- MOTION SETTINGS ----------
const unsigned long STEP_INTERVAL = 15;   // ms between 1-degree steps (bigger = slower, smoother)
const int STEP_SIZE = 1;                  // Degrees moved per step (1 deg / 15 ms = about 66 deg/s)

// ---------- BUZZER SETTINGS ----------
const unsigned long BEEP_ON_TIME  = 200;  // ms the buzzer is ON in each beep
const unsigned long BEEP_OFF_TIME = 200;  // ms the buzzer is OFF between beeps
const unsigned long COMM_TIMEOUT  = 5000; // If nothing arrives for 5 s, turn the buzzer OFF
                                          // (stops a stuck buzzer if the laptop disconnects)

// ---------- OBJECTS AND VARIABLES ----------
Servo panServo;                    // Represents the pan servo
Servo tiltServo;                   // Represents the tilt servo

int panTarget   = 90;              // Angle we WANT the pan servo to reach
int tiltTarget  = 90;              // Angle we WANT the tilt servo to reach
int panNow      = 90;              // Angle the pan servo is AT right now
int tiltNow     = 90;              // Angle the tilt servo is AT right now

bool buzzerRequested = false;      // true = the laptop asked for the buzzer
bool buzzerOn        = false;      // true = the buzzer is sounding right now

unsigned long lastStepTime    = 0; // When the servos last took a step
unsigned long lastBeepToggle  = 0; // When the buzzer last switched ON/OFF
unsigned long lastCommandTime = 0; // When the last valid message arrived

const byte BUF_SIZE = 32;          // Room for one incoming line
char inBuf[BUF_SIZE];              // Stores characters until the line is complete
byte inLen = 0;                    // How many characters are stored so far
bool skipLine = false;             // true = current line was too long, ignore it until its newline

// =====================================================
//  setBuzzer(): the ONLY place that touches the buzzer pin,
//  so active and passive buzzers are handled in one spot.
// =====================================================
void setBuzzer(bool on) {
  buzzerOn = on;
  if (BUZZER_IS_PASSIVE) {
    if (on) tone(BUZZER_PIN, BUZZER_FREQ_HZ);   // start the pitch
    else    noTone(BUZZER_PIN);                 // stop it
  } else {
    digitalWrite(BUZZER_PIN, on ? HIGH : LOW);  // just power on / off
  }
}

// =====================================================
//  setup(): runs ONCE when the board powers on
// =====================================================
void setup() {
  Serial.begin(115200);            // Must match DEFAULT_BAUD in Arduino.py

  panServo.attach(PAN_PIN);        // Connect the pan servo object to its pin
  tiltServo.attach(TILT_PIN);      // Connect the tilt servo object to its pin
  panServo.write(panNow);          // Start both servos at the center
  tiltServo.write(tiltNow);

  pinMode(BUZZER_PIN, OUTPUT);     // Buzzer pin sends signals OUT of the Arduino
  setBuzzer(false);                // Start silent

  delay(500);                      // Let the servos reach the center
  Serial.println("READY");         // Tell the laptop we are ready
}

// =====================================================
//  loop(): runs again and again forever
//  Every task is a separate function and none of them
//  uses delay(), so reading, moving and beeping all
//  keep working at the same time.
// =====================================================
void loop() {
  readSerial();                    // 1. Look for a new message
  checkTimeout();                  // 2. Safety: silence the buzzer if messages stop
  moveServos();                    // 3. Move servos one small step toward their targets
  updateBuzzer();                  // 4. Beep or stay silent
}

// =====================================================
//  readSerial(): collects characters into a line
// =====================================================
void readSerial() {
  while (Serial.available()) {             // While unread characters are waiting...
    char c = Serial.read();                // ...take one

    if (c == '\n' || c == '\r') {          // Newline = the message is finished
      if (inLen > 0 && !skipLine) {        // Ignore empty and over-long lines
        inBuf[inLen] = '\0';               // Mark the end of the text
        parseCommand(inBuf);               // Interpret the finished line
      }
      inLen = 0;                           // Get ready for the next message
      skipLine = false;
    }
    else if (inLen < BUF_SIZE - 1) {       // Space left in the buffer?
      inBuf[inLen++] = c;                  // Store the character
    }
    else {
      skipLine = true;                     // Line too long = garbage: ignore all of it
    }
  }
}

// =====================================================
//  parseCommand(): turns "pan,tilt,buzzer" into numbers
// =====================================================
void parseCommand(const char *line) {
  int pan, tilt, buzzer;

  // sscanf pulls three whole numbers out of the text and returns how many it found
  if (sscanf(line, "%d,%d,%d", &pan, &tilt, &buzzer) == 3) {
    panTarget  = constrain(pan,  PAN_MIN,  PAN_MAX);    // Clamp to the safe pan range
    tiltTarget = constrain(tilt, TILT_MIN, TILT_MAX);   // Clamp to the safe tilt range
    buzzerRequested = (buzzer != 0);                    // 0 = off, anything else = on
    lastCommandTime = millis();                         // Remember when this arrived
    Serial.println("OK");                               // Confirm to the laptop
  } else {
    Serial.println("ERR");                              // Message was not in the right format
  }
}

// =====================================================
//  checkTimeout(): failsafe if the laptop goes silent
// =====================================================
void checkTimeout() {
  if (buzzerRequested && (millis() - lastCommandTime > COMM_TIMEOUT)) {
    buzzerRequested = false;               // No update for too long: stop the buzzer
  }
}

// =====================================================
//  moveServos(): smooth motion, 1 small step at a time
//  Instead of jumping to the target (jerky, high current),
//  each servo creeps toward it every STEP_INTERVAL ms.
// =====================================================
void moveServos() {
  unsigned long now = millis();
  if (now - lastStepTime < STEP_INTERVAL) return;   // Not time for the next step yet
  lastStepTime = now;

  // --- PAN ---
  if (panNow < panTarget) {
    panNow = min(panNow + STEP_SIZE, panTarget);    // Move up, never overshoot
    panServo.write(panNow);                         // Send the new angle
  } else if (panNow > panTarget) {
    panNow = max(panNow - STEP_SIZE, panTarget);    // Move down, never overshoot
    panServo.write(panNow);
  }

  // --- TILT (same logic) ---
  if (tiltNow < tiltTarget) {
    tiltNow = min(tiltNow + STEP_SIZE, tiltTarget);
    tiltServo.write(tiltNow);
  } else if (tiltNow > tiltTarget) {
    tiltNow = max(tiltNow - STEP_SIZE, tiltTarget);
    tiltServo.write(tiltNow);
  }
}

// =====================================================
//  updateBuzzer(): beeping pattern while requested
// =====================================================
void updateBuzzer() {
  if (!buzzerRequested) {                  // No buzzer wanted
    if (buzzerOn) setBuzzer(false);        // If it is still sounding, switch it off
    return;                                // Nothing more to do
  }

  unsigned long now = millis();
  unsigned long wait = buzzerOn ? BEEP_ON_TIME : BEEP_OFF_TIME;  // How long to stay in this state

  if (now - lastBeepToggle >= wait) {      // Time to flip the state?
    setBuzzer(!buzzerOn);                  // ON -> OFF or OFF -> ON
    lastBeepToggle = now;                  // Restart the timer
  }
}

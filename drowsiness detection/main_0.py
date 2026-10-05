import cv2 as cv
from collections import deque
from model import detect_faces, get_locked_face, draw_lock, reset_detector
from model import load_face_mesh, release_face_mesh, process_face_landmarks, crop_face
from model.DisplayINFO import write_info
from model.drowsiness_detector import display_info, update_perclos
from model.DisplayINFO import PERCLOS_ALERT_THRESHOLD   # same threshold that shows DROWSINESS ALERT
from model.pantilt import PanTilt                      # sends angles + buzzer to the Arduino


def open_camera(index):
    """Open a camera once with DirectShow. Return the capture, or None if it fails."""
    cap = cv.VideoCapture(index, cv.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        return None
    return cap


# ---- 1. Read the camera index ----
raw = input("Enter camera index (default 0): ").strip()
try:
    camIndex = int(raw) if raw else 0
    if camIndex < 0:
        raise ValueError
except ValueError:
    print("Invalid input. Using default camera index 0.")
    camIndex = 0

# ---- 2. Open the camera (only once) ----
print(f"Opening camera {camIndex}...")
cap = open_camera(camIndex)

if cap is None and camIndex != 0:
    print(f"Camera {camIndex} not available. Trying camera 0...")
    camIndex = 0
    cap = open_camera(0)

if cap is None:
    raise SystemExit("No camera could be opened. Close other apps using the camera and try again.")
print("Camera opened.")

# ---- 3. Load the face mesh ----
print("Loading face mesh...")
face_mesh = load_face_mesh()
print("Face mesh loaded.")

# ---- 4. Open the Arduino port ----
print("Connecting to Arduino...")
pantilt = PanTilt()
print("Arduino step done. Press 'q' in the video window to quit.")

perclos_window = deque()
failed_reads = 0

# ---- 5. Main loop (finally = cleanup always runs) ----
try:
    while True:
        success, frame = cap.read()
        if not success:
            failed_reads += 1
            print(f"Failed to read frame ({failed_reads}/30).")
            if failed_reads >= 30:
                print("Camera stopped giving frames. Exiting.")
                break
            continue
        failed_reads = 0

        boxes = detect_faces(frame)
        locked_face = get_locked_face(boxes)
        frame, dx, dy = draw_lock(frame, locked_face)

        avg_ear, mar, eye_closed, yawning = None, None, False, False

        if locked_face is not None:
            x, y, w, h, cx, cy = locked_face
            face_crop = crop_face(frame, (x, y, w, h))

            if face_crop is not None:
                crop_h, crop_w = face_crop.shape[:2]
                results = face_mesh.process(cv.cvtColor(face_crop, cv.COLOR_BGR2RGB))
                avg_ear, mar, eye_closed, yawning = process_face_landmarks(
                    results, crop_w, crop_h, x, y, frame
                )

        perclos = update_perclos(eye_closed, perclos_window)

        # send pan/tilt angles and the buzzer state to the Arduino
        alert = perclos > PERCLOS_ALERT_THRESHOLD
        pantilt.update(dx, dy, frame.shape[1], frame.shape[0], alert)

        write_info(frame, dy, dx, avg_ear, mar, perclos, eye_closed, yawning)

        cv.imshow("Face Lock and Drowsiness Detection", frame)
        if cv.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    pantilt.close()          # re-center, buzzer off, close the port
    reset_detector()
    release_face_mesh()
    cap.release()
    cv.destroyAllWindows()

import ipaddress
import cv2 as cv
from collections import deque
from model import detect_faces, get_locked_face, draw_lock, reset_detector
from model import load_face_mesh, release_face_mesh, process_face_landmarks, crop_face
from model.DisplayINFO import write_info
from model.drowsiness_detector import update_perclos

PORT = 81
PATH = "/stream"
RECONNECT_AFTER = 30  # consecutive failed reads before reopening the stream


def ask_stream_url():
    """Ask for the camera IP and return a full stream URL."""
    while True:
        text = input("Enter camera IP (e.g. 10.101.14.96): ").strip()

        # Allow pasting a full URL
        if text.startswith("http://") or text.startswith("https://"):
            return text

        # Allow "ip:port" or plain "ip"
        host, _, port = text.partition(":")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            print("That is not a valid IP address. Try again.")
            continue

        return f"http://{host}:{port or PORT}{PATH}"


def open_stream(url):
    cap = cv.VideoCapture(url)
    cap.set(cv.CAP_PROP_BUFFERSIZE, 1)  # reduce lag; ignored by some backends
    return cap


# Keep asking until a stream actually opens
while True:
    stream_url = ask_stream_url()
    print(f"Connecting to {stream_url} ...")
    cap = open_stream(stream_url)
    if cap.isOpened():
        break
    print("Could not open that stream. Check the IP and that the camera is on.")
    cap.release()

face_mesh = load_face_mesh()
perclos_window = deque()
perclos = 0.0
failures = 0

try:
    while True:
        success, frame = cap.read()
        if not success:
            failures += 1
            print("Failed to read frame from camera.")
            if failures >= RECONNECT_AFTER:
                print("Reconnecting to stream...")
                cap.release()
                cap = open_stream(stream_url)
                failures = 0
            if cv.waitKey(100) & 0xFF == ord('q'):
                break
            continue
        failures = 0

        clean_frame = frame.copy()  # untouched copy for the face crop

        boxes = detect_faces(frame)
        locked_face = get_locked_face(boxes)
        frame, dx, dy = draw_lock(frame, locked_face)

        avg_ear, mar, eye_closed, yawning = None, None, False, False

        if locked_face is not None:
            x, y, w, h, _, _ = locked_face
            face_crop = crop_face(clean_frame, (x, y, w, h))

            if face_crop is not None:
                crop_h, crop_w = face_crop.shape[:2]
                results = face_mesh.process(cv.cvtColor(face_crop, cv.COLOR_BGR2RGB))
                avg_ear, mar, eye_closed, yawning = process_face_landmarks(
                    results, crop_w, crop_h, x, y, frame
                )

        if avg_ear is not None:
            perclos = update_perclos(eye_closed, perclos_window)

        write_info(frame, dy, dx, avg_ear, mar, perclos, eye_closed, yawning)

        cv.imshow("Face Lock and Drowsiness Detection", frame)
        if cv.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    reset_detector()
    release_face_mesh()
    cap.release()
    cv.destroyAllWindows()
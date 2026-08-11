import cv2 as cv
from collections import deque
from model import detect_faces, get_locked_face, draw_lock, reset_detector
from model import load_face_mesh, release_face_mesh, process_face_landmarks
from model.DisplayINFO import write_info
from model.drowsiness_detector import display_info, update_perclos

try:
    camIndex = int(input("Enter camera index (default 0): ") or 0)
    if camIndex < 0:
        raise ValueError("Camera index must be a non-negative integer.")
    if not cv.VideoCapture(camIndex).isOpened():
        raise ValueError(f"Camera index {camIndex} is not available.")
except ValueError:
    print("Invalid input. Using default camera index 0.")

face_mesh = load_face_mesh()
cap = cv.VideoCapture(camIndex)
perclos_window = deque()
while True:
    success, frame = cap.read()
    if not success:
        print("Failed to read frame from camera.")
        continue
    boxes = detect_faces(frame)
    locked_face = get_locked_face(boxes)
    frame, dx, dy = draw_lock(frame, locked_face)

    results = face_mesh.process(cv.cvtColor(frame, cv.COLOR_BGR2RGB))
    avg_ear, mar, eye_closed, yawning = process_face_landmarks(results, frame)
    perclos = update_perclos(eye_closed, perclos_window)

    write_info(frame, dy, dx, avg_ear, mar, perclos, eye_closed, yawning)

    cv.imshow("Face Lock and Drowsiness Detection", frame)
    if cv.waitKey(1) & 0xFF == ord('q'):
        break

    
reset_detector()
release_face_mesh()
cap.release()
cv.destroyAllWindows()
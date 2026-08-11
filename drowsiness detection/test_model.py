import cv2 as cv
from model import detect_faces, get_locked_face, draw_lock
try:
    camIndex = int(input("Enter camera index (default 0): ") or 0)
    if camIndex < 0:
        raise ValueError("Camera index must be a non-negative integer.")
    if not cv.VideoCapture(camIndex).isOpened():
        raise ValueError(f"Camera index {camIndex} is not available.")
except ValueError:
    print("Invalid input. Using default camera index 0.")

def main():
    cap = cv.VideoCapture(camIndex)
    while True:
        success, frame = cap.read()
        if not success:
            print("Failed to read frame from camera.")
            continue

        boxes = detect_faces(frame)
        locked_face = get_locked_face(boxes)
        frame, dx, dy = draw_lock(frame, locked_face)

        cv.imshow("Face Lock", frame)
        if cv.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv.destroyAllWindows()

main()
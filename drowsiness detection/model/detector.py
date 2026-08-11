import cv2 as cv
from ultralytics import YOLO

_detector = None

def get_detector():
    """Lazy-loads the YOLO model once, on first call."""
    global _detector
    if _detector is None:
        _detector = YOLO('model/yolo26n-face.pt')
    return _detector
def reset_detector():
    """Resets the YOLO model, allowing it to be reloaded."""
    global _detector
    if _detector is not None:
        _detector = None
def detect_faces(frame):
    results = get_detector()(frame, verbose=False)
    return results[0].boxes  # YOLO's box container (empty if nothing found)

def get_locked_face(boxes):
    if boxes is None or len(boxes) == 0:
        return None

    def box_area(b):
        x1, y1, x2, y2 = b.xyxy[0]
        return float((x2 - x1) * (y2 - y1))

    best = max(boxes, key=box_area)  # largest face = "locked" target
    x1, y1, x2, y2 = map(int, best.xyxy[0])
    w, h = x2 - x1, y2 - y1
    cx, cy = x1 + w // 2, y1 + h // 2
    return (x1, y1, w, h, cx, cy)

def draw_lock(frame, face):
    h, w, _ = frame.shape
    frame_cx, frame_cy = w // 2, h // 2
    if face is None:
        cv.putText(frame, "No face - searching...", (20, 30),
                   cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        return frame, None, None
    x, y, bw, bh, cx, cy = face
    cv.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
    cv.putText(frame, "LOCKED", (x, y - 10),
               cv.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv.drawMarker(frame, (cx, cy), (0, 255, 0), cv.MARKER_CROSS, 20, 2)
    cv.drawMarker(frame, (frame_cx, frame_cy), (255, 255, 0), cv.MARKER_CROSS, 15, 1)
    dx, dy = cx - frame_cx, cy - frame_cy
    cv.line(frame, (frame_cx, frame_cy), (cx, cy), (255, 255, 0), 1)
    # printing the dx and dy values on the frame for debugging at right corner
    # cv.putText(frame, f"dx: {dx}  dy: {dy}", (20, 30),
    #            cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    return frame, dx, dy 
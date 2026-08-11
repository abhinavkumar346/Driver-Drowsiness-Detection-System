import time
from collections import deque
import cv2
import numpy as np  
import mediapipe as mp

_model = None

MAR_THRESHOLD = 0.6             #\
EAR_THRESHOLD = 0.21            # |
                                # |>--- thresholds & parameters for drowsiness detection
PERCLOS_WINDOW_SECONDS = 60     # |
PERCLOS_ALERT_THRESHOLD = 0.3   #/


LEFT_EYE = [33, 160, 158, 133, 153, 144]  #\
RIGHT_EYE = [263, 387, 385, 362, 380, 373]# |---index of the resulting 
MOUTH = [61, 39, 269, 291, 405, 181]      #/

# aspect ratio calculations

def eye_aspect_ratio(landmarks, eye_indices, frame_w, frame_h):
    pts = []
    for idx in eye_indices:
        lm = landmarks[idx]
        pts.append(np.array([lm.x * frame_w, lm.y * frame_h]))
    p1, p2, p3, p4, p5, p6 = pts
    vertical_1 = np.linalg.norm(p2 - p6)
    vertical_2 = np.linalg.norm(p3 - p5)
    horizontal = np.linalg.norm(p1 - p4)
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)

def mouth_aspect_ratio(landmarks, frame_w, frame_h):
    pts = []
    for idx in MOUTH:
        lm = landmarks[idx]
        pts.append(np.array([lm.x * frame_w, lm.y * frame_h]))
    p1, p2, p3, p4, p5, p6 = pts
    vertical_1 = np.linalg.norm(p2 - p6)
    vertical_2 = np.linalg.norm(p3 - p5)
    horizontal = np.linalg.norm(p1 - p4)
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)

#crop the face region from the frame based on the detected face coordinates

def crop_face(frame, face_coordinates):
    x, y, w, h = face_coordinates
    frame_h, frame_w = frame.shape[:2]
    # FIX 1: bounds-check the bbox before slicing.
    # A raw YOLO bbox can have negative x/y (box partially off-screen)
    # or x+w / y+h beyond the frame edges. Without clamping, frame[y:y+h, x:x+w]
    # silently returns a smaller/empty array instead of erroring, which then
    # breaks process_face_landmarks() downstream with no clear cause.
    x, y = max(0, x), max(0, y)
    x2, y2 = min(frame_w, x + w), min(frame_h, y + h)
    if x2 <= x or y2 <= y:
        return None  # caller must check for None before using the crop
    return frame[y:y2, x:x2]

#loading the mediapipe face mesh _model
def load_face_mesh():
    global _model
    if _model is None:
        mp_face_mesh = mp.solutions.face_mesh
        mp_drawing = mp.solutions.drawing_utils
        _model = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
    return _model

def release_face_mesh():
    global _model
    if _model is not None:
        _model.close()
        _model = None

def process_face_landmarks(results, frame):
    h, w = frame.shape[:2]
    if results.multi_face_landmarks:

        landmarks = results.multi_face_landmarks[0].landmark
        left_ear = eye_aspect_ratio(landmarks, LEFT_EYE, w, h)
        right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE, w, h)
        avg_ear = (left_ear + right_ear) / 2.0
        eye_closed = avg_ear < EAR_THRESHOLD

        # FIX 2: mouth_aspect_ratio() existed but was never called, so MAR/yawn
        # data never actually reached the caller. Computing it here and folding
        # it into the return value is what makes the function's output match
        # what display_info() (and the module's stated design) expects.
        mar = mouth_aspect_ratio(landmarks, w, h)
        yawning = mar > MAR_THRESHOLD

        for idx in LEFT_EYE + RIGHT_EYE:
            lm = landmarks[idx]
            cx = int(lm.x * w)
            cy = int(lm.y * h)
            cv2.circle(frame, (cx, cy), 2, (0, 255, 0), -1)
        # draw mouth points too, mirroring the eye drawing above
        for idx in MOUTH:
            lm = landmarks[idx]
            cx = int(lm.x * w)
            cy = int(lm.y * h)
            cv2.circle(frame, (cx, cy), 2, (0, 200, 255), -1)

        # FIX 2 (cont.): return signature grew from (avg_ear, eye_closed)
        # to (avg_ear, mar, eye_closed, yawning). Anything calling this
        # function elsewhere in your main file needs to be updated to
        # unpack 4 values instead of 2, or this will throw/misassign.
        return avg_ear, mar, eye_closed, yawning
    
    # FIX 2 (cont.): "no face" fallback must match the new 4-value shape
    # above, otherwise callers get an unpacking error only on the frames
    # where no face is detected -- the kind of bug that hides until runtime.
    return None, None, False, False

def process_face_landmarks(results, crop_w, crop_h, offset_x, offset_y, frame):
    if results.multi_face_landmarks:
        landmarks = results.multi_face_landmarks[0].landmark
        left_ear = eye_aspect_ratio(landmarks, LEFT_EYE, crop_w, crop_h)
        right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE, crop_w, crop_h)
        avg_ear = (left_ear + right_ear) / 2.0
        eye_closed = avg_ear < EAR_THRESHOLD

        mar = mouth_aspect_ratio(landmarks, crop_w, crop_h)
        yawning = mar > MAR_THRESHOLD

        for idx in LEFT_EYE + RIGHT_EYE:
            lm = landmarks[idx]
            cx = int(lm.x * crop_w) + offset_x
            cy = int(lm.y * crop_h) + offset_y
            cv2.circle(frame, (cx, cy), 2, (0, 255, 0), -1)

        for idx in MOUTH:
            lm = landmarks[idx]
            cx = int(lm.x * crop_w) + offset_x
            cy = int(lm.y * crop_h) + offset_y
            cv2.circle(frame, (cx, cy), 2, (0, 200, 255), -1)

        return avg_ear, mar, eye_closed, yawning
    return None, None, False, False

def update_perclos(eye_closed, perclos_window):
    current_time = time.time()
    perclos_window.append((current_time, eye_closed))
    while perclos_window and (current_time - perclos_window[0][0]) > PERCLOS_WINDOW_SECONDS:
        perclos_window.popleft()
    closed_count = sum(1 for _, closed in perclos_window if closed)
    total_count = len(perclos_window)
    if total_count == 0:
        return 0.0
    return closed_count / total_count


# FIX 2 (cont.): display_info() needs mar/yawning params to actually show
# the yawn data now that process_face_landmarks() produces it.
def display_info(frame, avg_ear, mar, perclos, eye_closed, yawning):


    # EAR
    ear_text = f"EAR: {avg_ear:.3f}" if avg_ear is not None else "EAR: no face"
    cv2.putText(
        frame,
        ear_text,
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )
    # MAR -- new line, mirrors the EAR line above
    mar_text = f"MAR: {mar:.3f}" if mar is not None else "MAR: no face"
    cv2.putText(
        frame,
        mar_text,
        (10, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )
    # PERCLOS -- shifted down 35px to make room for the MAR line above
    perclos_text = f"PERCLOS: {perclos * 100:.1f}%"
    cv2.putText(
        frame,
        perclos_text,
        (10, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )
    # Eyes closed -- shifted down to keep spacing consistent
    if eye_closed:
        cv2.putText(
            frame,
            "EYES CLOSED",
            (10, 135),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )
    # Yawning -- new block, same pattern as "EYES CLOSED"
    if yawning:
        cv2.putText(
            frame,
            "YAWNING",
            (10, 170),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 165, 255),
            2
        )
    # Drowsiness alert -- shifted down to stay below the new lines
    if perclos > PERCLOS_ALERT_THRESHOLD:
        cv2.putText(
            frame,
            "DROWSINESS ALERT",
            (10, 210),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            3
        )

    return frame


#--------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    # Example usage of the drowsiness detection functions
    cap = cv2.VideoCapture(0)
    perclos_window = deque()

    load_face_mesh()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Convert the frame to RGB for Mediapipe processing
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = _model.process(rgb_frame)

        avg_ear, mar, eye_closed, yawning = process_face_landmarks(results, frame)
        perclos = update_perclos(eye_closed, perclos_window)
        
        display_info(frame, avg_ear, mar, perclos, eye_closed, yawning)

        cv2.imshow("Drowsiness Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    release_face_mesh()
    cap.release()
    cv2.destroyAllWindows()
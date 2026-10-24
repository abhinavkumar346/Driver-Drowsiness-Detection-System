import sys  
import argparse    
import cv2
from pages import (
    ModelLoader,
    FaceDetection,
    FaceMetrics,
    DisplayInfo,
    DrowsinessAlert,
    PanTilt,
)

def parse_args():
    parser = argparse.ArgumentParser(description="Saarthi drowsiness detection")
    parser.add_argument("--port", default=None,
                        help="Arduino COM port, e.g. COM4 (default: auto-detect)")
    parser.add_argument("--no-hardware", action="store_true",
                        help="run the vision code without an Arduino")
    return parser.parse_args()

args = parse_args()

WINDOW_NAME = "Saarthi"
MAX_FAILED_READS = 30        
URL = "http://172.20.10.4:81/stream"
loader = ModelLoader()
loader.load_models()
detector = FaceDetection(loader)
metrics = FaceMetrics()
alert = DrowsinessAlert()
display = DisplayInfo()
pantilt = None
failed_reads = 0

camera = cv2.VideoCapture(URL)

try:
    pantilt = PanTilt(port=args.port, use_hardware=not args.no_hardware)   

    while True:

        status, frame = camera.read()

        if not status:
            failed_reads += 1
            if failed_reads >= MAX_FAILED_READS:
                print("Camera stopped giving frames. Exiting.")
                break
            continue

        failed_reads = 0

        frame_h, frame_w = frame.shape[:2]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        boxes = detector.detect_faces(frame_rgb)
        locked_face = detector.get_locked_face(boxes)
        dx, dy = detector.get_offset(locked_face, frame_w, frame_h)

        results = loader.face_mesh.process(frame_rgb)
        avg_ear, mar, eye_closed, yawning = metrics.process(results, frame_w, frame_h)
        face_found = locked_face is not None

        if face_found:
            perclos = metrics.update_perclos(eye_closed)
        else:
            perclos = metrics.get_perclos()

        alert_on = alert.update(perclos, eye_closed, face_found)
        pantilt.update(dx, dy, frame_w, frame_h, alert_on)


        display.write_info(frame, dx, dy, avg_ear, mar, perclos,
                            eye_closed, yawning, alert_on)
        display.draw_lock(frame, locked_face)
        display.draw_eye_and_mouth_landmarks(
            frame, results, metrics.LEFT_EYE, metrics.RIGHT_EYE, metrics.MOUTH
        )
        display.draw_hardware_status(frame, pantilt.pan, pantilt.tilt,
                                        pantilt.status_text, pantilt.connected)

        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):              
            break

finally:
    if pantilt is not None:
        pantilt.close()                        # re-center, buzzer off, release the port
    camera.release()
    cv2.destroyAllWindows()
    loader.release_models()

import argparse
import sys
import cv2
from pages import (
    ModelLoader,
    FaceDetection,
    FaceMetrics,
    DisplayInfo,
    DrowsinessAlert,
    PanTilt,
)

WINDOW_NAME = "Saarthi"
MAX_FAILED_READS = 30        # give up after this many bad camera reads in a row

def parse_args():
    parser = argparse.ArgumentParser(description="Saarthi drowsiness detection")
    parser.add_argument("--camera", type=int, default=0,
                        help="camera index (default 0)")
    parser.add_argument("--port", default=None,
                        help="Arduino COM port, e.g. COM4 (default: auto-detect)")
    parser.add_argument("--no-hardware", action="store_true",
                        help="run the vision code without an Arduino")
    return parser.parse_args()


def open_camera(index):
    """Open the camera. Returns the capture, or None if it cannot be opened."""
    # DirectShow opens faster and more reliably on Windows; other systems use the default.
    backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if sys.platform == "win32" else [cv2.CAP_ANY]

    for backend in backends:
        camera = cv2.VideoCapture(index, backend)
        if camera.isOpened():
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # smaller queue = fresher frames for tracking
            return camera
        camera.release()
    return None


def main():
    args = parse_args()

    camera = open_camera(args.camera)
    if camera is None:
        raise SystemExit(f"Could not open camera {args.camera}. "
                         f"Close other apps that use it, or try --camera 1.")

    loader = ModelLoader()
    loader.load_models()

    detector = FaceDetection(loader)
    metrics = FaceMetrics()
    alert = DrowsinessAlert()
    display = DisplayInfo()
    pantilt = None
    failed_reads = 0

    try:
        pantilt = PanTilt(port=args.port, use_hardware=not args.no_hardware)

        while True:
            ok, frame = camera.read()
            if not ok:
                failed_reads += 1
                if failed_reads >= MAX_FAILED_READS:
                    print("Camera stopped giving frames. Exiting.")
                    break
                continue
            failed_reads = 0

            frame_h, frame_w = frame.shape[:2]
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)   # convert once, share it

            # --- 1. Find and lock the face ---
            boxes = detector.detect_faces(frame_rgb)
            locked_face = detector.get_locked_face(boxes)
            dx, dy = detector.get_offset(locked_face, frame_w, frame_h)

            # --- 2. Measure the eyes and mouth ---
            results = loader.face_mesh.process(frame_rgb)
            avg_ear, mar, eye_closed, yawning = metrics.process(results, frame_w, frame_h)
            face_found = avg_ear is not None

            if face_found:
                perclos = metrics.update_perclos(eye_closed)
            else:
                perclos = metrics.get_perclos()    # no face: do not count this frame

            # --- 3. Decide on the alert, then drive the Arduino (servos + buzzer) ---
            alert_on = alert.update(perclos, eye_closed, face_found)
            pantilt.update(dx, dy, frame_w, frame_h, alert_on)

            # --- 4. Draw everything ---
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
            if key in (27, ord("q")):              # Esc or q
                break
    finally:
        if pantilt is not None:
            pantilt.close()                        # re-center, buzzer off, release the port
        camera.release()
        cv2.destroyAllWindows()
        loader.release_models()


if __name__ == "__main__":
    main()

import cv2

MAR_THRESHOLD = 0.6             #\
EAR_THRESHOLD = 0.21            # |
                                # |>--- thresholds & parameters for drowsiness detection
PERCLOS_WINDOW_SECONDS = 60     # |
PERCLOS_ALERT_THRESHOLD = 0.3   #/


LEFT_EYE = [33, 160, 158, 133, 153, 144]  #\
RIGHT_EYE = [263, 387, 385, 362, 380, 373]# |---index of the resulting 
MOUTH = [61, 39, 269, 291, 405, 181]      #/


def write_info(frame, dy, dx, avg_ear, mar, perclos, eye_closed, yawning):
    h, w = frame.shape[:2]

    # EAR
    ear_text = f"EAR: {avg_ear:.3f}" if avg_ear is not None else "EAR: no face"
    cv2.putText(frame, ear_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    # MAR
    mar_text = f"MAR: {mar:.3f}" if mar is not None else "MAR: no face"
    cv2.putText(frame, mar_text, (10, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    # PERCLOS
    perclos_text = f"PERCLOS: {perclos * 100:.1f}%"
    cv2.putText(frame, perclos_text, (10, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    # Eyes closed
    if eye_closed:
        cv2.putText(frame, "EYES CLOSED", (10, 135),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    # Yawning
    if yawning:
        cv2.putText(frame, "YAWNING", (10, 170),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

    # Drowsiness alert
    if perclos > PERCLOS_ALERT_THRESHOLD:
        cv2.putText(frame, "DROWSINESS ALERT", (10, 210),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

    # dx/dy -- right-aligned so it sits on the opposite side from the EAR/MAR/PERCLOS block
    dxdy_text = f"dx: {dx}  dy: {dy}"
    (text_w, _), _ = cv2.getTextSize(dxdy_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x_right = w - text_w - 10
    cv2.putText(frame, dxdy_text, (x_right, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    return frame
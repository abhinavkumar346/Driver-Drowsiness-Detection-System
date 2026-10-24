import cv2


class DisplayInfo:

    def draw_lock(self, frame, face):
        h, w = frame.shape[:2]
        frame_cx, frame_cy = w // 2, h // 2
        if face is None:
            cv2.putText(frame, "No face - searching...", (20, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame
        x, y, bw, bh, cx, cy = face
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
        cv2.putText(frame, "LOCKED", (x, max(15, y - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.drawMarker(frame, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
        cv2.drawMarker(frame, (frame_cx, frame_cy), (255, 255, 0), cv2.MARKER_CROSS, 15, 1)
        cv2.line(frame, (frame_cx, frame_cy), (cx, cy), (255, 255, 0), 1)
        return frame

    def draw_eye_landmarks(self, frame, results, left_eye, right_eye):
        if not results.multi_face_landmarks:
            return frame

        h, w = frame.shape[:2]
        landmarks = results.multi_face_landmarks[0].landmark

        for idx in left_eye + right_eye:
            lm = landmarks[idx]
            cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 2, (0, 255, 0), -1)
        return frame

    def draw_mouth_landmarks(self, frame, results, mouth):
        if not results.multi_face_landmarks:
            return frame

        h, w = frame.shape[:2]
        landmarks = results.multi_face_landmarks[0].landmark

        for idx in mouth:
            lm = landmarks[idx]
            cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 2, (0, 165, 255), -1)
        return frame

    def draw_eye_and_mouth_landmarks(self, frame, results, left_eye, right_eye, mouth):
        self.draw_eye_landmarks(frame, results, left_eye, right_eye)
        self.draw_mouth_landmarks(frame, results, mouth)
        return frame

    def draw_all_landmarks(self, frame, results):
        """Optional debugging view: every one of the face mesh points."""
        if not results.multi_face_landmarks:
            return frame

        h, w = frame.shape[:2]
        landmarks = results.multi_face_landmarks[0].landmark

        for lm in landmarks:
            cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 1, (0, 0, 255), -1)
        return frame

    def write_info(self, frame, dx, dy, avg_ear, mar, perclos, eye_closed, yawning, alert):
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

        # Drowsiness alert (decided by DrowsinessAlert, the same flag that rings the buzzer)
        if alert:
            cv2.putText(frame, "DROWSINESS ALERT", (10, 210),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

        # dx/dy -- right-aligned so it sits on the opposite side from the EAR/MAR/PERCLOS block
        dxdy_text = "dx: --  dy: --" if dx is None else f"dx: {dx}  dy: {dy}"
        (text_w, _), _ = cv2.getTextSize(dxdy_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.putText(frame, dxdy_text, (w - text_w - 10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        return frame

    def draw_hardware_status(self, frame, pan, tilt, status_text, connected):
        """Bottom-right corner: current pan/tilt angles and whether the Arduino is connected."""
        h, w = frame.shape[:2]
        color = (0, 255, 0) if connected else (0, 165, 255)

        for line_no, (text, text_color) in enumerate([
            (f"Pan: {pan}  Tilt: {tilt}", (255, 255, 0)),
            (status_text, color),
        ]):
            (text_w, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            y = h - 50 + line_no * 28
            cv2.putText(frame, text, (w - text_w - 10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        return frame

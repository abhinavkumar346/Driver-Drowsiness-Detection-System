class FaceDetection:

    def __init__(self, loader):
        self.loader = loader
    
    def detect_faces(self, frame_rgb):
        """
        frame_rgb: the frame already converted to RGB (MediaPipe wants RGB).
        Returns a list of (x, y, w, h) boxes in pixels.
        """
        if self.loader.face_detector is None:
            raise ValueError("Face detection model is not loaded.")

        frame_height, frame_width = frame_rgb.shape[:2]
        result = self.loader.face_detector.process(frame_rgb)
        boxes = []
        if result.detections:
            for detection in result.detections:
                box = detection.location_data.relative_bounding_box

                x1 = max(0, int(box.xmin * frame_width))
                y1 = max(0, int(box.ymin * frame_height))
                x2 = min(frame_width, int((box.xmin + box.width) * frame_width))
                y2 = min(frame_height, int((box.ymin + box.height) * frame_height))

                if x2 > x1 and y2 > y1:
                    boxes.append((x1, y1, x2 - x1, y2 - y1))
        return boxes

    def get_locked_face(self, boxes):
        """Pick the largest face as the 'locked' target. Returns (x, y, w, h, cx, cy) or None."""
        if not boxes:
            return None

        best = max(boxes, key=lambda b: b[2] * b[3])   # biggest width * height
        x, y, w, h = best
        cx, cy = x + w // 2, y + h // 2
        return (x, y, w, h, cx, cy)

    def get_offset(self, face, frame_w, frame_h):
        """Face centre minus frame centre, in pixels. Returns (None, None) when there is no face."""
        if face is None:
            return None, None
        cx, cy = face[4], face[5]
        dx = cx - frame_w // 2
        dy = cy - frame_h // 2
        return dx, dy

import mediapipe as mp

class ModelLoader:
    def __init__(self):
        self.face_detector = None
        self.face_mesh = None

    def load_models(self):
        if self.face_detector is None:
            self.face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5,
            )

        if self.face_mesh is None:
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
    def get_face_detector(self , model_selection=0, min_detection_confidence=0.5):

        if self.face_detector is None:
            self.face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=model_selection,
                min_detection_confidence=min_detection_confidence,
            )
        return self.face_detector

    def get_face_mesh(
            self,
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
    ):
        if self.face_mesh is None:
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=static_image_mode,
                max_num_faces=max_num_faces,
                refine_landmarks=refine_landmarks,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )
        return self.face_mesh

    def release_models(self):
        if self.face_detector is not None:
            self.face_detector.close()
            self.face_detector = None

        if self.face_mesh is not None:
            self.face_mesh.close()
            self.face_mesh = None
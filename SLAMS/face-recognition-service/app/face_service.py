import face_recognition
import numpy as np


def generate_embedding(image_path: str) -> list[float]:
    """
    Detect a face in an image and generate its 128-dimensional encoding.
    """

    image = face_recognition.load_image_file(image_path)
    face_encodings = face_recognition.face_encodings(image)

    if not face_encodings:
        raise ValueError("No face detected in the image.")

    if len(face_encodings) > 1:
        raise ValueError("Multiple faces detected. Please provide an image with one face.")

    return face_encodings[0].tolist()


def compare_embeddings(
    known_embedding: list[float],
    face_embedding: list[float],
    tolerance: float = 0.6
) -> bool:
    """
    Compare a stored face embedding with a newly detected face.
    """

    known = np.array(known_embedding)
    current = np.array(face_embedding)

    return bool(
        face_recognition.compare_faces(
            [known],
            current,
            tolerance=tolerance
        )[0]
    )

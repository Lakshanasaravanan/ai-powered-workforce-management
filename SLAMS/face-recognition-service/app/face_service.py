import face_recognition
import numpy as np
from PIL import Image
from io import BytesIO


def generate_embedding_from_bytes(image_bytes: bytes) -> list[float]:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image_array = np.array(image)

    face_locations = face_recognition.face_locations(image_array)

    if not face_locations:
        raise ValueError("No face detected in the image.")

    if len(face_locations) > 1:
        raise ValueError(
            "Multiple faces detected. Please provide an image with one face."
        )

    face_encodings = face_recognition.face_encodings(
        image_array,
        face_locations
    )

    if not face_encodings:
        raise ValueError("Could not generate face embedding.")

    return face_encodings[0].tolist()


def compare_embeddings(
    known_embedding: list[float],
    face_embedding: list[float],
    tolerance: float = 0.6
) -> bool:
    known = np.array(known_embedding)
    current = np.array(face_embedding)

    return bool(
        face_recognition.compare_faces(
            [known],
            current,
            tolerance=tolerance
        )[0]
    )
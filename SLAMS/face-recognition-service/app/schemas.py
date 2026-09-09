from pydantic import BaseModel, Field


class FaceEmbeddingRequest(BaseModel):
    image_path: str = Field(..., description="Path to the image containing the face")


class FaceEmbeddingResponse(BaseModel):
    embedding: list[float]
    dimension: int


class FaceCompareRequest(BaseModel):
    known_embedding: list[float]
    face_embedding: list[float]
    tolerance: float = 0.6


class FaceCompareResponse(BaseModel):
    matched: bool

from fastapi import APIRouter, HTTPException

from app.face_service import generate_embedding, compare_embeddings
from app.schemas import (
    FaceEmbeddingRequest,
    FaceEmbeddingResponse,
    FaceCompareRequest,
    FaceCompareResponse,
)


router = APIRouter(prefix="/face", tags=["Face Recognition"])


@router.post("/embedding", response_model=FaceEmbeddingResponse)
def create_embedding(request: FaceEmbeddingRequest):
    try:
        embedding = generate_embedding(request.image_path)

        return FaceEmbeddingResponse(
            embedding=embedding,
            dimension=len(embedding)
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare", response_model=FaceCompareResponse)
def compare_face(request: FaceCompareRequest):
    try:
        matched = compare_embeddings(
            request.known_embedding,
            request.face_embedding,
            request.tolerance
        )

        return FaceCompareResponse(matched=matched)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

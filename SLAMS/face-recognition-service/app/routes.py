from fastapi import APIRouter, HTTPException, UploadFile, File
from app.face_service import generate_embedding_from_bytes
from app.schemas import (
    FaceEmbeddingResponse,
    FaceCompareRequest,
    FaceCompareResponse,
)

router = APIRouter(prefix="/face", tags=["Face Recognition"])


@router.post("/embedding", response_model=FaceEmbeddingResponse)
async def create_embedding(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()

        embedding = generate_embedding_from_bytes(image_bytes)

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
        from app.face_service import compare_embeddings

        matched = compare_embeddings(
            request.known_embedding,
            request.face_embedding,
            request.tolerance
        )

        return FaceCompareResponse(matched=matched)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
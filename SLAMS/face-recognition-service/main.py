from fastapi import FastAPI

from app.routes import router as face_router


app = FastAPI(title="SLAMS Face Recognition Service")

app.include_router(face_router)


@app.get("/health")
def health_check():
    return {"status": "Face recognition service is running"}

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import SettingsDependency
from app.core.security import authenticate_mock_user, create_access_token
from app.schemas.auth import TokenRequest, TokenResponse


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/token", response_model=TokenResponse)
def issue_development_token(payload: TokenRequest, settings: SettingsDependency) -> TokenResponse:
    user = authenticate_mock_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token, expires_in = create_access_token(user, settings)
    return TokenResponse(access_token=token, expires_in=expires_in)

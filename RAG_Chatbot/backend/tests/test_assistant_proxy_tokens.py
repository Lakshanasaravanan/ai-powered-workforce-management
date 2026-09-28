from __future__ import annotations
from datetime import datetime, timedelta, timezone
import jwt
import pytest
from fastapi import HTTPException
from app.core.config import Settings
from app.core.security import decode_access_token

def settings():
    return Settings(environment="test", jwt_secret_key="development-token-secret-that-is-long-enough", assistant_proxy_jwt_secret="assistant-token-secret-that-is-long-enough")

def token(**changes):
    now=datetime.now(timezone.utc); claims={"iss":"slams-assistant-proxy","aud":"agentic-rag-assistant","sub":"EMP001","employee_id":"EMP001","name":"Avery","token_type":"assistant","exp":now+timedelta(seconds=60),"iat":now,"roles":["ROLE_ADMIN"]}; claims.update(changes)
    return jwt.encode(claims,"assistant-token-secret-that-is-long-enough",algorithm="HS256")

def test_valid_assistant_token_is_bound_and_roles_are_not_trusted():
    user=decode_access_token(token(),settings())
    assert user.employee_id == "EMP001" and user.roles == ("employee",)

@pytest.mark.parametrize("claims", [{"iss":"wrong"},{"aud":"wrong"},{"token_type":"access"},{"sub":"EMP002"},{"exp":datetime.now(timezone.utc)-timedelta(seconds=1)}])
def test_assistant_token_required_claims_are_enforced(claims):
    with pytest.raises(HTTPException): decode_access_token(token(**claims),settings())

def test_malformed_and_algorithm_confusion_tokens_are_rejected():
    with pytest.raises(HTTPException): decode_access_token("not-a-token",settings())
    unsigned=jwt.encode({"sub":"EMP001"},key="",algorithm="none")
    with pytest.raises(HTTPException): decode_access_token(unsigned,settings())

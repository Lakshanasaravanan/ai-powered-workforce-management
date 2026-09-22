import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_hs256_accepts_a_sufficiently_strong_secret():
    assert Settings(_env_file=None, jwt_secret="s" * 32).jwt_secret == "s" * 32


def test_hs256_rejects_short_secret_without_echoing_its_value():
    weak_secret = "short-secret"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, jwt_secret=weak_secret)
    assert weak_secret not in str(error.value)
    assert "at least 32 bytes" in str(error.value)


def test_hs256_rejects_example_placeholder():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret="replace-with-a-local-secret-of-at-least-32-bytes")


def test_cors_origins_are_explicit_and_credentials_are_not_needed_for_bearer_auth():
    settings = Settings(_env_file=None, jwt_secret="s" * 32)
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]

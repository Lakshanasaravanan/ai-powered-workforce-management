"""Isolated, non-secret defaults for EMS tests."""

import os


os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-signing-secret-not-for-production-32-bytes")

from __future__ import annotations
import fakeredis
import pytest
from types import SimpleNamespace
from app.api.routes import health
from app.services.rate_limit import InMemoryRateLimiter, RedisRateLimiter, RateLimitExceeded

@pytest.mark.parametrize("factory", [InMemoryRateLimiter, lambda: RedisRateLimiter(fakeredis.FakeRedis(decode_responses=True))])
def test_rate_limit_threshold_employee_and_route_isolation(factory):
    limiter=factory()
    limiter.check("chat:EMP001", 2); limiter.check("chat:EMP001", 2)
    with pytest.raises(RateLimitExceeded): limiter.check("chat:EMP001", 2)
    limiter.check("chat:EMP002", 2)
    limiter.check("confirmation:EMP001", 2)

def test_redis_rate_limit_is_shared_by_independent_instances():
    backend=fakeredis.FakeRedis(decode_responses=True); one=RedisRateLimiter(backend); two=RedisRateLimiter(backend)
    one.check("chat:EMP001", 1)
    with pytest.raises(RateLimitExceeded): two.check("chat:EMP001", 1)

def test_redis_rate_failure_fails_closed():
    class Broken:
        def pipeline(self): raise ConnectionError("unavailable")
    with pytest.raises(RateLimitExceeded): RedisRateLimiter(Broken()).check("chat:EMP001", 1)

def test_readiness_redis_disabled_and_unavailable_are_safe(monkeypatch):
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis_client=None)))
    monkeypatch.setattr(health, "get_settings", lambda: SimpleNamespace(redis_enabled=False, environment="test", readiness_warnings=[]))
    assert health.ready(request).status_code == 200
    class Broken:
        def ping(self): raise ConnectionError("redis://user:password@secret")
    request.app.state.redis_client=Broken()
    monkeypatch.setattr(health, "get_settings", lambda: SimpleNamespace(redis_enabled=True, environment="test", readiness_warnings=[]))
    response=health.ready(request)
    assert response.status_code == 503 and b"password" not in response.body and b"redis://" not in response.body

def test_readiness_redis_healthy_and_liveness_unaffected(monkeypatch):
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis_client=SimpleNamespace(ping=lambda: True))))
    monkeypatch.setattr(health, "get_settings", lambda: SimpleNamespace(redis_enabled=True, environment="test", readiness_warnings=[]))
    assert health.ready(request).status_code == 200
    assert health.health() == {"status":"ok"}

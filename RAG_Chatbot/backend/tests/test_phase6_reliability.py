from __future__ import annotations
import json
import fakeredis
import pytest
from types import SimpleNamespace
from app.api.routes import health
from app.services.rate_limit import InMemoryRateLimiter, RedisRateLimiter, RateLimitExceeded
from app.services.llm import LLMProvider

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


def test_readiness_fails_closed_for_missing_artifacts_or_selected_llm(monkeypatch):
    class Provider(LLMProvider):
        def __init__(self, ready): self.ready = ready
        def generate(self, *args, **kwargs): raise AssertionError("readiness must not generate")
        def is_ready(self): return self.ready

    def request(index_ready, provider_ready):
        service = SimpleNamespace(generator=SimpleNamespace(provider=Provider(provider_ready)))
        state = SimpleNamespace(rag_index_status=SimpleNamespace(available=index_ready), rag_service=service, redis_client=None)
        return SimpleNamespace(app=SimpleNamespace(state=state))

    monkeypatch.setattr(health, "get_settings", lambda: SimpleNamespace(redis_enabled=False, environment="test", readiness_warnings=[], llm_provider="ollama"))
    missing_artifacts = health.ready(request(False, True))
    assert missing_artifacts.status_code == 503 and json.loads(missing_artifacts.body)["dependencies"]["rag"] == "unavailable"
    missing_llm = health.ready(request(True, False))
    assert missing_llm.status_code == 503 and json.loads(missing_llm.body)["dependencies"]["ollama"] == "unavailable"
    assert health.ready(request(True, True)).status_code == 200

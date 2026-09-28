from __future__ import annotations

import json

from app.agents.semantic_routing import EMSReadOperation, SemanticCategory, SemanticIntentRouter


class StubProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict]] = []

    def generate(self, system_prompt: str, user_prompt: str, response_schema: dict) -> str:
        self.calls.append((system_prompt, user_prompt, response_schema))
        return self.response


def test_semantic_router_accepts_only_the_closed_general_and_ems_read_shapes():
    provider = StubProvider(json.dumps({"category": "general", "general_response": "Hello from InfoTech Agent."}))
    route = SemanticIntentRouter(provider).classify("Explain REST APIs simply.")
    assert route is not None
    assert route.category is SemanticCategory.GENERAL
    assert route.general_response == "Hello from InfoTech Agent."
    assert provider.calls and "Explain REST APIs simply." in provider.calls[0][1]

    provider = StubProvider(json.dumps({"category": "ems_read", "read_operation": "manager"}))
    route = SemanticIntentRouter(provider).classify("Who is my manger?")
    assert route is not None
    assert route.category is SemanticCategory.EMS_READ
    assert route.read_operation is EMSReadOperation.MANAGER


def test_semantic_router_rejects_untrusted_action_arguments_and_invalid_responses():
    provider = StubProvider(json.dumps({"category": "ems_action_leave", "arguments": {"employee_id": "unsafe"}}))
    assert SemanticIntentRouter(provider).classify("I need leave tomorrow.") is None

    provider = StubProvider("not JSON")
    assert SemanticIntentRouter(provider).classify("Tell me something interesting.") is None

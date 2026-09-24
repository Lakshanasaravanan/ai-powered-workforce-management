from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.agents.apply_leave import ApplyLeaveInput
from app.core.config import get_settings
from app.services.infotech_ems import (
    EMSConflict,
    EMSForbidden,
    EMSUncertainOutcome,
    EMSUnauthorized,
    EMSValidationFailure,
    InfoTechEMSReadClient,
)


def leave() -> ApplyLeaveInput:
    return ApplyLeaveInput(leave_type="CASUAL", start_date=date(2028, 1, 1), end_date=date(2028, 1, 1), duration="FULL_DAY", reason="test")


@pytest.mark.parametrize("status,error", [(401, EMSUnauthorized), (403, EMSForbidden), (409, EMSConflict), (422, EMSValidationFailure)])
def test_definitive_apply_leave_responses_are_not_uncertain_retries(status, error):
    client = InfoTechEMSReadClient(get_settings(), httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status))))
    with pytest.raises(error):
        client.apply_leave(leave(), "test-bearer", "server-generated-test-key-with-safe-length", None)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_apply_leave_responses_remain_uncertain(status):
    client = InfoTechEMSReadClient(get_settings(), httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status))))
    with pytest.raises(EMSUncertainOutcome):
        client.apply_leave(leave(), "test-bearer", "server-generated-test-key-with-safe-length", None)


@pytest.mark.parametrize("exception", [httpx.ReadTimeout("timeout"), httpx.ConnectError("connection")])
def test_transport_failures_remain_uncertain(exception):
    def fail(request): raise exception
    client = InfoTechEMSReadClient(get_settings(), httpx.Client(transport=httpx.MockTransport(fail)))
    with pytest.raises(EMSUncertainOutcome):
        client.apply_leave(leave(), "test-bearer", "server-generated-test-key-with-safe-length", None)

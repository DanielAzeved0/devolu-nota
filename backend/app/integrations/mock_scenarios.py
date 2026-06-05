from typing import Literal

from app.integrations.errors import MockIntegrationError
from app.schemas.mock_integrations import ExternalProvider

MockScenario = Literal["success", "invalid_token", "timeout", "external_error"]


def raise_for_mock_scenario(*, provider: ExternalProvider, scenario: MockScenario) -> None:
    if scenario == "success":
        return
    if scenario == "invalid_token":
        raise MockIntegrationError(
            code="MOCK_INVALID_TOKEN",
            message=f"{provider} credentials are invalid in mock scenario",
            provider=provider,
            retryable=False,
        )
    if scenario == "timeout":
        raise MockIntegrationError(
            code="MOCK_TIMEOUT",
            message=f"{provider} timed out in mock scenario",
            provider=provider,
            retryable=True,
        )
    raise MockIntegrationError(
        code="MOCK_EXTERNAL_ERROR",
        message=f"{provider} returned a transient external error in mock scenario",
        provider=provider,
        retryable=True,
    )

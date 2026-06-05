from app.schemas.mock_integrations import ExternalProvider, MockErrorCode, MockIntegrationErrorPayload


class MockIntegrationError(Exception):
    def __init__(
        self,
        *,
        code: MockErrorCode,
        message: str,
        provider: ExternalProvider,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.payload = MockIntegrationErrorPayload(
            code=code,
            message=message,
            provider=provider,
            retryable=retryable,
        )

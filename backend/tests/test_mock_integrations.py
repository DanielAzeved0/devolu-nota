import uuid

import pytest

from app.integrations.errors import MockIntegrationError
from app.integrations.mercado_livre.mock_client import MercadoLivreMockClient
from app.integrations.shopee.mock_client import ShopeeMockClient
from app.integrations.tiny.mock_client import TinyMockClient
from app.services.mock_integrations import MockIntegrationService

pytestmark = pytest.mark.asyncio


def assert_payload_has_no_secrets(payload: object) -> None:
    serialized = str(payload)
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "api_token" not in serialized
    assert "client_secret" not in serialized
    assert "encrypted_credentials" not in serialized


async def test_mercado_livre_mock_client_returns_safe_return_orders() -> None:
    company_id = uuid.uuid4()
    returns = await MercadoLivreMockClient().list_return_orders(company_id=company_id)

    assert len(returns) == 1
    assert returns[0].company_id == company_id
    assert returns[0].marketplace == "MERCADO_LIVRE"
    assert returns[0].external_order_id == "ML-RETURN-1001"
    assert returns[0].items[0].quantity > 0
    assert_payload_has_no_secrets(returns)


async def test_shopee_mock_client_returns_safe_return_orders() -> None:
    company_id = uuid.uuid4()
    returns = await ShopeeMockClient().list_return_orders(company_id=company_id)

    assert len(returns) == 1
    assert returns[0].company_id == company_id
    assert returns[0].marketplace == "SHOPEE"
    assert returns[0].external_order_id == "SHP-RETURN-2001"
    assert returns[0].items[0].unit_price > 0
    assert_payload_has_no_secrets(returns)


async def test_tiny_mock_client_returns_original_invoice_for_known_order() -> None:
    company_id = uuid.uuid4()
    invoice = await TinyMockClient().get_original_invoice(
        company_id=company_id,
        external_order_id="ML-RETURN-1001",
    )

    assert invoice.company_id == company_id
    assert invoice.external_order_id == "ML-RETURN-1001"
    assert len(invoice.original_nfe_key) == 44
    assert invoice.items[0].sku == "SKU-ML-001"
    assert_payload_has_no_secrets(invoice)


async def test_tiny_mock_client_returns_controlled_not_found_error() -> None:
    with pytest.raises(MockIntegrationError) as exc_info:
        await TinyMockClient().get_original_invoice(
            company_id=uuid.uuid4(),
            external_order_id="UNKNOWN",
        )

    assert exc_info.value.payload.code == "MOCK_NOT_FOUND"
    assert exc_info.value.payload.provider == "TINY"
    assert exc_info.value.payload.retryable is False
    assert_payload_has_no_secrets(exc_info.value.payload)


@pytest.mark.parametrize("scenario", ["invalid_token", "timeout", "external_error"])
async def test_mock_clients_return_controlled_provider_errors(scenario: str) -> None:
    with pytest.raises(MockIntegrationError) as exc_info:
        await MercadoLivreMockClient().list_return_orders(
            company_id=uuid.uuid4(),
            scenario=scenario,
        )

    expected_code = {
        "invalid_token": "MOCK_INVALID_TOKEN",
        "timeout": "MOCK_TIMEOUT",
        "external_error": "MOCK_EXTERNAL_ERROR",
    }[scenario]
    assert exc_info.value.payload.code == expected_code
    assert exc_info.value.payload.provider == "MERCADO_LIVRE"
    assert exc_info.value.payload.retryable is (scenario != "invalid_token")
    assert_payload_has_no_secrets(exc_info.value.payload)


async def test_mock_integration_service_links_return_to_original_invoice() -> None:
    company_id = uuid.uuid4()
    return_order, invoice = await MockIntegrationService().link_first_return_to_original_invoice(
        company_id=company_id,
        marketplace="MERCADO_LIVRE",
    )

    assert return_order.company_id == company_id
    assert invoice.company_id == company_id
    assert invoice.external_order_id == return_order.external_order_id
    assert len(invoice.original_nfe_key) == 44

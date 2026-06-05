from uuid import UUID

from app.integrations.mercado_livre.mock_client import MercadoLivreMockClient
from app.integrations.mock_scenarios import MockScenario
from app.integrations.shopee.mock_client import ShopeeMockClient
from app.integrations.tiny.mock_client import TinyMockClient
from app.schemas.mock_integrations import MarketplaceProvider, MockOriginalInvoice, MockReturnOrder


class UnsupportedMarketplaceError(ValueError):
    pass


class MockIntegrationService:
    def __init__(
        self,
        *,
        mercado_livre_client: MercadoLivreMockClient | None = None,
        shopee_client: ShopeeMockClient | None = None,
        tiny_client: TinyMockClient | None = None,
    ) -> None:
        self.mercado_livre_client = mercado_livre_client or MercadoLivreMockClient()
        self.shopee_client = shopee_client or ShopeeMockClient()
        self.tiny_client = tiny_client or TinyMockClient()

    async def list_marketplace_returns(
        self,
        *,
        company_id: UUID,
        marketplace: MarketplaceProvider,
        scenario: MockScenario = "success",
    ) -> list[MockReturnOrder]:
        if marketplace == "MERCADO_LIVRE":
            return await self.mercado_livre_client.list_return_orders(
                company_id=company_id,
                scenario=scenario,
            )
        if marketplace == "SHOPEE":
            return await self.shopee_client.list_return_orders(
                company_id=company_id,
                scenario=scenario,
            )
        raise UnsupportedMarketplaceError("Unsupported marketplace")

    async def get_tiny_original_invoice(
        self,
        *,
        company_id: UUID,
        external_order_id: str,
        scenario: MockScenario = "success",
    ) -> MockOriginalInvoice:
        return await self.tiny_client.get_original_invoice(
            company_id=company_id,
            external_order_id=external_order_id,
            scenario=scenario,
        )

    async def link_first_return_to_original_invoice(
        self,
        *,
        company_id: UUID,
        marketplace: MarketplaceProvider,
    ) -> tuple[MockReturnOrder, MockOriginalInvoice]:
        returns = await self.list_marketplace_returns(company_id=company_id, marketplace=marketplace)
        return_order = returns[0]
        invoice = await self.get_tiny_original_invoice(
            company_id=company_id,
            external_order_id=return_order.external_order_id,
        )
        return return_order, invoice

from decimal import Decimal
from uuid import UUID

from app.integrations.mock_scenarios import MockScenario, raise_for_mock_scenario
from app.schemas.mock_integrations import MockReturnItem, MockReturnOrder, utc_datetime


class MercadoLivreMockClient:
    provider = "MERCADO_LIVRE"

    async def list_return_orders(
        self,
        *,
        company_id: UUID,
        scenario: MockScenario = "success",
    ) -> list[MockReturnOrder]:
        raise_for_mock_scenario(provider=self.provider, scenario=scenario)

        return [
            MockReturnOrder(
                company_id=company_id,
                external_order_id="ML-RETURN-1001",
                marketplace="MERCADO_LIVRE",
                status="RETURNED",
                occurred_at=utc_datetime(2026, 6, 4, 12, 30),
                buyer_reference="buyer-ml-001",
                items=[
                    MockReturnItem(
                        sku="SKU-ML-001",
                        name="Produto devolvido Mercado Livre",
                        quantity=Decimal("1"),
                        unit_price=Decimal("129.90"),
                    )
                ],
            )
        ]

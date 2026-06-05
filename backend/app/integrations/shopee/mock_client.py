from decimal import Decimal
from uuid import UUID

from app.integrations.mock_scenarios import MockScenario, raise_for_mock_scenario
from app.schemas.mock_integrations import MockReturnItem, MockReturnOrder, utc_datetime


class ShopeeMockClient:
    provider = "SHOPEE"

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
                external_order_id="SHP-RETURN-2001",
                marketplace="SHOPEE",
                status="RETURN_REQUESTED",
                occurred_at=utc_datetime(2026, 6, 4, 13, 45),
                buyer_reference="buyer-shopee-001",
                items=[
                    MockReturnItem(
                        sku="SKU-SHP-001",
                        name="Produto devolvido Shopee",
                        quantity=Decimal("2"),
                        unit_price=Decimal("49.90"),
                    )
                ],
            )
        ]

from decimal import Decimal
from uuid import UUID

from app.integrations.errors import MockIntegrationError
from app.integrations.mock_scenarios import MockScenario, raise_for_mock_scenario
from app.schemas.mock_integrations import MockOriginalInvoice, MockReturnItem, utc_datetime


class TinyMockClient:
    provider = "TINY"

    async def get_original_invoice(
        self,
        *,
        company_id: UUID,
        external_order_id: str,
        scenario: MockScenario = "success",
    ) -> MockOriginalInvoice:
        raise_for_mock_scenario(provider=self.provider, scenario=scenario)
        if external_order_id not in {"ML-RETURN-1001", "SHP-RETURN-2001"}:
            raise MockIntegrationError(
                code="MOCK_NOT_FOUND",
                message="Original invoice was not found in Tiny mock data",
                provider=self.provider,
                retryable=False,
            )

        return MockOriginalInvoice(
            company_id=company_id,
            external_order_id=external_order_id,
            original_nfe_key="35260612345678000199550010000010011000010010",
            invoice_number="1001",
            issued_at=utc_datetime(2026, 6, 1, 10, 0),
            customer_document="12345678901",
            items=[
                MockReturnItem(
                    sku="SKU-ML-001" if external_order_id.startswith("ML-") else "SKU-SHP-001",
                    name="Produto da NF-e original simulada",
                    quantity=Decimal("1"),
                    unit_price=Decimal("129.90"),
                )
            ],
        )

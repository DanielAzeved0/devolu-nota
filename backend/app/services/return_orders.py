from typing import Any
from uuid import UUID

from app.models import ReturnOrder, User
from app.repositories.return_orders import ReturnOrderRepository
from app.schemas.mock_integrations import MockReturnOrder
from app.schemas.return_orders import ReturnOrderMockSyncRequest, ReturnOrderMockSyncResponse
from app.services.companies import COMPANY_OPERATOR_ROLES, CompanyService
from app.services.mock_integrations import MockIntegrationService


class ReturnOrderMockSyncService:
    def __init__(
        self,
        *,
        companies: CompanyService,
        return_orders: ReturnOrderRepository,
        mock_integrations: MockIntegrationService | None = None,
    ) -> None:
        self.companies = companies
        self.return_orders = return_orders
        self.mock_integrations = mock_integrations or MockIntegrationService()

    async def sync_marketplace_returns(
        self,
        *,
        company_id: UUID,
        payload: ReturnOrderMockSyncRequest,
        current_user: User,
    ) -> ReturnOrderMockSyncResponse:
        await self.companies.require_company_role(
            company_id=company_id,
            current_user=current_user,
            allowed_roles=COMPANY_OPERATOR_ROLES,
        )
        mock_returns = await self.mock_integrations.list_marketplace_returns(
            company_id=company_id,
            marketplace=payload.marketplace,
            scenario=payload.scenario,
        )
        marketplace_account = await self.return_orders.ensure_mock_marketplace_account(
            company_id=company_id,
            marketplace=payload.marketplace,
        )

        created = 0
        updated = 0
        skipped = 0
        synced_items: list[ReturnOrder] = []

        for mock_return in mock_returns:
            payload_data = self._build_safe_payload(mock_return)
            existing = await self.return_orders.get_by_company_marketplace_external_id(
                company_id=company_id,
                marketplace=payload.marketplace,
                external_order_id=mock_return.external_order_id,
            )
            if existing is None:
                return_order = await self.return_orders.create(
                    company_id=company_id,
                    marketplace_account_id=marketplace_account.id,
                    marketplace=payload.marketplace,
                    external_order_id=mock_return.external_order_id,
                    payload=payload_data,
                )
                created += 1
                synced_items.append(return_order)
                continue

            changed = False
            if existing.payload != payload_data:
                existing.payload = payload_data
                changed = True

            if changed:
                updated += 1
            else:
                skipped += 1
            synced_items.append(existing)

        return ReturnOrderMockSyncResponse(
            company_id=company_id,
            marketplace=payload.marketplace,
            created=created,
            updated=updated,
            skipped=skipped,
            items=synced_items,
        )

    def _build_safe_payload(self, mock_return: MockReturnOrder) -> dict[str, Any]:
        return {
            "status": mock_return.status,
            "occurred_at": mock_return.occurred_at.isoformat(),
            "buyer_reference": mock_return.buyer_reference,
            "items": [
                {
                    "sku": item.sku,
                    "name": item.name,
                    "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price),
                }
                for item in mock_return.items
            ],
        }

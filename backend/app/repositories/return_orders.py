from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Integration, MarketplaceAccount, ReturnOrder


class ReturnOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_company_marketplace_external_id(
        self,
        *,
        company_id: UUID,
        marketplace: str,
        external_order_id: str,
    ) -> ReturnOrder | None:
        result = await self.session.execute(
            select(ReturnOrder).where(
                ReturnOrder.company_id == company_id,
                ReturnOrder.marketplace == marketplace,
                ReturnOrder.external_order_id == external_order_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_company_id(self, *, company_id: UUID, return_order_id: UUID) -> ReturnOrder | None:
        result = await self.session.execute(
            select(ReturnOrder).where(
                ReturnOrder.id == return_order_id,
                ReturnOrder.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        company_id: UUID,
        marketplace_account_id: UUID,
        marketplace: str,
        external_order_id: str,
        payload: dict[str, Any],
        customer_document: str | None = None,
        customer_name: str | None = None,
    ) -> ReturnOrder:
        return_order = ReturnOrder(
            company_id=company_id,
            marketplace_account_id=marketplace_account_id,
            marketplace=marketplace,
            external_order_id=external_order_id,
            status="OPEN",
            customer_document=customer_document,
            customer_name=customer_name,
            payload=payload,
        )
        self.session.add(return_order)
        await self.session.flush()
        await self.session.refresh(return_order)
        return return_order

    async def ensure_mock_marketplace_account(
        self,
        *,
        company_id: UUID,
        marketplace: str,
    ) -> MarketplaceAccount:
        external_account_id = f"mock-{marketplace.lower()}-{company_id}"
        result = await self.session.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.company_id == company_id,
                MarketplaceAccount.marketplace == marketplace,
                MarketplaceAccount.external_account_id == external_account_id,
            )
        )
        marketplace_account = result.scalar_one_or_none()
        if marketplace_account is not None:
            return marketplace_account

        integration = await self._ensure_mock_integration(company_id=company_id, marketplace=marketplace)
        marketplace_account = MarketplaceAccount(
            company_id=company_id,
            integration_id=integration.id,
            marketplace=marketplace,
            external_account_id=external_account_id,
            status="ACTIVE",
        )
        self.session.add(marketplace_account)
        await self.session.flush()
        await self.session.refresh(marketplace_account)
        return marketplace_account

    async def _ensure_mock_integration(self, *, company_id: UUID, marketplace: str) -> Integration:
        result = await self.session.execute(
            select(Integration).where(
                Integration.company_id == company_id,
                Integration.provider == marketplace,
                Integration.settings["mock"].as_boolean().is_(True),
            )
        )
        integration = result.scalar_one_or_none()
        if integration is not None:
            return integration

        integration = Integration(
            company_id=company_id,
            provider=marketplace,
            status="ACTIVE",
            settings={"mock": True},
            encrypted_credentials=None,
        )
        self.session.add(integration)
        await self.session.flush()
        await self.session.refresh(integration)
        return integration

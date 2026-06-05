from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Integration


class IntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        company_id: UUID,
        provider: str,
        settings: dict[str, object] | None,
        encrypted_credentials: dict[str, str] | None,
    ) -> Integration:
        integration = Integration(
            company_id=company_id,
            provider=provider,
            status="ACTIVE" if encrypted_credentials else "DISCONNECTED",
            settings=settings,
            encrypted_credentials=encrypted_credentials,
        )
        self.session.add(integration)
        await self.session.flush()
        await self.session.refresh(integration)
        return integration

    async def list_by_company(self, company_id: UUID) -> list[Integration]:
        result = await self.session.execute(
            select(Integration)
            .where(Integration.company_id == company_id)
            .order_by(Integration.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_company(self, *, company_id: UUID, integration_id: UUID) -> Integration | None:
        result = await self.session.execute(
            select(Integration).where(
                Integration.id == integration_id,
                Integration.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

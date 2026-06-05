from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, CompanyUser, User


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, legal_name: str, document: str, trade_name: str | None) -> Company:
        company = Company(
            legal_name=legal_name,
            trade_name=trade_name,
            document=document,
            status="ACTIVE",
        )
        self.session.add(company)
        await self.session.flush()
        await self.session.refresh(company)
        return company

    async def get_by_document(self, document: str) -> Company | None:
        result = await self.session.execute(select(Company).where(Company.document == document))
        return result.scalar_one_or_none()

    async def get_accessible_by_id(self, *, company_id: UUID, user_id: UUID) -> Company | None:
        result = await self.session.execute(
            select(Company)
            .join(CompanyUser, CompanyUser.company_id == Company.id)
            .where(
                Company.id == company_id,
                Company.status == "ACTIVE",
                CompanyUser.user_id == user_id,
                CompanyUser.status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[Company]:
        result = await self.session.execute(
            select(Company)
            .join(CompanyUser, CompanyUser.company_id == Company.id)
            .where(
                Company.status == "ACTIVE",
                CompanyUser.user_id == user_id,
                CompanyUser.status == "ACTIVE",
            )
            .order_by(Company.created_at.desc())
        )
        return list(result.scalars().all())


class CompanyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_membership(self, *, company_id: UUID, user_id: UUID) -> CompanyUser | None:
        result = await self.session.execute(
            select(CompanyUser).where(
                CompanyUser.company_id == company_id,
                CompanyUser.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_membership(self, *, company_id: UUID, user_id: UUID) -> CompanyUser | None:
        result = await self.session.execute(
            select(CompanyUser).where(
                CompanyUser.company_id == company_id,
                CompanyUser.user_id == user_id,
                CompanyUser.status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none()

    async def create(self, *, company_id: UUID, user_id: UUID, role: str) -> CompanyUser:
        membership = CompanyUser(
            company_id=company_id,
            user_id=user_id,
            role=role,
            status="ACTIVE",
        )
        self.session.add(membership)
        await self.session.flush()
        await self.session.refresh(membership)
        return membership

    async def list_company_users(self, company_id: UUID) -> list[tuple[CompanyUser, User]]:
        result = await self.session.execute(
            select(CompanyUser, User)
            .join(User, User.id == CompanyUser.user_id)
            .where(CompanyUser.company_id == company_id)
            .order_by(CompanyUser.created_at.asc())
        )
        return list(result.all())

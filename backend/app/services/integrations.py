from uuid import UUID

from app.models import Integration, User
from app.repositories.integrations import IntegrationRepository
from app.schemas.integrations import (
    IntegrationCreateRequest,
    IntegrationCredentialsRequest,
    IntegrationUpdateRequest,
)
from app.services.companies import CompanyService
from app.services.integration_credentials import encrypt_integration_credentials


class IntegrationNotFoundError(ValueError):
    pass


class IntegrationService:
    def __init__(
        self,
        integrations: IntegrationRepository,
        companies: CompanyService,
    ) -> None:
        self.integrations = integrations
        self.companies = companies

    async def create_integration(
        self,
        *,
        company_id: UUID,
        payload: IntegrationCreateRequest,
        current_user: User,
    ) -> Integration:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        encrypted_credentials = (
            encrypt_integration_credentials(payload.credentials.to_sensitive_dict())
            if payload.credentials is not None
            else None
        )
        return await self.integrations.create(
            company_id=company_id,
            provider=payload.provider,
            settings=payload.settings,
            encrypted_credentials=encrypted_credentials,
        )

    async def list_integrations(self, *, company_id: UUID, current_user: User) -> list[Integration]:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        return await self.integrations.list_by_company(company_id)

    async def get_integration(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        current_user: User,
    ) -> Integration:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        integration = await self.integrations.get_by_company(
            company_id=company_id,
            integration_id=integration_id,
        )
        if integration is None:
            raise IntegrationNotFoundError("Integration not found")
        return integration

    async def update_integration(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        payload: IntegrationUpdateRequest,
        current_user: User,
    ) -> Integration:
        integration = await self.get_integration(
            company_id=company_id,
            integration_id=integration_id,
            current_user=current_user,
        )
        if payload.status is not None:
            integration.status = payload.status
        if payload.settings is not None:
            integration.settings = payload.settings
        return integration

    async def replace_credentials(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        payload: IntegrationCredentialsRequest,
        current_user: User,
    ) -> Integration:
        integration = await self.get_integration(
            company_id=company_id,
            integration_id=integration_id,
            current_user=current_user,
        )
        integration.encrypted_credentials = encrypt_integration_credentials(payload.to_sensitive_dict())
        integration.status = "ACTIVE"
        return integration

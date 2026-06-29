from uuid import UUID

from app.models import Company, CompanyUser, User
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.users import UserRepository
from app.schemas.companies import CompanyCreateRequest, CompanyUserCreateRequest, CompanyUserPublic

# Politica de autorizacao por empresa:
# - COMPANY_READER_ROLES: leitura (devolucoes, notas, lotes, documentos, auditoria, usuarios).
# - COMPANY_OPERATOR_ROLES: mutacoes operacionais (sync, notas, emissao).
# - COMPANY_ADMIN_ROLES: gestao sensivel (usuarios, integracoes, credenciais, retencao manual).
COMPANY_ADMIN_ROLES = ("OWNER", "ADMIN")
COMPANY_OPERATOR_ROLES = ("OWNER", "ADMIN", "OPERATOR")
COMPANY_READER_ROLES = ("OWNER", "ADMIN", "OPERATOR", "VIEWER")


class CompanyDocumentAlreadyExistsError(ValueError):
    pass


class CompanyNotFoundError(ValueError):
    pass


class UserNotFoundError(ValueError):
    pass


class CompanyUserAlreadyExistsError(ValueError):
    pass


class CompanyPermissionDeniedError(ValueError):
    pass


class CompanyService:
    def __init__(
        self,
        companies: CompanyRepository,
        company_users: CompanyUserRepository,
        users: UserRepository,
    ) -> None:
        self.companies = companies
        self.company_users = company_users
        self.users = users

    async def create_company(self, *, payload: CompanyCreateRequest, current_user: User) -> Company:
        existing_company = await self.companies.get_by_document(payload.document)
        if existing_company is not None:
            raise CompanyDocumentAlreadyExistsError("Company document already exists")

        company = await self.companies.create(
            legal_name=payload.legal_name,
            trade_name=payload.trade_name,
            document=payload.document,
        )
        await self.company_users.create(company_id=company.id, user_id=current_user.id, role="OWNER")
        return company

    async def list_companies(self, current_user: User) -> list[Company]:
        return await self.companies.list_for_user(current_user.id)

    async def get_company(self, *, company_id: UUID, current_user: User) -> Company:
        company = await self.companies.get_accessible_by_id(
            company_id=company_id,
            user_id=current_user.id,
        )
        if company is None:
            raise CompanyNotFoundError("Company not found")
        return company

    async def require_company_role(
        self,
        *,
        company_id: UUID,
        current_user: User,
        allowed_roles: tuple[str, ...],
    ) -> CompanyUser:
        await self.get_company(company_id=company_id, current_user=current_user)
        membership = await self.company_users.get_active_membership(
            company_id=company_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise CompanyNotFoundError("Company not found")
        if membership.role not in allowed_roles:
            raise CompanyPermissionDeniedError("Insufficient company role")
        return membership

    async def list_company_users(
        self, *, company_id: UUID, current_user: User
    ) -> list[CompanyUserPublic]:
        await self.require_company_role(
            company_id=company_id,
            current_user=current_user,
            allowed_roles=COMPANY_READER_ROLES,
        )
        rows = await self.company_users.list_company_users(company_id)
        return [self._to_public_membership(membership, user) for membership, user in rows]

    async def add_company_user(
        self,
        *,
        company_id: UUID,
        payload: CompanyUserCreateRequest,
        current_user: User,
    ) -> CompanyUserPublic:
        await self.require_company_role(
            company_id=company_id,
            current_user=current_user,
            allowed_roles=COMPANY_ADMIN_ROLES,
        )

        target_user = await self.users.get_by_id(payload.user_id)
        if target_user is None:
            raise UserNotFoundError("User not found")

        existing_membership = await self.company_users.get_membership(
            company_id=company_id,
            user_id=payload.user_id,
        )
        if existing_membership is not None:
            raise CompanyUserAlreadyExistsError("Company user already exists")

        membership = await self.company_users.create(
            company_id=company_id,
            user_id=payload.user_id,
            role=payload.role,
        )
        return self._to_public_membership(membership, target_user)

    def _to_public_membership(self, membership: CompanyUser, user: User) -> CompanyUserPublic:
        return CompanyUserPublic(
            id=membership.id,
            company_id=membership.company_id,
            user_id=membership.user_id,
            user_email=user.email,
            user_name=user.name,
            role=membership.role,
            status=membership.status,
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )

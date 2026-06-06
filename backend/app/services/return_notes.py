from uuid import UUID

from app.models import ReturnNote, User
from app.repositories.return_notes import ReturnNoteRepository
from app.repositories.return_orders import ReturnOrderRepository
from app.schemas.return_notes import ReturnNoteMockCreateRequest
from app.services.companies import CompanyService
from app.services.mock_integrations import MockIntegrationService
from app.services.return_orders import ReturnOrderNotFoundError


class ReturnNoteAlreadyExistsError(ValueError):
    pass


class ReturnNoteInvalidOriginalInvoiceError(ValueError):
    pass


class ReturnNoteNotFoundError(ValueError):
    pass


class ReturnNoteMockCreationService:
    def __init__(
        self,
        *,
        companies: CompanyService,
        return_orders: ReturnOrderRepository,
        return_notes: ReturnNoteRepository,
        mock_integrations: MockIntegrationService | None = None,
    ) -> None:
        self.companies = companies
        self.return_orders = return_orders
        self.return_notes = return_notes
        self.mock_integrations = mock_integrations or MockIntegrationService()

    async def create_mock_return_note(
        self,
        *,
        company_id: UUID,
        return_order_id: UUID,
        payload: ReturnNoteMockCreateRequest,
        current_user: User,
    ) -> ReturnNote:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        return_order = await self.return_orders.get_by_company_id(
            company_id=company_id,
            return_order_id=return_order_id,
        )
        if return_order is None:
            raise ReturnOrderNotFoundError("Return order not found")

        existing_return_note = await self.return_notes.get_active_by_return_order(
            company_id=company_id,
            return_order_id=return_order_id,
        )
        if existing_return_note is not None:
            raise ReturnNoteAlreadyExistsError("Return note already exists")

        original_invoice = await self.mock_integrations.get_tiny_original_invoice(
            company_id=company_id,
            external_order_id=return_order.external_order_id,
            scenario=payload.scenario,
        )
        if len(original_invoice.original_nfe_key) != 44:
            raise ReturnNoteInvalidOriginalInvoiceError("Original invoice key is invalid")

        return_order.original_nfe_key = original_invoice.original_nfe_key
        return_order.status = "LINKED_TO_NFE"
        return await self.return_notes.create_mock_draft(
            company_id=company_id,
            return_order_id=return_order_id,
            original_nfe_key=original_invoice.original_nfe_key,
        )


class ReturnNoteQueryService:
    def __init__(
        self,
        *,
        companies: CompanyService,
        return_notes: ReturnNoteRepository,
    ) -> None:
        self.companies = companies
        self.return_notes = return_notes

    async def list_company_return_notes(
        self,
        *,
        company_id: UUID,
        current_user: User,
        status: str | None = None,
        return_order_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReturnNote]:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        return await self.return_notes.list_for_company(
            company_id=company_id,
            status=status,
            return_order_id=return_order_id,
            limit=limit,
            offset=offset,
        )

    async def get_company_return_note(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID,
        current_user: User,
    ) -> ReturnNote:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        return_note = await self.return_notes.get_by_company_id(
            company_id=company_id,
            return_note_id=return_note_id,
        )
        if return_note is None:
            raise ReturnNoteNotFoundError("Return note not found")
        return return_note

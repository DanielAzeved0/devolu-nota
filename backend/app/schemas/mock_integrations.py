from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MarketplaceProvider = Literal["MERCADO_LIVRE", "SHOPEE"]
ExternalProvider = Literal["TINY", "MERCADO_LIVRE", "SHOPEE"]
MockErrorCode = Literal["MOCK_TIMEOUT", "MOCK_NOT_FOUND", "MOCK_INVALID_TOKEN", "MOCK_EXTERNAL_ERROR"]
ReturnStatus = Literal["RETURN_REQUESTED", "RETURNED"]


class MockIntegrationErrorPayload(BaseModel):
    code: MockErrorCode
    message: str
    provider: ExternalProvider
    retryable: bool


class MockReturnItem(BaseModel):
    sku: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., gt=0)


class MockReturnOrder(BaseModel):
    company_id: UUID
    external_order_id: str = Field(..., min_length=1)
    marketplace: MarketplaceProvider
    status: ReturnStatus
    occurred_at: datetime
    buyer_reference: str | None = None
    items: list[MockReturnItem] = Field(..., min_length=1)


class MockOriginalInvoice(BaseModel):
    company_id: UUID
    external_order_id: str = Field(..., min_length=1)
    original_nfe_key: str = Field(..., min_length=44, max_length=44)
    invoice_number: str = Field(..., min_length=1)
    issued_at: datetime
    customer_document: str | None = None
    items: list[MockReturnItem] = Field(..., min_length=1)


def utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)

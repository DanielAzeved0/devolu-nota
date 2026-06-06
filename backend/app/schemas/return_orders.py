from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.integrations.mock_scenarios import MockScenario
from app.schemas.mock_integrations import MarketplaceProvider


class ReturnOrderMockSyncRequest(BaseModel):
    marketplace: MarketplaceProvider
    scenario: MockScenario = "success"


class ReturnOrderPublic(BaseModel):
    id: UUID
    company_id: UUID
    marketplace_account_id: UUID
    marketplace: str
    external_order_id: str
    status: str
    original_nfe_key: str | None = None
    customer_document: str | None = None
    customer_name: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReturnOrderMockSyncResponse(BaseModel):
    company_id: UUID
    marketplace: MarketplaceProvider
    created: int
    updated: int
    skipped: int
    items: list[ReturnOrderPublic]


class ReturnOrderListResponse(BaseModel):
    items: list[ReturnOrderPublic]
    limit: int
    offset: int
    count: int

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import validation_exception_handler
from app.api.v1.routes.audit_logs import router as audit_logs_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.companies import router as companies_router
from app.api.v1.routes.emission_batches import router as emission_batches_router
from app.api.v1.routes.fiscal_documents import router as fiscal_documents_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.integrations import router as integrations_router
from app.api.v1.routes.return_notes import router as return_notes_router
from app.api.v1.routes.return_orders import router as return_orders_router
from app.api.v1.routes.retention import router as retention_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(integrations_router)
app.include_router(return_orders_router)
app.include_router(return_notes_router)
app.include_router(fiscal_documents_router)
app.include_router(emission_batches_router)
app.include_router(audit_logs_router)
app.include_router(retention_router)

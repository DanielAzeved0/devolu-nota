from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Verifica status da API")
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="api")


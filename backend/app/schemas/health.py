from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    service: str

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok", "service": "api"}})


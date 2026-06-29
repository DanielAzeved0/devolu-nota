from pydantic import BaseModel


class RetentionApplyResponse(BaseModel):
    moved_to_cold: int
    moved_to_deleted: int
    skipped: int

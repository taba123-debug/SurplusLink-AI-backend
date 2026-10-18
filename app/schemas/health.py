from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["surpluslink-api"] = "surpluslink-api"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["connected"] = "connected"


class PingResponse(BaseModel):
    message: str = "SurplusLink API v1 is running"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail

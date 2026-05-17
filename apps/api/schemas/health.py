from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: Literal["ok", "error"]
    redis: Literal["ok", "error"]
    minio: Literal["ok", "error"]

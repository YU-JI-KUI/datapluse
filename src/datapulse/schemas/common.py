"""公共 Pydantic 模型：分页参数、分页响应等"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Pagination(BaseModel):
    page:      int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    total:     int = 0

"""标注相关 Pydantic Schema"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnnotationCreate(BaseModel):
    data_id: int   = Field(..., description="数据ID")
    label:   str   = Field(..., min_length=1, description="标注标签")


class CommentCreate(BaseModel):
    data_id: int  = Field(..., description="数据ID")
    comment: str  = Field(..., min_length=1, description="评论内容")


class DataStateUpdate(BaseModel):
    data_id: int = Field(..., description="数据ID")
    stage:   str = Field(..., description="目标阶段：cleaned / pre_annotated / annotated / checked")

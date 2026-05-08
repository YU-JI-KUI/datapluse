"""标注相关 Pydantic Schema"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnnotationCreate(BaseModel):
    data_id:       int      = Field(..., description="数据ID")
    label:         str      = Field(..., min_length=1, description="标注标签")
    cot:           str | None = Field(None, description="Chain of Thought 标注理由（可选）")
    category:      str | None = Field(None, description="业务分类（来自 t_category.name）")
    keywords:      str | None = Field(None, description="关键词")
    keywords_desc: str | None = Field(None, description="关键词说明")


class CommentCreate(BaseModel):
    data_id: int  = Field(..., description="数据ID")
    comment: str  = Field(..., min_length=1, description="评论内容")


class DataStateUpdate(BaseModel):
    data_id: int = Field(..., description="数据ID")
    stage:   str = Field(..., description="目标阶段：cleaned / pre_annotated / annotated / checked")

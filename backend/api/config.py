"""
配置中心 API（DB 驱动，per-dataset）
- 读取/更新数据集配置（存储于 PostgreSQL system_config 表）
- 每次读取直接查数据库，天然支持热更新
- 重载 embedding 模型 / 重建向量索引
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user
from modules.embedding import reload_model
from modules.vector import rebuild_index
from storage.db import get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]


@router.get("")
async def get_config(
    user: CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """获取指定 dataset 的完整配置（直接读 DB，热更新）"""
    db = get_db()
    cfg = db.get_dataset_config(dataset_id)
    return {"success": True, "data": cfg}


@router.post("/update")
async def update_config(
    body: ConfigUpdateRequest,
    user: CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """更新指定 dataset 的配置并立即生效（写入 DB）"""
    if not user.has_permission("config:write"):
        raise HTTPException(403, "无权限修改配置")
    db = get_db()
    # 确认 dataset 存在
    if not db.get_dataset(dataset_id):
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    db.set_dataset_config(dataset_id, body.config, updated_by=user.username)
    return {"success": True, "message": "配置已更新并生效"}


@router.post("/reload-model")
async def reload_embedding_model(user: CurrentUser):
    """强制重新加载 embedding 模型（更改 model_path 后调用）"""
    try:
        reload_model()
        return {"success": True, "message": "Embedding 模型已重载"}
    except Exception as e:
        raise HTTPException(500, f"模型重载失败: {e}")


@router.post("/rebuild-index")
async def rebuild_vector_index(user: CurrentUser):
    """从本地向量文件重新构建 FAISS 索引"""
    try:
        count = rebuild_index()
        return {"success": True, "message": f"索引重建完成，共 {count} 条向量"}
    except Exception as e:
        raise HTTPException(500, f"索引重建失败: {e}")

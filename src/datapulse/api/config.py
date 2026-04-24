"""
配置中心 API（DB 驱动，per-dataset）
- 读取/更新数据集配置（存储于 PostgreSQL system_config 表）
- 每次读取直接查数据库，天然支持热更新
- 重载 embedding 模型 / 后台异步重建向量索引
"""

from __future__ import annotations

import structlog
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.modules.embedding import reload_model
from datapulse.modules.vector import rebuild_index, invalidate_index
from datapulse.repository.base import get_db

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
_log        = structlog.get_logger(__name__)


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]


@router.get("")
async def get_config(
    user:       CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """获取指定 dataset 的完整配置（直接读 DB，热更新）"""
    db  = get_db()
    cfg = db.get_dataset_config(dataset_id)
    return {"success": True, "data": cfg}


@router.post("/update")
async def update_config(
    body:       ConfigUpdateRequest,
    user:       CurrentUser,
    dataset_id: int = Query(..., description="数据集 ID"),
):
    """更新指定 dataset 的配置并立即生效（写入 DB）"""
    if not user.has_permission("config:write"):
        raise HTTPException(403, "无权限修改配置")
    db = get_db()
    if not db.get_dataset(dataset_id):
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    db.set_dataset_config(dataset_id, body.config, updated_by=user.username)
    return {"success": True, "message": "配置已更新并生效"}


@router.post("/reload-model")
async def reload_embedding_model(user: CurrentUser):
    """清除 embedding 模型缓存，下次调用时自动按 EMBEDDING_MODEL_PATH 重新加载"""
    try:
        reload_model()
        return {"success": True, "message": "Embedding 模型缓存已清除，将在下次使用时重新加载"}
    except Exception as e:
        raise HTTPException(500, f"模型重载失败: {e}")


def _do_rebuild_index(dataset_id: int) -> None:
    """后台执行索引重建（在线程池中运行，不阻塞事件循环）"""
    try:
        count = rebuild_index(dataset_id)
        _log.info("vector index rebuild completed", dataset_id=dataset_id, count=count)
    except Exception as e:
        _log.error("vector index rebuild failed", dataset_id=dataset_id, error=str(e))


@router.post("/rebuild-index")
async def rebuild_vector_index(
    background_tasks: BackgroundTasks,
    user:             CurrentUser,
    dataset_id:       int = Query(..., description="数据集 ID"),
):
    """后台异步重建指定 dataset 的 FAISS 索引（立即返回，重建在后台执行）。
    对于 6 万条数据，从 PostgreSQL 加载向量 + 重建 FAISS 索引可能耗时数十秒，
    改为异步后台执行可避免请求超时和界面卡死。
    """
    if not user.has_permission("config:write"):
        raise HTTPException(403, "无权限执行索引重建")
    db = get_db()
    if not db.get_dataset(dataset_id):
        raise HTTPException(404, f"数据集不存在: {dataset_id}")

    # 先使内存缓存失效，防止冲突检测读到旧索引
    invalidate_index(dataset_id)
    background_tasks.add_task(_do_rebuild_index, dataset_id)

    return {
        "success": True,
        "message": "索引重建已在后台启动，完成后可正常使用冲突检测功能",
    }

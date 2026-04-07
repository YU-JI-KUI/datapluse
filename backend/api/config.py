"""
配置中心 API
- 读取当前配置
- 更新配置（立即生效）
- 重载 embedding 模型
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user
from config.settings import get_settings
from modules.embedding import reload_model
from modules.vector import rebuild_index

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]


@router.get("")
async def get_config(user: CurrentUser):
    """获取完整配置（不含密码）"""
    settings = get_settings()
    data = dict(settings.raw)
    # 隐藏密码
    if "auth" in data:
        data["auth"] = {
            k: "***" if k == "admin_password" else v
            for k, v in data["auth"].items()
        }
    return {"success": True, "data": data}


@router.post("/update")
async def update_config(body: ConfigUpdateRequest, user: CurrentUser):
    """更新配置并持久化到 config.yaml"""
    settings = get_settings()
    new_config = body.config

    # 保护密码字段（不允许通过 API 修改）
    if "auth" in new_config and "admin_password" in new_config["auth"]:
        if new_config["auth"]["admin_password"] == "***":
            new_config["auth"]["admin_password"] = settings.admin_password

    try:
        settings.update(new_config)
    except Exception as e:
        raise HTTPException(500, f"配置保存失败: {e}")

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
    """从 NAS 重新构建 FAISS 向量索引"""
    try:
        count = rebuild_index()
        return {"success": True, "message": f"索引重建完成，共 {count} 条向量"}
    except Exception as e:
        raise HTTPException(500, f"索引重建失败: {e}")

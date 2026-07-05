"""
角色权限管理路由
GET /api/permissions            — 权限全集（按模块分组，供前端渲染两级树）
GET /api/roles                  — 所有角色及其权限
PUT /api/roles/{name}/permissions — 覆盖式更新某角色权限（admin 不可改）

角色权限变更后需相关用户重新登录才生效（权限随 JWT 下发）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, invalidate_role_cache, require_perm
from datapulse.core.exceptions import NotFoundError, ParamError
from datapulse.core.permissions import ALL_CODES, grouped_permissions
from datapulse.core.response import success
from datapulse.repository.base import get_db

router     = APIRouter()
RoleManage = Annotated[UserInfo, Depends(require_perm("role:manage"))]


class UpdatePermissionsBody(BaseModel):
    permissions: list[str]


@router.get("/permissions")
async def list_permissions(user: RoleManage):
    """权限全集，按模块分组。前端据此渲染两级树。"""
    return success(grouped_permissions())


@router.get("/roles")
async def list_roles(user: RoleManage):
    """所有角色及其当前权限集。"""
    return success(get_db().list_roles())


@router.put("/roles/{name}/permissions")
async def update_role_permissions(name: str, body: UpdatePermissionsBody, user: RoleManage):
    """覆盖式更新角色权限。校验权限串合法、admin 不可改，更新后失效权限缓存。"""
    invalid = [p for p in body.permissions if p not in ALL_CODES]
    if invalid:
        raise ParamError(f"非法权限：{', '.join(invalid)}")

    db = get_db()
    try:
        updated = db.update_role_permissions(name, body.permissions, updated_by=user.username)
    except ValueError as e:
        raise ParamError(str(e))
    if updated is None:
        raise NotFoundError(f"角色不存在：{name}")

    invalidate_role_cache()
    return success(updated, message="权限已更新，相关用户重新登录后生效")

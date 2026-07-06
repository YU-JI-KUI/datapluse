"""
Admin 专用路由（仅 admin 角色可访问）

POST /api/admin/execute-sql   — 执行任意 SQL，返回查询结果或受影响行数
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from datapulse.router.auth import UserInfo, require_perm
from datapulse.core.response import success
from datapulse.repository.base import get_db

router    = APIRouter()
AdminUser = Annotated[UserInfo, Depends(require_perm("system:sql"))]


class ExecuteSQLBody(BaseModel):
    sql: str


@router.post("/execute-sql")
async def execute_sql(body: ExecuteSQLBody, user: AdminUser):
    """执行任意 SQL 语句，返回查询结果（SELECT）或受影响行数（DML）。
    仅 admin 可用，用于数据修复和临时数据操作。
    """
    raw_sql = body.sql.strip()
    if not raw_sql:
        return success({"rows": [], "columns": [], "rowcount": 0, "message": "SQL 为空"})

    db = get_db()
    with db._session() as session:
        result = session.execute(text(raw_sql))
        session.commit()

        # SELECT / RETURNING 类查询
        if result.returns_rows:
            columns = list(result.keys())
            rows: list[list[Any]] = []
            for row in result:
                rows.append([
                    str(v) if v is not None and not isinstance(v, (int, float, bool, str)) else v
                    for v in row
                ])
            return success({
                "columns": columns,
                "rows":    rows,
                "rowcount": len(rows),
                "message": f"查询返回 {len(rows)} 行",
            })
        else:
            # INSERT / UPDATE / DELETE
            rc = result.rowcount
            return success({
                "columns": [],
                "rows":    [],
                "rowcount": rc,
                "message": f"执行成功，影响 {rc} 行",
            })

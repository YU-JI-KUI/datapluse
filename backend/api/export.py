"""
导出 API
- 格式：JSON / Excel / CSV
- 支持模板导出（自定义字段映射）和默认导出
- 文件不落盘，直接 StreamingResponse 返回给前端
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Annotated, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user
from storage.db import AVAILABLE_FIELDS, DEFAULT_COLUMNS, get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class ExportRequest(BaseModel):
    dataset_id: int
    format: str = "json"                    # json | excel | csv
    status_filter: str = "checked"
    include_conflicts: bool = False
    template_id: Optional[int] = None      # 指定模板 ID，None 则用默认字段


def _apply_columns(item: dict, columns: list[dict]) -> dict:
    """按模板列定义将 item 转换为输出 dict"""
    return {
        col["target"]: item.get(col["source"])
        for col in columns
        if col.get("include", True)
    }


@router.post("/create")
async def create_export(body: ExportRequest, user: CurrentUser):
    """生成导出文件并直接流式返回（文件不落盘，下载即走）"""
    if not user.has_permission("export:create"):
        raise HTTPException(403, "无权限导出数据")
    db = get_db()

    items = db.list_by_status(body.dataset_id, body.status_filter)
    if not body.include_conflicts:
        items = [i for i in items if not i.get("conflict_flag")]
    if not items:
        raise HTTPException(404, f"没有可导出的数据（状态={body.status_filter}）")

    if body.template_id:
        tpl = db.get_template(body.template_id)
        if not tpl:
            raise HTTPException(404, f"模板不存在: {body.template_id}")
        columns = tpl["columns"]
        fmt = tpl["format"]
    else:
        columns = DEFAULT_COLUMNS
        fmt = body.format

    clean_items = [_apply_columns(item, columns) for item in items]
    ts = datetime.now(_SHANGHAI_TZ).strftime("%Y%m%d_%H%M%S")

    if fmt == "excel":
        buf = io.BytesIO()
        pd.DataFrame(clean_items).to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        filename = f"datapulse_export_{ts}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return StreamingResponse(
            buf, media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    elif fmt == "csv":
        buf = io.StringIO()
        if clean_items:
            writer = csv.DictWriter(buf, fieldnames=clean_items[0].keys())
            writer.writeheader()
            writer.writerows(clean_items)
        filename = f"datapulse_export_{ts}.csv"
        return StreamingResponse(
            iter([buf.getvalue().encode("utf-8-sig")]),
            media_type="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    else:  # json
        content = json.dumps(clean_items, ensure_ascii=False, indent=2).encode("utf-8")
        filename = f"datapulse_export_{ts}.json"
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@router.get("/fields")
async def get_available_fields(user: CurrentUser):
    """返回所有可用的源字段（用于前端模板编辑器）"""
    return {"success": True, "data": AVAILABLE_FIELDS}

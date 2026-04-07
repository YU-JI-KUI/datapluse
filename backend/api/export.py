"""
导出 API
- 导出 checked 数据为 JSON / Excel
- 下载导出文件
- 查看已导出列表
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.auth import UserInfo, get_current_user
from storage.nas import get_nas

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]


class ExportRequest(BaseModel):
    format: str = "json"          # json | excel
    status_filter: str = "checked"  # 默认只导出 checked 数据
    include_conflicts: bool = False


@router.post("/create")
async def create_export(body: ExportRequest, user: CurrentUser):
    """生成导出文件"""
    nas = get_nas()

    # 获取待导出数据
    items = nas.list_by_status(body.status_filter)
    if not body.include_conflicts:
        items = [i for i in items if not i.get("conflict_flag")]

    if not items:
        raise HTTPException(404, f"没有可导出的数据（状态={body.status_filter}）")

    # 导出字段（去除内部字段）
    export_fields = [
        "id", "text", "label", "status",
        "model_pred", "model_score",
        "annotator", "annotated_at",
        "source_file", "created_at",
    ]
    clean_items = [
        {k: item.get(k) for k in export_fields}
        for item in items
    ]

    # 文件名
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    export_dir = nas.export_dir()

    if body.format == "excel":
        filename = f"datapluse_export_{ts}.xlsx"
        filepath = export_dir / filename
        df = pd.DataFrame(clean_items)
        df.to_excel(str(filepath), index=False, engine="openpyxl")
    else:
        filename = f"datapluse_export_{ts}.json"
        filepath = export_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(clean_items, f, ensure_ascii=False, indent=2)

    size = filepath.stat().st_size
    return {
        "success": True,
        "filename": filename,
        "count": len(clean_items),
        "size": size,
        "format": body.format,
    }


@router.get("/list")
async def list_exports(user: CurrentUser):
    """列出所有已导出文件"""
    nas = get_nas()
    return {"success": True, "data": nas.list_exports()}


@router.get("/download/{filename}")
async def download(filename: str, user: CurrentUser):
    """下载导出文件"""
    nas = get_nas()
    filepath = nas.export_dir() / filename
    if not filepath.exists():
        raise HTTPException(404, f"文件不存在: {filename}")

    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if filename.endswith(".xlsx")
        else "application/json"
    )
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
    )

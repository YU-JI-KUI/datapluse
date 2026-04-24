"""
导出 API
- 格式：JSON / Excel / CSV
- 支持模板导出（自定义字段映射）和默认导出
- 两步下载：POST /export/prepare 生成临时文件 → GET /export/download/{token} 浏览器原生下载
  浏览器原生 GET 导航不会触发 Chrome "不安全下载" 拦截（比 Blob URL 更可靠）
"""

from __future__ import annotations

import csv
import io
import json
import secrets
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.repository.base import AVAILABLE_FIELDS, DEFAULT_COLUMNS, get_db

router = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# ── 临时文件管理（内存 token → 文件路径，TTL 300s）────────────────────────────
_TEMP_DIR   = Path(tempfile.gettempdir()) / "datapulse_exports"
_TEMP_DIR.mkdir(parents=True, exist_ok=True)

_token_store: dict[str, dict] = {}   # token -> {path, filename, expires_at}
_store_lock  = threading.Lock()


def _register_file(path: Path, filename: str, ttl: int = 300) -> str:
    token = secrets.token_urlsafe(32)
    with _store_lock:
        _token_store[token] = {
            "path":       str(path),
            "filename":   filename,
            "expires_at": time.time() + ttl,
        }
    # 异步后台清理过期文件
    def _cleanup():
        time.sleep(ttl + 10)
        with _store_lock:
            entry = _token_store.pop(token, None)
        if entry:
            try:
                Path(entry["path"]).unlink(missing_ok=True)
            except Exception:
                pass
    threading.Thread(target=_cleanup, daemon=True).start()
    return token


class ExportRequest(BaseModel):
    dataset_id: int
    format: str = "json"  # json | excel | csv
    status_filter: str = "checked"
    include_conflicts: bool = False
    template_id: int | None = None  # 指定模板 ID，None 则用默认字段


def _apply_columns(item: dict, columns: list[dict]) -> dict:
    """按模板列定义将 item 转换为输出 dict"""
    return {col["target"]: item.get(col["source"]) for col in columns if col.get("include", True)}


@router.post("/prepare")
async def prepare_export(body: ExportRequest, user: CurrentUser):
    """生成导出文件，写入服务端临时目录，返回一次性下载 token。
    前端拿到 token 后用 window.location.href 导航到 /api/export/download/{token}
    由浏览器原生触发下载，绕过 Chrome "不安全下载" 拦截。
    """
    if not user.has_permission("export:create"):
        raise HTTPException(403, "无权限导出数据")
    db = get_db()

    items = db.list_data_for_export(body.dataset_id, body.status_filter)
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
        filename = f"datapulse_export_{ts}.xlsx"
        fpath = _TEMP_DIR / filename
        pd.DataFrame(clean_items).to_excel(str(fpath), index=False, engine="openpyxl")
    elif fmt == "csv":
        filename = f"datapulse_export_{ts}.csv"
        fpath = _TEMP_DIR / filename
        buf = io.StringIO()
        if clean_items:
            writer = csv.DictWriter(buf, fieldnames=clean_items[0].keys())
            writer.writeheader()
            writer.writerows(clean_items)
        fpath.write_bytes(buf.getvalue().encode("utf-8-sig"))
    else:  # json
        filename = f"datapulse_export_{ts}.json"
        fpath = _TEMP_DIR / filename
        fpath.write_bytes(json.dumps(clean_items, ensure_ascii=False, indent=2).encode("utf-8"))

    token = _register_file(fpath, filename)
    return {"success": True, "data": {"token": token, "filename": filename}}


@router.get("/download/{token}")
async def download_export(token: str):
    """通过一次性 token 下载已生成的导出文件（无需 Authorization header，支持浏览器直接导航）"""
    with _store_lock:
        entry = _token_store.get(token)
    if not entry or time.time() > entry["expires_at"]:
        raise HTTPException(404, "下载链接已失效或不存在，请重新导出")

    fpath = Path(entry["path"])
    if not fpath.exists():
        raise HTTPException(404, "文件不存在，请重新导出")

    filename = entry["filename"]
    ext = fpath.suffix.lower()
    media_type_map = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv":  "text/csv; charset=utf-8-sig",
        ".json": "application/json",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(fpath),
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# 保留旧接口兼容（直接流式返回）
@router.post("/create")
async def create_export(body: ExportRequest, user: CurrentUser):
    """兼容旧接口：直接流式返回文件（不推荐，Excel 可能被浏览器拦截）"""
    result = await prepare_export(body, user)
    token = result["data"]["token"]
    with _store_lock:
        entry = _token_store.get(token)
    if not entry:
        raise HTTPException(500, "生成导出文件失败")
    fpath  = Path(entry["path"])
    filename = entry["filename"]
    ext = fpath.suffix.lower()
    media_type_map = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv":  "text/csv; charset=utf-8-sig",
        ".json": "application/json",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")
    return StreamingResponse(
        iter([fpath.read_bytes()]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fields")
async def get_available_fields(user: CurrentUser):
    """返回所有可用的源字段（用于前端模板编辑器）"""
    return {"success": True, "data": AVAILABLE_FIELDS}

"""
Dashboard 路由
GET /api/dashboard/annotator-stats — 每个标注员的今日 / 本周 / 本月工作量
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from datapulse.api.auth import UserInfo, get_current_user
from datapulse.core.response import success
from datapulse.repository.base import get_db

router      = APIRouter()
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
_SHANGHAI   = ZoneInfo("Asia/Shanghai")


def _compute_window_starts() -> tuple[datetime, datetime, datetime]:
    """按上海时区计算今日 / 本周（周一为起）/ 本月的起点。

    时区与 t_work_volume.created_at 写入端一致（base.py / annotation_repository.py
    都使用 _SHANGHAI），所以可以直接拿 naive datetime（去 tz）和无时区的 TIMESTAMP(6) 列比较。
    """
    now         = datetime.now(_SHANGHAI)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start  = today_start - timedelta(days=today_start.weekday())   # 周一为本周起
    month_start = today_start.replace(day=1)
    # PG 列是 TIMESTAMP(6) 无时区，但写入时用了 aware datetime；这里返回 aware 即可，
    # SQLAlchemy / psycopg 会按本地壁钟比较。
    return today_start, week_start, month_start


@router.get("/annotator-stats")
async def annotator_stats(
    user:       CurrentUser,
    dataset_id: int | None = Query(None, description="数据集 ID；不传则跨数据集汇总"),
):
    """返回所有标注员的今日 / 本周 / 本月标注与裁决次数。

    返回结构：
        [
          {
            "username":         "alice",
            "today_annotation": 23, "today_resolve": 5,
            "week_annotation":  142, "week_resolve":  12,
            "month_annotation": 580, "month_resolve":  45
          },
          ...
        ]

    数据来源：t_work_volume（撤销不计入；同一人对同一条数据反复修改算多次）。
    """
    db = get_db()
    today_start, week_start, month_start = _compute_window_starts()
    rows = db.get_annotator_stats(dataset_id, today_start, week_start, month_start)
    return success(rows)

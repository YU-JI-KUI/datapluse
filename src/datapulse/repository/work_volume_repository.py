"""Work-volume repository — t_work_volume

记录每次标注 / 裁决操作（仅 INSERT），用于 Dashboard 统计每个标注员
今日 / 本周 / 本月的工作量。撤销不写记录；同一人对同一条数据反复修改也算多次。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from datapulse.model.entities import WorkVolume

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_SHANGHAI)


class WorkVolumeRepository:
    """所有写入仅 INSERT；查询用条件聚合一次性返回所有标注员的今/周/月工作量。"""

    def __init__(self, session: Session):
        self.s = session

    # ── 写入 ────────────────────────────────────────────────────────────────
    def record_one(
        self,
        *,
        data_id: int,
        dataset_id: int,
        username: str,
        action_type: str,
        created_by: str = "",
    ) -> None:
        row = WorkVolume(
            username=username,
            dataset_id=dataset_id,
            data_id=data_id,
            action_type=action_type,
            created_at=_now(),
            created_by=created_by or username,
        )
        self.s.add(row)
        self.s.flush()

    def bulk_record(self, records: list[dict]) -> int:
        if not records:
            return 0
        now = _now()
        payload = [
            {
                "username":    r["username"],
                "dataset_id":  r["dataset_id"],
                "data_id":     r["data_id"],
                "action_type": r["action_type"],
                "created_at":  now,
                "created_by":  r.get("created_by") or r["username"],
            }
            for r in records
        ]
        self.s.bulk_insert_mappings(WorkVolume, payload)
        return len(payload)

    # ── 查询 ────────────────────────────────────────────────────────────────
    def query_aggregates(
        self,
        dataset_id: int | None,
        today_start: datetime,
        week_start: datetime,
        month_start: datetime,
    ) -> list[dict[str, Any]]:
        """一次 GROUP BY 返回所有人的今/周/月工作量。

        SQL 结构：WHERE created_at >= :month_start 走 idx_t_work_volume_user_time
        把扫描限制在 30 天内，再用 COUNT(*) FILTER 切分今/周/月与标注/裁决。
        """
        sql = text(
            """
            SELECT
                username,
                COUNT(*) FILTER (WHERE action_type='annotation'       AND created_at >= :today_start) AS today_annotation,
                COUNT(*) FILTER (WHERE action_type='conflict_resolve' AND created_at >= :today_start) AS today_resolve,
                COUNT(*) FILTER (WHERE action_type='annotation'       AND created_at >= :week_start)  AS week_annotation,
                COUNT(*) FILTER (WHERE action_type='conflict_resolve' AND created_at >= :week_start)  AS week_resolve,
                COUNT(*) FILTER (WHERE action_type='annotation'       AND created_at >= :month_start) AS month_annotation,
                COUNT(*) FILTER (WHERE action_type='conflict_resolve' AND created_at >= :month_start) AS month_resolve
            FROM t_work_volume
            WHERE created_at >= :month_start
              AND (CAST(:dataset_id AS BIGINT) IS NULL OR dataset_id = CAST(:dataset_id AS BIGINT))
            GROUP BY username
            ORDER BY (
                COUNT(*) FILTER (WHERE created_at >= :today_start)
            ) DESC, username ASC
            """
        )
        rows = self.s.execute(
            sql,
            {
                "today_start": today_start,
                "week_start":  week_start,
                "month_start": month_start,
                "dataset_id":  dataset_id,
            },
        ).mappings().all()

        return [
            {
                "username":         r["username"],
                "today_annotation": int(r["today_annotation"] or 0),
                "today_resolve":    int(r["today_resolve"]    or 0),
                "week_annotation":  int(r["week_annotation"]  or 0),
                "week_resolve":     int(r["week_resolve"]     or 0),
                "month_annotation": int(r["month_annotation"] or 0),
                "month_resolve":    int(r["month_resolve"]    or 0),
            }
            for r in rows
        ]

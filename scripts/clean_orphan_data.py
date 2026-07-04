"""孤儿数据清理：删除关联表中 data_id 指向不存在 DataItem 的行，以及指向已删数据集的 DataItem。

背景：历史上「删除数据」只删了 t_data_item + t_data_state，漏删标注/预标注/评论等关联表，
积累了大量孤儿数据，拖慢查询。本脚本一次性清干净。

清理两类孤儿：
  1. data_id 孤儿：8 张关联表中 data_id 指向的 DataItem 已不存在的行
     （t_annotation_result / t_annotation / t_pre_annotation / t_conflict /
      t_data_comment / t_work_volume / t_embedding / t_data_state）
  2. dataset 孤儿：t_data_item 中 dataset_id 指向已删数据集的行，连同其全部关联数据

安全：默认 dry-run 只统计不删除，加 --apply 才真正删除。

用法（项目根目录）：
  uv run python scripts/clean_orphan_data.py            # dry-run，只打印各表孤儿条数
  uv run python scripts/clean_orphan_data.py --apply    # 真正删除
"""
import argparse
import sys

sys.path.insert(0, "src")

from sqlalchemy import select  # noqa: E402

from datapulse.config.settings import get_settings  # noqa: E402
from datapulse.model.entities import (  # noqa: E402
    Annotation, AnnotationResult, Conflict, DataComment, DataItem, DataState,
    Dataset, Embedding, PreAnnotation, WorkVolume,
)
from datapulse.repository import get_db, init_db  # noqa: E402

# data_id 关联表清单（与 DataRepository._cascade_delete_by_ids 保持一致）
RELATED = [
    AnnotationResult, Annotation, PreAnnotation, Conflict,
    DataComment, WorkVolume, Embedding, DataState,
]


def _count_data_id_orphans(sess) -> dict[str, int]:
    """各关联表中 data_id 指向不存在 DataItem 的行数。"""
    valid_ids = select(DataItem.id)
    return {
        e.__tablename__: sess.query(e).filter(e.data_id.notin_(valid_ids)).count()
        for e in RELATED
    }


def _dataset_orphan_item_ids(sess) -> list[int]:
    """dataset_id 指向已删数据集的 DataItem id 列表。"""
    valid_ds = select(Dataset.id)
    return [
        r[0]
        for r in sess.query(DataItem.id).filter(DataItem.dataset_id.notin_(valid_ds)).all()
    ]


def clean(apply: bool) -> None:
    settings = get_settings()
    init_db(settings.db_url, connect_args=settings.db_connect_args,
            db_url_safe=settings.db_url_safe)
    db = get_db()

    mode = "APPLY（真正删除）" if apply else "DRY-RUN（只统计，不删除）"
    print(f"=== 孤儿数据清理 · {mode} ===\n")

    with db._session() as sess:
        # ① dataset 孤儿：DataItem 指向已删数据集 —— 这些 item 及其关联数据都要清
        ds_orphan_ids = _dataset_orphan_item_ids(sess)
        print(f"── dataset 孤儿（DataItem 指向已删数据集）──")
        print(f"  t_data_item  {len(ds_orphan_ids)} 行（连同其关联数据一并清理）\n")

        if apply and ds_orphan_ids:
            # 复用级联删除：先删这些 item 的关联数据，再删 item 本身
            from datapulse.repository.data_repository import DataRepository
            DataRepository(sess)._cascade_delete_by_ids(ds_orphan_ids)

        # ② data_id 孤儿：关联表指向不存在 DataItem 的行（含①级联清理后新暴露的）
        counts = _count_data_id_orphans(sess)
        total = sum(counts.values())
        print(f"── data_id 孤儿（关联表指向不存在的 DataItem）──")
        for tbl, n in counts.items():
            print(f"  {tbl:24} {n}")
        print(f"  {'合计':24} {total}\n")

        if apply:
            valid_ids = select(DataItem.id)
            deleted = 0
            for e in RELATED:
                deleted += sess.query(e).filter(
                    e.data_id.notin_(valid_ids)
                ).delete(synchronize_session=False)
            sess.commit()
            print(f"✅ 已删除 {len(ds_orphan_ids)} 个 dataset 孤儿 item + {deleted} 行 data_id 孤儿关联数据。")
        else:
            print("（dry-run 未删除任何数据。确认无误后加 --apply 执行）")


def main():
    ap = argparse.ArgumentParser(description="清理孤儿数据（关联表 data_id 悬空 + DataItem dataset 悬空）")
    ap.add_argument("--apply", action="store_true", help="真正删除；不加则只 dry-run 统计")
    args = ap.parse_args()
    clean(args.apply)


if __name__ == "__main__":
    main()

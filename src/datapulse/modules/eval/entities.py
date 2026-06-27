"""AI 评测子系统的 ORM 实体（独立 Base，与标注主体的实体解耦）。

eval 三张表无外键到标注表，自成体系。挂独立 EvalBase（而非主体 Base），
使得：主体 Base.metadata.create_all() 不再建 eval 表，eval 表结构变更也不
碰主体 entities.py。共享同一物理库与 engine，只是 ORM 元数据分离。
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import declarative_base

EvalBase = declarative_base()

_TS = TIMESTAMP(precision=6)


class EvalTask(EvalBase):
    """t_eval_task — AI 对话评测任务（每个评测任务一行）

    独立于标注数据集（dataset），自成体系：上传 Excel → 评测 → 出报告。
    task_id 是对外业务主键（uuid 截断），id 为符合规范的自增主键。
    result_json 存聚合结果（summary/metrics/insights/advice），逐条 rows 在 t_eval_task_row。
    """

    __tablename__ = "t_eval_task"

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id        = Column(String(64), nullable=False, unique=True, index=True)
    filename       = Column(Text, nullable=False, default="")
    file_path      = Column(Text, nullable=False, default="")
    bu             = Column(String(64), nullable=False, default="")
    status         = Column(String(32), nullable=False, default="pending")  # pending|running|done|failed
    stage          = Column(String(64), nullable=False, default="")          # loading|loaded|judging|advising|done
    mode           = Column(String(32), nullable=False, default="")          # calibration|production
    progress_done  = Column(Integer, nullable=False, default=0)
    progress_total = Column(Integer, nullable=False, default=0)
    error          = Column(Text)
    result_json    = Column(JSONB)
    finished_at    = Column(_TS)
    created_at     = Column(_TS, nullable=False)
    created_by     = Column(String(100), nullable=False, default="")
    updated_at     = Column(_TS, nullable=False)
    updated_by     = Column(String(100), nullable=False, default="")


class EvalTaskRow(EvalBase):
    """t_eval_task_row — 逐条评测结果（断点续跑的依据）

    每个评测任务的每行明细一条，(task_id, row_index) 联合唯一。
    只写不改（重跑用 UPSERT 覆盖），故只需 created_at / created_by。
    """

    __tablename__ = "t_eval_task_row"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id    = Column(String(64), nullable=False, index=True)
    row_index  = Column(BigInteger, nullable=False)
    row_json   = Column(JSONB, nullable=False)
    created_at = Column(_TS, nullable=False)
    created_by = Column(String(100), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("task_id", "row_index", name="uk_t_eval_task_row_task_idx"),
    )


class EvalPrompt(EvalBase):
    """t_eval_prompt — AI 评测提示词（支持页面实时编辑，改后不重启即生效）

    一条 prompt 由 (bu, name) 唯一标识。bu 用约定字符串区分作用域：
      _root    = prompts/ 根目录的共用模板（如 judge_user.md）
      _default = 各 BU 通用兜底（prompts/_default/）
      其余     = 具体 BU（securities / life / ...）
    库中无记录时加载层回退读 prompts/ 下的同名文件（出厂默认）。
    """

    __tablename__ = "t_eval_prompt"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    bu          = Column(String(64), nullable=False)    # _root | _default | 具体BU code
    name        = Column(String(128), nullable=False)   # 模板文件名，如 judge_system.md
    content     = Column(Text, nullable=False, default="")
    description = Column(String(255), nullable=False, default="")
    created_at  = Column(_TS, nullable=False)
    created_by  = Column(String(100), nullable=False, default="")
    updated_at  = Column(_TS, nullable=False)
    updated_by  = Column(String(100), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("bu", "name", name="uk_t_eval_prompt_bu_name"),
    )

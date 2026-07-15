"""AI 评测子系统的 ORM 实体（独立 Base，与标注主体的实体解耦）。

eval 三张表无外键到标注表，自成体系。挂独立 EvalBase（而非主体 Base），
使得：主体 Base.metadata.create_all() 不再建 eval 表，eval 表结构变更也不
碰主体 entities.py。共享同一物理库与 engine，只是 ORM 元数据分离。
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, Index, Integer, String, Text, UniqueConstraint
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
    # 多 POD 抢占式调度:哪个 worker 抢到、何时抢到、最近心跳。心跳超时视为该 POD
    # 已死,任务被回收重抢(断点续跑)。pending 任务靠 FOR UPDATE SKIP LOCKED 抢占。
    claimed_by     = Column(String(128))
    claimed_at     = Column(_TS)
    heartbeat_at   = Column(_TS)
    started_at     = Column(_TS)   # 真正开跑（pending→running）的时间，排队等待不计入
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
    # ── 平铺列（被明细过滤 / 洞察聚合当列查，拆出走原生索引）───────────────────────
    session       = Column(String(128))   # 会话ID
    turn          = Column(Integer)        # 会话内轮次
    question      = Column(Text)           # 客户提问原文（可能超长，不建 B-tree 索引）
    ask_time      = Column(String(32))     # 提问时间原文，洞察按日聚合
    dispatched_bu = Column(String(64))     # Excel 分发BU列原值
    j_intent      = Column(String(128))    # AI 判定业务分类
    j_dispatch    = Column(String(8))      # 分发判定 是/否
    j_resolved    = Column(String(8))      # 解决判定 是/否
    # ── JSON 列（嵌套结构 / AI 完整输出，整体读写不拆）─────────────────────────────
    judge_json    = Column(JSONB)          # LLM 完整判定输出（11 字段）
    context_json  = Column(JSONB)          # 多轮对话上下文 [{turn,user,ai}]
    gold_json     = Column(JSONB)          # 人工金标 dict
    # ── 兜底 / 审计 ───────────────────────────────────────────────────────────────
    row_json   = Column(JSONB, nullable=False)   # 完整快照，旧行读它兜底 + 过渡期双写
    created_at = Column(_TS, nullable=False)
    created_by = Column(String(100), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("task_id", "row_index", name="uk_t_eval_task_row_task_idx"),
        # 明细页高频过滤 j_dispatch / j_resolved（按 task 内），复合索引走原生 B-tree
        Index("idx_t_eval_row_task_dispatch", "task_id", "j_dispatch"),
        Index("idx_t_eval_row_task_resolved", "task_id", "j_resolved"),
        # 问题洞察跨任务 GROUP BY j_intent / 按 ask_time 日聚合
        Index("idx_t_eval_row_j_intent", "j_intent"),
        Index("idx_t_eval_row_ask_time", "ask_time"),
        # question 不建索引：可能超长（>2704 B-tree 上限），聚合走 HashAggregate
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


class EvalCategory(EvalBase):
    """t_eval_category — AI 评测业务分类（每个 BU 一套，支持页面增删改）

    一条分类由 (bu, name) 唯一标识。评测时按当前 BU 取全部分类喂给模型判定。
    库中无记录时加载层回退读 prompts/<bu>/categories.json（出厂默认）。
    """

    __tablename__ = "t_eval_category"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    bu          = Column(String(64), nullable=False)    # 所属 BU code（securities / life）
    name        = Column(String(128), nullable=False)   # 业务分类名
    definition  = Column(Text, nullable=False, default="")   # 分类定义（喂给模型判定）
    sort_order  = Column(Integer, nullable=False, default=0)
    created_at  = Column(_TS, nullable=False)
    created_by  = Column(String(100), nullable=False, default="")
    updated_at  = Column(_TS, nullable=False)
    updated_by  = Column(String(100), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("bu", "name", name="uk_t_eval_category_bu_name"),
    )


class EvalActivityQuestion(EvalBase):
    """t_eval_activity_question — 活动标问（前端写死按钮 → 写死回复，不经 AI）

    这类问题（如「帮我解锁消费权益」）回复是写死的，不经 AI 分发/生成，评测时
    应整条跳过：不喂模型、不计入分发准确率/解决率，仅作为后续轮的上下文保留。
    按 BU 一套，页面可增删改；客户问题与 question 精确相等即判定为活动标问。
    """

    __tablename__ = "t_eval_activity_question"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    bu            = Column(String(64), nullable=False)     # 所属 BU code
    question      = Column(Text, nullable=False)           # 活动标问全文（精确匹配）
    activity_name = Column(String(255))                    # 活动名称：多个 question 同名即同活动，报告按此聚合
    note          = Column(String(255), nullable=False, default="")  # 备注（可选，说明用途）
    created_at  = Column(_TS, nullable=False)
    created_by  = Column(String(100), nullable=False, default="")
    updated_at  = Column(_TS, nullable=False)
    updated_by  = Column(String(100), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("bu", "question", name="uk_t_eval_activity_bu_question"),
    )


class EvalReview(EvalBase):
    """t_eval_review — 人工复核覆盖（每条评测明细可被人工复核覆盖 AI 判定）

    AI 原始判定存在 t_eval_task_row（只读不改）；人工复核结论存这里，读取时叠加：
    有复核用复核值、无复核用 AI 值。指标基于「最终值」重算（人工优先）。
    (task_id, row_index) 唯一——同一条可反复复核（upsert 覆盖）。
    """

    __tablename__ = "t_eval_review"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id          = Column(String(64), nullable=False)
    row_index        = Column(BigInteger, nullable=False)
    # 复核后的「分发是否正确」/「是否解决」：'是' | '否' | ''（''=该维度不改，沿用AI）
    reviewed_dispatch = Column(String(8), nullable=False, default="")
    reviewed_resolved = Column(String(8), nullable=False, default="")
    reviewed_intent   = Column(String(128), nullable=False, default="")  # 复核改的业务分类（空=不改）
    comment           = Column(Text, nullable=False, default="")          # 复核评论
    reviewer          = Column(String(100), nullable=False, default="")
    created_at        = Column(_TS, nullable=False)
    created_by        = Column(String(100), nullable=False, default="")
    updated_at        = Column(_TS, nullable=False)
    updated_by        = Column(String(100), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("task_id", "row_index", name="uk_t_eval_review_task_row"),
    )


class EvalRule(EvalBase):
    """t_eval_rule — 规则短路（写死评测结果，命中即免 LLM）·规则集模型

    一个规则 = 名字 + 触发问题集合 + 期望答案集合 + 一份写死 judge。评测时若客户问题
    ∈ questions 且答案 ∈ answers（独立组合），直接用 judge_json（结构同 LLM 输出）产出
    结果、计入指标、落盘，不调 LLM——省大量调用。报告按 name 聚合。按 BU 一套，(bu, name) 唯一。

    旧列 question/expected_answer 保留作历史兼容，新逻辑只读 questions/answers 集合。
    """

    __tablename__ = "t_eval_rule"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    bu              = Column(String(64), nullable=False)
    name            = Column(String(255), nullable=False, default="")  # 规则名（同 BU 唯一，报告按此聚合）
    questions       = Column(JSONB, nullable=False, default=list)       # 触发问题集合（字符串数组）
    answers         = Column(JSONB, nullable=False, default=list)       # 期望答案集合（字符串数组）
    question        = Column(Text, nullable=False, default="")          # 旧列（保留兼容）
    expected_answer = Column(Text, nullable=False, default="")          # 旧列（保留兼容）
    judge_json      = Column(JSONB, nullable=False)          # 写死的 judge 输出（11 字段，结构同 LLM）
    note            = Column(String(255), nullable=False, default="")
    created_at      = Column(_TS, nullable=False)
    created_by      = Column(String(100), nullable=False, default="")
    updated_at      = Column(_TS, nullable=False)
    updated_by      = Column(String(100), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("bu", "name", name="uk_t_eval_rule_bu_name"),
    )

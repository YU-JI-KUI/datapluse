DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260627_arkpgdata_add_eval_tables.sql -- AI dialog eval tables'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 对话评测（ark-dialog-eval）功能模块的两张表。
-- 独立于标注数据集（dataset），自成体系：上传 Excel -> 评测 -> 出报告。
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. 评测任务表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_task ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_task (
    id             BIGSERIAL    NOT NULL,
    task_id        VARCHAR(64)  NOT NULL,
    filename       TEXT         NOT NULL DEFAULT '',
    file_path      TEXT         NOT NULL DEFAULT '',
    bu             VARCHAR(64)  NOT NULL DEFAULT '',
    status         VARCHAR(32)  NOT NULL DEFAULT 'pending',
    stage          VARCHAR(64)  NOT NULL DEFAULT '',
    mode           VARCHAR(32)  NOT NULL DEFAULT '',
    progress_done  INTEGER      NOT NULL DEFAULT 0,
    progress_total INTEGER      NOT NULL DEFAULT 0,
    error          TEXT,
    result_json    JSONB,
    finished_at    TIMESTAMP(6),
    created_at     TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by     VARCHAR(100) NOT NULL DEFAULT '',
    updated_at     TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by     VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_task PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_task                IS 'AI对话评测任务表（每个评测任务一行）';
COMMENT ON COLUMN t_eval_task.id             IS '主键ID';
COMMENT ON COLUMN t_eval_task.task_id        IS '业务任务ID（uuid截断，对外标识）';
COMMENT ON COLUMN t_eval_task.filename       IS '上传文件名';
COMMENT ON COLUMN t_eval_task.file_path      IS '上传文件存储路径';
COMMENT ON COLUMN t_eval_task.bu             IS '业务单元：securities=证券 / life=寿险';
COMMENT ON COLUMN t_eval_task.status         IS '任务状态：pending=待执行 / running=执行中 / done=完成 / failed=失败';
COMMENT ON COLUMN t_eval_task.stage          IS '执行阶段：loading=加载 / loaded=已加载 / judging=评测中 / advising=出建议 / done=完成';
COMMENT ON COLUMN t_eval_task.mode           IS '评测模式：calibration=校准(有人工金标) / production=生产(无标注)';
COMMENT ON COLUMN t_eval_task.progress_done  IS '已完成样本数';
COMMENT ON COLUMN t_eval_task.progress_total IS '样本总数';
COMMENT ON COLUMN t_eval_task.error          IS '失败原因（status=failed 时有值）';
COMMENT ON COLUMN t_eval_task.result_json    IS '聚合结果（summary/metrics/insights/advice，逐条 rows 在 t_eval_task_row）';
COMMENT ON COLUMN t_eval_task.finished_at    IS '完成时间';
COMMENT ON COLUMN t_eval_task.created_at     IS '创建时间';
COMMENT ON COLUMN t_eval_task.created_by     IS '创建人';
COMMENT ON COLUMN t_eval_task.updated_at     IS '更新时间';
COMMENT ON COLUMN t_eval_task.updated_by     IS '更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_task_task_id ON t_eval_task(task_id);
CREATE INDEX IF NOT EXISTS idx_t_eval_task_created ON t_eval_task(created_at DESC);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_task'; END $$;

-- ---------------------------------------------------------------------------
-- 2. 逐条评测结果表（断点续跑依据）
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_task_row ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_task_row (
    id         BIGSERIAL    NOT NULL,
    task_id    VARCHAR(64)  NOT NULL,
    row_index  BIGINT       NOT NULL,
    row_json   JSONB        NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_task_row PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_task_row            IS 'AI对话评测逐条结果表（每行明细一条，断点续跑依据）';
COMMENT ON COLUMN t_eval_task_row.id         IS '主键ID';
COMMENT ON COLUMN t_eval_task_row.task_id    IS '所属评测任务ID（逻辑外键 -> t_eval_task.task_id）';
COMMENT ON COLUMN t_eval_task_row.row_index  IS '行序号（在该任务内唯一）';
COMMENT ON COLUMN t_eval_task_row.row_json   IS '单行完整评测结果（含 judge 输出、金标、分发场景等）';
COMMENT ON COLUMN t_eval_task_row.created_at IS '落盘时间';
COMMENT ON COLUMN t_eval_task_row.created_by IS '操作人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_task_row_task_idx ON t_eval_task_row(task_id, row_index);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_task_row'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260627_arkpgdata_add_eval_tables.sql complete'; END $$;

DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260701_arkpgdata_add_eval_review.sql -- eval manual review override'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 评测人工复核覆盖表：AI 原始判定存 t_eval_task_row（只读不改），人工复核结论
-- 存这里，读取时叠加（有复核用复核值、无复核用 AI 值）。BU分发准确率、问题解决率、
-- 需复核数基于「最终值」重算。(task_id, row_index) 唯一，同一条可反复复核（覆盖）。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_review ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_review (
    id                BIGSERIAL    NOT NULL,
    task_id           VARCHAR(64)  NOT NULL,
    row_index         BIGINT       NOT NULL,
    reviewed_dispatch VARCHAR(8)   NOT NULL DEFAULT '',
    reviewed_resolved VARCHAR(8)   NOT NULL DEFAULT '',
    reviewed_intent   VARCHAR(128) NOT NULL DEFAULT '',
    comment           TEXT         NOT NULL DEFAULT '',
    reviewer          VARCHAR(100) NOT NULL DEFAULT '',
    created_at        TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by        VARCHAR(100) NOT NULL DEFAULT '',
    updated_at        TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by        VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_review PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_review                   IS 'AI评测人工复核覆盖表（人工复核结论覆盖AI判定，指标按最终值重算）';
COMMENT ON COLUMN t_eval_review.id                IS '主键ID';
COMMENT ON COLUMN t_eval_review.task_id           IS '所属评测任务ID（逻辑外键 → t_eval_task.task_id）';
COMMENT ON COLUMN t_eval_review.row_index         IS '明细行序号（逻辑外键 → t_eval_task_row.row_index）';
COMMENT ON COLUMN t_eval_review.reviewed_dispatch IS '复核后分发是否正确：是 / 否 / 空（空=该维度不改，沿用AI判定）';
COMMENT ON COLUMN t_eval_review.reviewed_resolved IS '复核后是否解决：是 / 否 / 空（空=不改；仅对实际分到本BU的样本生效）';
COMMENT ON COLUMN t_eval_review.reviewed_intent   IS '复核改的业务分类标签（空=不改）';
COMMENT ON COLUMN t_eval_review.comment           IS '复核评论';
COMMENT ON COLUMN t_eval_review.reviewer          IS '复核人';
COMMENT ON COLUMN t_eval_review.created_at        IS '创建时间';
COMMENT ON COLUMN t_eval_review.created_by        IS '创建人';
COMMENT ON COLUMN t_eval_review.updated_at        IS '更新时间';
COMMENT ON COLUMN t_eval_review.updated_by        IS '更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_review_task_row ON t_eval_review(task_id, row_index);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_review'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260701_arkpgdata_add_eval_review.sql complete'; END $$;

DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260630_arkpgdata_add_eval_activity.sql -- eval activity questions'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 评测活动标问表：前端写死按钮（如「帮我解锁消费权益」）触发的写死回复，
-- 不经 AI 分发/生成。评测时这类问题应整条跳过——不喂模型、不计入分发准确率/
-- 解决率，仅作后续轮上下文保留。按 BU 一套，页面可增删改；客户问题与 question
-- 精确相等即判定为活动标问。(bu, question) 唯一。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_activity_question ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_activity_question (
    id          BIGSERIAL    NOT NULL,
    bu          VARCHAR(64)  NOT NULL,
    question    TEXT         NOT NULL,
    note        VARCHAR(255) NOT NULL DEFAULT '',
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(100) NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_activity_question PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_activity_question            IS 'AI评测活动标问表（写死按钮触发的写死回复，评测时整条跳过，不计入指标）';
COMMENT ON COLUMN t_eval_activity_question.id         IS '主键ID';
COMMENT ON COLUMN t_eval_activity_question.bu         IS '所属业务单元：securities=证券 / life=寿险';
COMMENT ON COLUMN t_eval_activity_question.question   IS '活动标问全文（与客户问题精确相等即命中，整条跳过评测）';
COMMENT ON COLUMN t_eval_activity_question.note       IS '备注（说明该活动标问的用途，可选）';
COMMENT ON COLUMN t_eval_activity_question.created_at IS '创建时间';
COMMENT ON COLUMN t_eval_activity_question.created_by IS '创建人';
COMMENT ON COLUMN t_eval_activity_question.updated_at IS '更新时间';
COMMENT ON COLUMN t_eval_activity_question.updated_by IS '更新人';

CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_activity_bu_question ON t_eval_activity_question(bu, question);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_activity_question'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260630_arkpgdata_add_eval_activity.sql complete'; END $$;

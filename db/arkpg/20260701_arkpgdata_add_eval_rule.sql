DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260701_arkpgdata_add_eval_rule.sql -- eval rule-based bypass'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 评测规则短路表：某些问题（如「转人工」）结果确定——分发/业务分类/答案/是否解决
-- 均已知。评测时若客户问题精确等于 question 且答案等于 expected_answer，直接用
-- judge_json（结构同 LLM 输出）产出结果、计入指标、落盘，不调 LLM，省大量调用。
-- 按 BU 一套，(bu, question) 唯一。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_rule ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_rule (
    id              BIGSERIAL    NOT NULL,
    bu              VARCHAR(64)  NOT NULL,
    question        TEXT         NOT NULL,
    expected_answer TEXT         NOT NULL DEFAULT '',
    judge_json      JSONB        NOT NULL,
    note            VARCHAR(255) NOT NULL DEFAULT '',
    created_at      TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by      VARCHAR(100) NOT NULL DEFAULT '',
    updated_at      TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by      VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_rule PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_rule                 IS 'AI评测规则短路表（命中写死结果、免LLM调用，计入指标）';
COMMENT ON COLUMN t_eval_rule.id              IS '主键ID';
COMMENT ON COLUMN t_eval_rule.bu              IS '所属业务单元：securities=证券 / life=寿险';
COMMENT ON COLUMN t_eval_rule.question        IS '触发问题（与客户问题精确相等即命中）';
COMMENT ON COLUMN t_eval_rule.expected_answer IS '期望答案（须与样本答案一致才命中；防答案已变仍套用写死结论）';
COMMENT ON COLUMN t_eval_rule.judge_json      IS '写死的judge输出（11字段，结构同LLM output，命中即原样产出）';
COMMENT ON COLUMN t_eval_rule.note            IS '备注';
COMMENT ON COLUMN t_eval_rule.created_at      IS '创建时间';
COMMENT ON COLUMN t_eval_rule.created_by      IS '创建人';
COMMENT ON COLUMN t_eval_rule.updated_at      IS '更新时间';
COMMENT ON COLUMN t_eval_rule.updated_by      IS '更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_rule_bu_question ON t_eval_rule(bu, question);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_rule'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260701_arkpgdata_add_eval_rule.sql complete'; END $$;

DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260710_arkpgdata_eval_rule_ruleset.sql -- rule bypass: single Q&A -> rule set'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- 规则短路升级为「规则集」：一个规则 = 名字 + 触发问题集合 + 期望答案集合 + judge。
-- 匹配语义：客户问题 ∈ 触发问题集合 且 答案 ∈ 期望答案集合（独立组合）→ 命中。
-- 报告按规则名聚合。旧的单问单答列（question/expected_answer）保留作迁移源与兼容。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] add columns name/questions/answers to t_eval_rule ...'; END $$;
ALTER TABLE t_eval_rule ADD COLUMN IF NOT EXISTS name      VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE t_eval_rule ADD COLUMN IF NOT EXISTS questions JSONB        NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE t_eval_rule ADD COLUMN IF NOT EXISTS answers   JSONB        NOT NULL DEFAULT '[]'::jsonb;
COMMENT ON COLUMN t_eval_rule.name      IS '规则名（同BU内唯一，报告按此聚合，如「转人工」）';
COMMENT ON COLUMN t_eval_rule.questions IS '触发问题集合（JSON字符串数组）；客户问题精确等于其中任一即满足问题条件';
COMMENT ON COLUMN t_eval_rule.answers   IS '期望答案集合（JSON字符串数组）；样本答案精确等于其中任一即满足答案条件';
DO $$ BEGIN RAISE NOTICE '[OK ]  columns added'; END $$;

DO $$ BEGIN RAISE NOTICE '[DATA] backfill old single-Q&A rules into rule-set shape ...'; END $$;
-- 每条旧规则迁成规则集：name=question，questions=[question]，answers=[expected_answer]
UPDATE t_eval_rule
   SET name      = question,
       questions = to_jsonb(ARRAY[question]),
       answers   = to_jsonb(ARRAY[expected_answer])
 WHERE (name IS NULL OR name = '')
   AND question IS NOT NULL AND question <> '';
DO $$ BEGIN RAISE NOTICE '[OK ]  backfill done'; END $$;

DO $$ BEGIN RAISE NOTICE '[DDL] unique index on (bu, name) ...'; END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_rule_bu_name ON t_eval_rule(bu, name);
DO $$ BEGIN RAISE NOTICE '[OK ]  uk_t_eval_rule_bu_name'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260710_arkpgdata_eval_rule_ruleset.sql complete'; END $$;

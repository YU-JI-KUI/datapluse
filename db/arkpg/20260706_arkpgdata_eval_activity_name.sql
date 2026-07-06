DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260706_arkpgdata_eval_activity_name.sql -- activity name layer'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- 活动标问抽出"活动名称"层：多个 question 归属同一 activity_name，报告按活动聚合。
-- (bu, question) 仍唯一，一个问题只属一个活动。判断逻辑不变（等值命中）。
-- 幂等：ADD COLUMN IF NOT EXISTS。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] add activity_name column ...'; END $$;
ALTER TABLE t_eval_activity_question ADD COLUMN IF NOT EXISTS activity_name VARCHAR(255);
COMMENT ON COLUMN t_eval_activity_question.activity_name IS '活动名称：多个 question 同名即同活动，评测报告按此聚合';
DO $$ BEGIN RAISE NOTICE '[OK ]  activity_name added'; END $$;

-- 回填：旧标问 activity_name = question 本身（每个老问题自成一活动，行为与改造前一致）
DO $$ BEGIN RAISE NOTICE '[DATA] backfill activity_name = question ...'; END $$;
UPDATE t_eval_activity_question
    SET activity_name = question
    WHERE activity_name IS NULL OR activity_name = '';
DO $$ BEGIN RAISE NOTICE '[OK ]  backfill done'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260706_arkpgdata_eval_activity_name.sql complete'; END $$;

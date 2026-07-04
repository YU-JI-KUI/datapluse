DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260704_arkpgdata_add_eval_started_at.sql -- eval task started_at'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 评测任务加「真正开跑时间」started_at
--   历史评测原先用 created_at 当开始时间，但任务可能排队等待很久才被抢占开跑，
--   等待时间不该算进耗时。started_at 在任务 pending→running 那一刻写入（claim 时），
--   重跑时清空、下次开跑再写新值。这样开始→完成的时间差即单次评测真实耗时。
-- 幂等：列 IF NOT EXISTS。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] add started_at column to t_eval_task ...'; END $$;
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS started_at TIMESTAMP(6);
COMMENT ON COLUMN t_eval_task.started_at IS '任务真正开跑（pending→running）时间，排队等待不计入，用于统计单次评测耗时';
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_task.started_at'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260704_arkpgdata_add_eval_started_at.sql complete'; END $$;

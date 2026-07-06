DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260705_arkpgdata_eval_row_expr_index.sql -- eval row JSONB expr index'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- 问题洞察页按 row_json->>'question' / row_json->>'j_intent' 做跨任务 GROUP BY 聚合。
-- 加两个表达式 B-tree 索引加速分组统计。幂等：CREATE INDEX IF NOT EXISTS。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] create expr index on t_eval_task_row(row_json->>question) ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_question
    ON t_eval_task_row ((row_json->>'question'));
DO $$ BEGIN RAISE NOTICE '[OK ]  idx_t_eval_row_question'; END $$;

DO $$ BEGIN RAISE NOTICE '[DDL] create expr index on t_eval_task_row(row_json->>j_intent) ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_j_intent
    ON t_eval_task_row ((row_json->>'j_intent'));
DO $$ BEGIN RAISE NOTICE '[OK ]  idx_t_eval_row_j_intent'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260705_arkpgdata_eval_row_expr_index.sql complete'; END $$;

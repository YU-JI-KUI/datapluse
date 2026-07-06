DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260705_arkpgdata_eval_row_expr_index.sql -- eval row JSONB expr index'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- 问题洞察页按 row_json->>'j_intent' 做跨任务 GROUP BY 聚合，加表达式索引加速。
-- 注意：不对 row_json->>'question' 建 B-tree —— 真实客户问题可能超长（>2704 字节
-- 的 B-tree 单行上限），且高频问按原文分组走 HashAggregate 用不到该索引，故不建。
-- 幂等：CREATE INDEX IF NOT EXISTS。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] create expr index on t_eval_task_row(row_json->>j_intent) ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_j_intent
    ON t_eval_task_row ((row_json->>'j_intent'));
DO $$ BEGIN RAISE NOTICE '[OK ]  idx_t_eval_row_j_intent'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260705_arkpgdata_eval_row_expr_index.sql complete'; END $$;

DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260706_arkpgdata_eval_row_flatten.sql -- flatten row_json to columns'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- t_eval_task_row 拆列：把被明细过滤/洞察聚合当列查的字段从 row_json 拆成平铺列，
-- judge/context/gold 各存独立 JSON 列，row_json 保留作旧行兜底 + 过渡期双写。
-- 幂等：ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] add flattened columns to t_eval_task_row ...'; END $$;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS session       VARCHAR(128);
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS turn          INTEGER;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS question      TEXT;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS ask_time      VARCHAR(32);
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS dispatched_bu VARCHAR(64);
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS j_intent      VARCHAR(128);
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS j_dispatch    VARCHAR(8);
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS j_resolved    VARCHAR(8);
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS judge_json    JSONB;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS context_json  JSONB;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS gold_json     JSONB;
DO $$ BEGIN RAISE NOTICE '[OK ]  columns added'; END $$;

COMMENT ON COLUMN t_eval_task_row.session       IS '会话ID（原 Excel 应用会话ID列）';
COMMENT ON COLUMN t_eval_task_row.turn          IS '会话内客户咨询轮次';
COMMENT ON COLUMN t_eval_task_row.question      IS '客户提问原文';
COMMENT ON COLUMN t_eval_task_row.ask_time      IS '客户提问时间原文，问题洞察按日聚合';
COMMENT ON COLUMN t_eval_task_row.dispatched_bu IS 'Excel 分发BU列原值';
COMMENT ON COLUMN t_eval_task_row.j_intent      IS 'AI 判定业务分类';
COMMENT ON COLUMN t_eval_task_row.j_dispatch    IS '分发判定结果：是 / 否';
COMMENT ON COLUMN t_eval_task_row.j_resolved    IS '答案解决判定结果：是 / 否';
COMMENT ON COLUMN t_eval_task_row.judge_json    IS 'LLM 完整判定输出（11 字段）';
COMMENT ON COLUMN t_eval_task_row.context_json  IS '多轮对话上下文 [{turn,user,ai}]';
COMMENT ON COLUMN t_eval_task_row.gold_json     IS '人工金标 dict';

-- 回填旧行的聚合窄字段（question/j_intent/ask_time）：问题洞察跨任务聚合直接查列走索引。
-- 只回填这三个（洞察用到的），其余平铺列旧行留空、读取时 fallback row_json。
-- 分批 UPDATE（每批 5000）避免大事务锁表。
DO $$
DECLARE
    n_updated INTEGER;
BEGIN
    LOOP
        UPDATE t_eval_task_row SET
            question = row_json->>'question',
            j_intent = row_json->>'j_intent',
            ask_time = COALESCE(row_json->>'ask_time', '')
        WHERE id IN (
            SELECT id FROM t_eval_task_row
            WHERE question IS NULL AND row_json IS NOT NULL
            LIMIT 5000
        );
        GET DIAGNOSTICS n_updated = ROW_COUNT;
        RAISE NOTICE '[DATA] backfill batch: % rows', n_updated;
        EXIT WHEN n_updated = 0;
    END LOOP;
END $$;
DO $$ BEGIN RAISE NOTICE '[OK ]  backfill done'; END $$;

-- 旧的 j_intent 表达式索引（基于 row_json->>'j_intent'）改为列索引，先删再建。
DO $$ BEGIN RAISE NOTICE '[DDL] rebuild indexes ...'; END $$;
DROP INDEX IF EXISTS idx_t_eval_row_j_intent;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_j_intent      ON t_eval_task_row (j_intent);
CREATE INDEX IF NOT EXISTS idx_t_eval_row_ask_time      ON t_eval_task_row (ask_time);
CREATE INDEX IF NOT EXISTS idx_t_eval_row_task_dispatch ON t_eval_task_row (task_id, j_dispatch);
CREATE INDEX IF NOT EXISTS idx_t_eval_row_task_resolved ON t_eval_task_row (task_id, j_resolved);
DO $$ BEGIN RAISE NOTICE '[OK ]  indexes rebuilt'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260706_arkpgdata_eval_row_flatten.sql complete'; END $$;

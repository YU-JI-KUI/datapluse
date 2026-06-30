DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260630_arkpgdata_eval_worker_claim.sql -- eval multi-pod claim + jsonb idx'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 评测多 POD 抢占式调度 + 逐条结果 JSONB 过滤索引
--   1. t_eval_task 加 claim 列：多副本部署下用 FOR UPDATE SKIP LOCKED 抢任务，
--      心跳续约 + 超时回收，保证任务不重复跑、POD 崩了能被接管续跑。
--   2. t_eval_task_row 加表达式索引：5万条任务的明细页按业务分类过滤 / 需复核筛选
--      原先全表扫 + 解 JSONB，加索引避免越翻越慢。
-- 全部幂等：列/索引均 IF NOT EXISTS。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] add claim columns to t_eval_task ...'; END $$;
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS claimed_by   VARCHAR(128);
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS claimed_at   TIMESTAMP(6);
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP(6);
COMMENT ON COLUMN t_eval_task.claimed_by   IS '抢占该任务的worker标识（主机:进程:随机后缀），多POD调度用';
COMMENT ON COLUMN t_eval_task.claimed_at   IS '抢占时间';
COMMENT ON COLUMN t_eval_task.heartbeat_at IS '最近心跳时间（运行中定期续约，超时视为持有POD已死，任务被回收重抢）';
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_task claim columns'; END $$;

-- 抢占扫描：WHERE status='pending' ORDER BY created_at，给 status 建索引加速抢占探测。
DO $$ BEGIN RAISE NOTICE '[DDL] index t_eval_task(status, created_at) ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_task_status_created ON t_eval_task(status, created_at);
DO $$ BEGIN RAISE NOTICE '[OK ]  idx_t_eval_task_status_created'; END $$;

-- 明细页按业务分类过滤：row_json->>'j_intent' 精确匹配（每任务一索引会太多，按
-- (task_id, j_intent) 复合表达式索引，命中后定位快）。
DO $$ BEGIN RAISE NOTICE '[DDL] expression index on row_json j_intent ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_intent
    ON t_eval_task_row (task_id, (row_json->>'j_intent'));
DO $$ BEGIN RAISE NOTICE '[OK ]  idx_t_eval_row_intent'; END $$;

-- 「需复核」筛选：row_json->'judge'->>'needs_human_review'。部分索引只收 true 行，体积小。
DO $$ BEGIN RAISE NOTICE '[DDL] partial index on needs_human_review ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_review
    ON t_eval_task_row (task_id)
    WHERE (row_json->'judge'->>'needs_human_review') = 'true';
DO $$ BEGIN RAISE NOTICE '[OK ]  idx_t_eval_row_review'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260630_arkpgdata_eval_worker_claim.sql complete'; END $$;

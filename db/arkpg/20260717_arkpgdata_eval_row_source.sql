DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260717_arkpgdata_eval_row_source.sql -- eval row source flat column'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;

-- ---------------------------------------------------------------------------
-- Why: 问题洞察-每日频率要按处理来源分维展示（活动标问 / 短路规则 / AI评测）。
--      来源此前只在 judge_json->>'_source'（JSONB，无索引），大库按来源分桶要扫
--      JSONB。拆成 source 平铺列 + (bu,ask_date,source) 复合索引，按日按来源走索引。
--      取值：activity=活动标问(跳过评测) / rule=短路规则命中 / llm=AI评测。
-- ---------------------------------------------------------------------------

DO $$ BEGIN RAISE NOTICE '[DDL] add column source on t_eval_task_row ...'; END $$;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS source VARCHAR(16);
COMMENT ON COLUMN t_eval_task_row.source IS '处理来源：activity=活动标问 / rule=短路规则 / llm=AI评测。每日频率分维、评测/洞察聚合排除 activity';
DO $$ BEGIN RAISE NOTICE '[OK ]  column added'; END $$;

-- Backfill old rows: judge_json._source='rule' -> rule, otherwise llm.
-- 老数据无活动标问行（活动标问此前不落库），故只有 rule / llm 两类。分批防锁表。
DO $$ BEGIN RAISE NOTICE '[DATA] backfill source from judge_json ...'; END $$;
DO $$
DECLARE
    n_updated INTEGER;
BEGIN
    LOOP
        UPDATE t_eval_task_row SET
            source = CASE WHEN judge_json->>'_source' = 'rule' THEN 'rule' ELSE 'llm' END
        WHERE id IN (
            SELECT id FROM t_eval_task_row WHERE source IS NULL LIMIT 5000
        );
        GET DIAGNOSTICS n_updated = ROW_COUNT;
        EXIT WHEN n_updated = 0;
        RAISE NOTICE '[DATA] source backfill batch: % rows', n_updated;
    END LOOP;
END $$;
DO $$ BEGIN RAISE NOTICE '[OK ]  backfill done'; END $$;

DO $$ BEGIN RAISE NOTICE '[DDL] create composite index (bu, ask_date, source) ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_bu_askdate_source ON t_eval_task_row (bu, ask_date, source);
DO $$ BEGIN RAISE NOTICE '[OK ]  index'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260717_arkpgdata_eval_row_source.sql complete'; END $$;

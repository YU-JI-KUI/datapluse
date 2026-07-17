DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260717_arkpgdata_eval_row_ask_date.sql -- eval row ask_date/bu/dispatched_to_bu + composite indexes'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;

-- ---------------------------------------------------------------------------
-- Why: question-insight & timeline queries filter/group by ask date and bu.
--      ask_time is raw VARCHAR text queried via substr(ask_time,1,10), so the
--      plain index on ask_time can never serve a date range; and bu lives only
--      on t_eval_task, forcing a JOIN on every aggregation. Denormalize a real
--      DATE column + bu + dispatched_to_bu onto the row table and add composite
--      indexes so BU + date-range + intent hits one index with no JOIN.
-- ---------------------------------------------------------------------------

DO $$ BEGIN RAISE NOTICE '[DDL] add columns ask_date / bu / dispatched_to_bu on t_eval_task_row ...'; END $$;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS ask_date         DATE;
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS bu               VARCHAR(64);
ALTER TABLE t_eval_task_row ADD COLUMN IF NOT EXISTS dispatched_to_bu BOOLEAN;
COMMENT ON COLUMN t_eval_task_row.ask_date         IS '客户提问日期（由 ask_time 前10位解析），问题洞察/时序按日聚合';
COMMENT ON COLUMN t_eval_task_row.bu               IS '所属业务单元（冗余自 t_eval_task.bu，免聚合 JOIN）';
COMMENT ON COLUMN t_eval_task_row.dispatched_to_bu IS '是否实际分发给本BU（解决率漏斗分母口径，冗余自 row_json）';
DO $$ BEGIN RAISE NOTICE '[OK ]  columns added'; END $$;

-- Backfill old rows in batches (5000/batch) to avoid a long table lock.
-- ask_date: ISO ask_time -> first 10 chars ::date; guard against blank/garbage.
DO $$ BEGIN RAISE NOTICE '[DATA] backfill ask_date from ask_time ...'; END $$;
DO $$
DECLARE
    n_updated INTEGER;
BEGIN
    LOOP
        UPDATE t_eval_task_row SET
            ask_date = substr(ask_time, 1, 10)::date
        WHERE id IN (
            SELECT id FROM t_eval_task_row
            WHERE ask_date IS NULL
              AND ask_time IS NOT NULL
              AND ask_time <> ''
              AND substr(ask_time, 1, 10) ~ '^\d{4}-\d{2}-\d{2}$'
            LIMIT 5000
        );
        GET DIAGNOSTICS n_updated = ROW_COUNT;
        EXIT WHEN n_updated = 0;
        RAISE NOTICE '[DATA] ask_date backfill batch: % rows', n_updated;
    END LOOP;
END $$;

-- bu: denormalize from t_eval_task via task_id, in batches.
DO $$ BEGIN RAISE NOTICE '[DATA] backfill bu from t_eval_task ...'; END $$;
DO $$
DECLARE
    n_updated INTEGER;
BEGIN
    LOOP
        UPDATE t_eval_task_row r SET
            bu = t.bu
        FROM t_eval_task t
        WHERE r.task_id = t.task_id
          AND r.bu IS NULL
          AND r.id IN (
            SELECT id FROM t_eval_task_row WHERE bu IS NULL LIMIT 5000
          );
        GET DIAGNOSTICS n_updated = ROW_COUNT;
        EXIT WHEN n_updated = 0;
        RAISE NOTICE '[DATA] bu backfill batch: % rows', n_updated;
    END LOOP;
END $$;

-- dispatched_to_bu: from row_json boolean, in batches. Coalesce to false so
-- backfilled rows stop being re-scanned every deploy.
DO $$ BEGIN RAISE NOTICE '[DATA] backfill dispatched_to_bu from row_json ...'; END $$;
DO $$
DECLARE
    n_updated INTEGER;
BEGIN
    LOOP
        UPDATE t_eval_task_row SET
            dispatched_to_bu = COALESCE((row_json->>'dispatched_to_bu')::boolean, false)
        WHERE id IN (
            SELECT id FROM t_eval_task_row
            WHERE dispatched_to_bu IS NULL AND row_json IS NOT NULL
            LIMIT 5000
        );
        GET DIAGNOSTICS n_updated = ROW_COUNT;
        EXIT WHEN n_updated = 0;
        RAISE NOTICE '[DATA] dispatched_to_bu backfill batch: % rows', n_updated;
    END LOOP;
END $$;
DO $$ BEGIN RAISE NOTICE '[OK ]  backfill done'; END $$;

-- Composite indexes: BU + date-range (+ intent) served by one index, no JOIN.
DO $$ BEGIN RAISE NOTICE '[DDL] create composite indexes ...'; END $$;
CREATE INDEX IF NOT EXISTS idx_t_eval_row_bu_askdate     ON t_eval_task_row (bu, ask_date);
CREATE INDEX IF NOT EXISTS idx_t_eval_row_bu_intent_date ON t_eval_task_row (bu, j_intent, ask_date);
DO $$ BEGIN RAISE NOTICE '[OK ]  composite indexes'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260717_arkpgdata_eval_row_ask_date.sql complete'; END $$;

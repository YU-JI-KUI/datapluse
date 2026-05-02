DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260501_arkpgdata_add_embed_job_column.sql -- add embed_job column to t_pipeline_status'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;

-- embed_job stores the async vectorization job state, decoupled from the main pipeline flow.
-- Only written by POST /pipeline/embed; main pipeline progress updates never touch this column.

DO $$ BEGIN RAISE NOTICE '[DDL] t_pipeline_status add column embed_job ...'; END $$;
ALTER TABLE t_pipeline_status
    ADD COLUMN IF NOT EXISTS embed_job JSONB;
COMMENT ON COLUMN t_pipeline_status.embed_job IS '向量化离线任务状态（与主流程解耦，独立写入）';
DO $$ BEGIN RAISE NOTICE '[OK ]  embed_job column ready'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260501_arkpgdata_add_embed_job_column.sql done'; END $$;

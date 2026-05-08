-- =============================================================
-- [SCRIPT] 20260508_arkpgdata_add_annotation_cot_fields.sql
--          Add structured COT fields to t_annotation:
--          category / keywords / keywords_desc
-- =============================================================
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260508_arkpgdata_add_annotation_cot_fields.sql'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;

-- ── category ──────────────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '[DDL] add column category to t_annotation ...'; END $$;
ALTER TABLE t_annotation
    ADD COLUMN IF NOT EXISTS category VARCHAR(200) DEFAULT NULL;
COMMENT ON COLUMN t_annotation.category IS '业务分类名称（来自 t_category.name，标注员点选）';
DO $$ BEGIN RAISE NOTICE '[OK ]  column category added'; END $$;

-- ── keywords ──────────────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '[DDL] add column keywords to t_annotation ...'; END $$;
ALTER TABLE t_annotation
    ADD COLUMN IF NOT EXISTS keywords VARCHAR(500) DEFAULT NULL;
COMMENT ON COLUMN t_annotation.keywords IS '关键词（标注员从文本中提取的核心词，逗号分隔或自由输入）';
DO $$ BEGIN RAISE NOTICE '[OK ]  column keywords added'; END $$;

-- ── keywords_desc ─────────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '[DDL] add column keywords_desc to t_annotation ...'; END $$;
ALTER TABLE t_annotation
    ADD COLUMN IF NOT EXISTS keywords_desc TEXT DEFAULT NULL;
COMMENT ON COLUMN t_annotation.keywords_desc IS '关键词说明（对关键词的进一步解释，TEXT 类型）';
DO $$ BEGIN RAISE NOTICE '[OK ]  column keywords_desc added'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260508_arkpgdata_add_annotation_cot_fields.sql complete'; END $$;

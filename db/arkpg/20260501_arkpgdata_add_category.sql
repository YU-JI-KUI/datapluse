-- =======================================================
-- [SCRIPT] 20260501_arkpgdata_add_category.sql -- add t_category table
-- =======================================================
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260501_arkpgdata_add_category.sql -- add t_category'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;

-- ── create t_category ──────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '[DDL] create t_category ...'; END $$;

CREATE TABLE IF NOT EXISTS t_category (
    id          BIGSERIAL       NOT NULL,
    dataset_id  BIGINT          NOT NULL,
    name        VARCHAR(200)    NOT NULL,
    description TEXT            NOT NULL DEFAULT '',
    created_at  TIMESTAMP(6)    NOT NULL,
    created_by  VARCHAR(100)    NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6)    NOT NULL,
    updated_by  VARCHAR(100)    NOT NULL DEFAULT '',
    CONSTRAINT pk_t_category PRIMARY KEY (id)
);

COMMENT ON TABLE  t_category             IS '业务分类表（按数据集隔离）';
COMMENT ON COLUMN t_category.id          IS '主键ID';
COMMENT ON COLUMN t_category.dataset_id  IS '所属数据集ID（逻辑外键 → t_dataset.id）';
COMMENT ON COLUMN t_category.name        IS '分类名称';
COMMENT ON COLUMN t_category.description IS '分类介绍（富文本/多行文本）';
COMMENT ON COLUMN t_category.created_at  IS '创建时间';
COMMENT ON COLUMN t_category.created_by  IS '创建人';
COMMENT ON COLUMN t_category.updated_at  IS '最后更新时间';
COMMENT ON COLUMN t_category.updated_by  IS '最后更新人';

DO $$ BEGIN RAISE NOTICE '[OK ]  t_category'; END $$;

-- ── indexes ────────────────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '[DDL] create indexes for t_category ...'; END $$;

CREATE INDEX IF NOT EXISTS idx_t_category_dataset ON t_category(dataset_id);
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_category_dataset_name ON t_category(dataset_id, name);

DO $$ BEGIN RAISE NOTICE '[OK ]  indexes for t_category'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260501_arkpgdata_add_category.sql complete'; END $$;

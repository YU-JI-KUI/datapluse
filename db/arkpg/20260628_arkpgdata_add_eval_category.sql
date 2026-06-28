DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260628_arkpgdata_add_eval_category.sql -- AI eval business categories'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 对话评测业务分类表：把原先写死在 prompts/<bu>/categories.json 的业务分类
-- 搬进数据库，支持按 BU 在页面增删改，改后不重启即生效（库无记录时加载层回退读
-- categories.json 作出厂默认）。(bu, name) 唯一标识一条分类。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_category ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_category (
    id          BIGSERIAL    NOT NULL,
    bu          VARCHAR(64)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    definition  TEXT         NOT NULL DEFAULT '',
    sort_order  INTEGER      NOT NULL DEFAULT 0,
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(100) NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_category PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_category            IS 'AI对话评测业务分类表（每个BU一套，支持页面增删改，改后不重启即生效）';
COMMENT ON COLUMN t_eval_category.id         IS '主键ID';
COMMENT ON COLUMN t_eval_category.bu         IS '所属业务单元：securities=证券 / life=寿险';
COMMENT ON COLUMN t_eval_category.name       IS '业务分类名';
COMMENT ON COLUMN t_eval_category.definition IS '分类定义（含正例反例，喂给大模型判定）';
COMMENT ON COLUMN t_eval_category.sort_order IS '排序序号（小在前）';
COMMENT ON COLUMN t_eval_category.created_at IS '创建时间';
COMMENT ON COLUMN t_eval_category.created_by IS '创建人';
COMMENT ON COLUMN t_eval_category.updated_at IS '更新时间';
COMMENT ON COLUMN t_eval_category.updated_by IS '更新人';

CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_category_bu_name ON t_eval_category(bu, name);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_category'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260628_arkpgdata_add_eval_category.sql complete'; END $$;

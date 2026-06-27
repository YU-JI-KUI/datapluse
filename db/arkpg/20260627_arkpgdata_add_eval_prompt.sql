DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260627_arkpgdata_add_eval_prompt.sql -- AI eval editable prompts'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- AI 对话评测提示词表：把原先散在 prompts/*.md 的提示词搬进数据库，
-- 支持页面实时编辑，改后不重启即生效（库无记录时加载层回退读文件作出厂默认）。
-- (bu, name) 唯一标识一条提示词；bu 用约定字符串区分作用域。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_prompt ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_prompt (
    id          BIGSERIAL    NOT NULL,
    bu          VARCHAR(64)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    content     TEXT         NOT NULL DEFAULT '',
    description VARCHAR(255) NOT NULL DEFAULT '',
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(100) NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_prompt PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_prompt             IS 'AI对话评测提示词表（支持页面实时编辑，改后不重启即生效）';
COMMENT ON COLUMN t_eval_prompt.id          IS '主键ID';
COMMENT ON COLUMN t_eval_prompt.bu          IS '作用域：_root=根目录共用 / _default=各BU通用兜底 / 其余=具体BU(securities=证券,life=寿险)';
COMMENT ON COLUMN t_eval_prompt.name        IS '模板名（沿用文件名），如 judge_system.md / task_dispatch.md';
COMMENT ON COLUMN t_eval_prompt.content     IS '提示词正文';
COMMENT ON COLUMN t_eval_prompt.description IS '用途说明（编辑页展示）';
COMMENT ON COLUMN t_eval_prompt.created_at  IS '创建时间';
COMMENT ON COLUMN t_eval_prompt.created_by  IS '创建人';
COMMENT ON COLUMN t_eval_prompt.updated_at  IS '更新时间';
COMMENT ON COLUMN t_eval_prompt.updated_by  IS '更新人';

CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_prompt_bu_name ON t_eval_prompt(bu, name);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_prompt'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260627_arkpgdata_add_eval_prompt.sql complete'; END $$;

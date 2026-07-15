DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260715_arkpgdata_add_user_nickname.sql -- add t_user.nickname'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- 用户表加昵称：username 全是英文不好辨认，nickname 供页面快速识别用户是谁。
-- 普通列（非唯一），旧用户默认空串；显示时空则兜底用 username。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DDL] add column t_user.nickname ...'; END $$;
ALTER TABLE t_user ADD COLUMN IF NOT EXISTS nickname VARCHAR(100) NOT NULL DEFAULT '';
COMMENT ON COLUMN t_user.nickname IS '用户昵称（展示用，便于辨认；空则页面兜底用username）';
DO $$ BEGIN RAISE NOTICE '[OK ]  t_user.nickname'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260715_arkpgdata_add_user_nickname.sql complete'; END $$;

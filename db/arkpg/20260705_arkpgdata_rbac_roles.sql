DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260705_arkpgdata_rbac_roles.sql -- RBAC roles & permissions refresh'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- 刷新四角色权限集，并新增 evaluator 角色。权限集与 core/permissions.py +
-- base.py _PRESET_ROLES 保持同源；应用启动 seed_defaults() 也会覆盖同步，
-- 本脚本保证「从零/老库部署」时 DB 直接为最终状态。幂等：ON CONFLICT DO UPDATE。
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '[DATA] upsert roles (admin/annotator/evaluator/viewer) ...'; END $$;
INSERT INTO t_role (name, description, permissions, created_by, updated_by) VALUES
    ('admin',     '超级管理员，拥有所有权限', '["*"]', 'system', 'system'),
    ('annotator', '标注员，负责标注平台全流程（标注、冲突裁决、分类、导出）',
     '["data:read","data:write","annotation:read","annotation:write","conflict:read","conflict:detect","conflict:resolve","category:read","category:write","comment:write","pre_annotation:run","pipeline:read","pipeline:run","export:read","export:create","template:write","config:read"]',
     'system', 'system'),
    ('evaluator', '评测员，仅负责 AI 对话评测模块',
     '["data:read","eval:read","eval:write","export:read","export:create","config:read"]',
     'system', 'system'),
    ('viewer',    '只读访问，可查看各模块数据但不可操作',
     '["data:read","annotation:read","conflict:read","category:read","pipeline:read","export:read","config:read","eval:read"]',
     'system', 'system')
ON CONFLICT (name) DO UPDATE
    SET permissions = EXCLUDED.permissions,
        description = EXCLUDED.description,
        updated_by  = 'system';
DO $$ BEGIN RAISE NOTICE '[OK ]  roles upserted'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260705_arkpgdata_rbac_roles.sql complete'; END $$;

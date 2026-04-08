-- =============================================================================
-- Datapulse 数据库初始化脚本
-- 执行前请确认数据库已存在：CREATE DATABASE datapulse;
-- 执行方式：psql -h <host> -p <port> -U <user> -d datapulse -f database/init.sql
-- =============================================================================


-- =============================================================================
-- 1. 数据集表（datasets）
--    多 dataset 隔离：不同业务场景各自维护独立的数据、配置和模板
-- =============================================================================
CREATE TABLE IF NOT EXISTS datasets (
    id          SERIAL       NOT NULL,
    name        VARCHAR(100) NOT NULL,              -- 数据集名称，如"保险意图 v1"
    description TEXT,                               -- 业务说明，可选
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE, -- 软删除标记，FALSE 表示已归档
    created_at  VARCHAR(30),                        -- 创建时间（上海时区，yyyy-MM-dd HH:mm:ss）
    updated_at  VARCHAR(30),                        -- 最后更新时间
    CONSTRAINT pk_datasets PRIMARY KEY (id)
);

COMMENT ON TABLE  datasets            IS '数据集：多 pipeline 隔离单元，每个 dataset 有独立的数据、配置和模板';
COMMENT ON COLUMN datasets.id         IS '数据集自增主键';
COMMENT ON COLUMN datasets.name       IS '数据集名称，要求见名知意，如"保险意图 v2"';
COMMENT ON COLUMN datasets.is_active  IS '是否启用。FALSE=已归档，不再接受新数据，但历史数据保留';


-- =============================================================================
-- 2. 系统配置表（system_config）
--    每个 dataset 独立一行配置，config_data 为整块 JSONB
--    字段扩展只需修改 JSON 结构，无需 ALTER TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_config (
    dataset_id  INTEGER      NOT NULL,
    config_data JSONB        NOT NULL DEFAULT '{}', -- 完整配置 JSON（见下方结构说明）
    updated_at  VARCHAR(30),                        -- 最后保存时间
    updated_by  VARCHAR(100),                       -- 最后保存的用户名
    CONSTRAINT pk_system_config PRIMARY KEY (dataset_id),
    CONSTRAINT fk_system_config_dataset FOREIGN KEY (dataset_id)
        REFERENCES datasets(id) ON DELETE CASCADE
);

COMMENT ON TABLE  system_config             IS '系统配置：每个 dataset 独立一行，所有参数存于 config_data JSONB';
COMMENT ON COLUMN system_config.dataset_id  IS '关联的 dataset，一对一关系';
COMMENT ON COLUMN system_config.config_data IS
    '配置 JSON 结构示例：
    {
      "llm": {
        "use_mock": true,               -- true=随机预标注（开发），false=调用真实 LLM
        "api_url": "http://...",        -- 内网 LLM 接口地址
        "model_name": "your-model",
        "timeout": 30
      },
      "embedding": {
        "use_mock": true,               -- true=随机向量，false=加载本地模型
        "model_path": "./models/bge-base-zh",
        "batch_size": 64
      },
      "similarity": {
        "threshold_high": 0.9,          -- 语义冲突高风险阈值（cosine 相似度）
        "threshold_mid": 0.8,           -- 中风险阈值（预留）
        "topk": 5                       -- 语义检索返回 top-k 邻居数
      },
      "pipeline": {
        "batch_size": 32               -- LLM 预标注每批大小
      },
      "labels": ["寿险意图", "拒识"]   -- 标注标签列表
    }';
COMMENT ON COLUMN system_config.updated_by  IS '最后修改配置的用户名，用于审计';


-- =============================================================================
-- 3. 角色表（roles）
--    预置三个角色：admin / annotator / viewer
--    permissions 为权限字符串数组，["*"] 表示全部权限
-- =============================================================================
CREATE TABLE IF NOT EXISTS roles (
    id          SERIAL       NOT NULL,
    name        VARCHAR(50)  NOT NULL,              -- 角色名称：admin / annotator / viewer
    description TEXT,                               -- 角色说明
    permissions JSONB        NOT NULL DEFAULT '[]', -- 权限列表，如 ["data:read", "annotation:write"]
    created_at  VARCHAR(30),
    CONSTRAINT pk_roles      PRIMARY KEY (id),
    CONSTRAINT uq_roles_name UNIQUE (name)
);

COMMENT ON TABLE  roles             IS 'RBAC 角色表，角色与权限的绑定';
COMMENT ON COLUMN roles.name        IS '角色标识符，系统预置：admin / annotator / viewer';
COMMENT ON COLUMN roles.permissions IS
    '权限字符串数组。["*"] = 所有权限（admin 使用）。
    细粒度权限字符串：
      data:read          读取数据列表和详情
      data:write         上传、删除数据
      annotation:read    查看标注队列
      annotation:write   提交标注结果
      pipeline:read      查看 pipeline 状态
      pipeline:run       触发 pipeline 运行
      export:read        查看导出模板
      export:create      执行导出
      config:read        查看配置
      config:write       修改配置
      user:read          查看用户列表
      user:write         创建/修改/停用用户
      dataset:read       查看数据集列表
      dataset:write      创建/修改数据集';


-- =============================================================================
-- 4. 用户表（users）
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL       NOT NULL,
    username      VARCHAR(100) NOT NULL,            -- 登录用户名，全局唯一
    email         VARCHAR(200),                      -- 邮箱（可选，暂不做认证）
    password_hash VARCHAR(200) NOT NULL,             -- bcrypt 哈希，不存明文
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE, -- FALSE=账号已停用，无法登录
    created_at    VARCHAR(30),
    updated_at    VARCHAR(30),
    last_login_at VARCHAR(30),                       -- 最近一次登录时间，用于安全审计
    CONSTRAINT pk_users          PRIMARY KEY (id),
    CONSTRAINT uq_users_username UNIQUE (username)
);

COMMENT ON TABLE  users                IS 'RBAC 用户表';
COMMENT ON COLUMN users.username       IS '登录用户名，大小写敏感，全局唯一';
COMMENT ON COLUMN users.password_hash  IS 'bcrypt 哈希密码（passlib bcrypt），绝不存储明文';
COMMENT ON COLUMN users.is_active      IS '是否可登录。停用账号后 JWT 仍可能在有效期内，需前端配合处理';
COMMENT ON COLUMN users.last_login_at  IS '最近登录时间（上海时区），用于安全审计，每次登录更新';


-- =============================================================================
-- 5. 用户-角色关联表（user_roles）
--    全局角色（不区分 dataset），简化 RBAC 实现
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_roles (
    user_id    INTEGER     NOT NULL,
    role_id    INTEGER     NOT NULL,
    created_at VARCHAR(30),                          -- 授权时间
    CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id)
        REFERENCES roles(id) ON DELETE CASCADE
);

COMMENT ON TABLE  user_roles           IS '用户与角色的多对多关联，全局生效（不区分 dataset）';
COMMENT ON COLUMN user_roles.user_id   IS '关联用户 ID';
COMMENT ON COLUMN user_roles.role_id   IS '关联角色 ID';
COMMENT ON COLUMN user_roles.created_at IS '授权时间，用于审计';


-- =============================================================================
-- 6. 数据条目表（data_items）
--    核心业务表，每条对应一条待标注的文本
-- =============================================================================
CREATE TABLE IF NOT EXISTS data_items (
    id              BIGSERIAL    NOT NULL,
    dataset_id      INTEGER      NOT NULL,           -- 所属数据集（强制关联）
    text            TEXT         NOT NULL,           -- 用户原始输入文本，不做清洗修改
    status          VARCHAR(20)  NOT NULL DEFAULT 'raw', -- 数据当前所在阶段（见状态机）
    label           VARCHAR(200),                    -- 人工标注的最终标签
    model_pred      VARCHAR(200),                    -- LLM 预标注预测标签
    model_score     FLOAT,                           -- LLM 预测置信度，范围 0~1
    annotator       VARCHAR(100),                    -- 最后标注的用户名（来自 JWT sub）
    annotated_at    VARCHAR(30),                     -- 标注提交时间（上海时区）
    conflict_flag   BOOLEAN      DEFAULT FALSE,      -- 是否存在标注冲突或语义冲突
    conflict_type   VARCHAR(50),                     -- 冲突类型：label_conflict / semantic_conflict
    conflict_detail JSONB,                           -- 冲突详情（见注释）
    source_file     VARCHAR(500),                    -- 来源文件名，便于溯源
    created_at      VARCHAR(30),                     -- 首次写入时间（上海时区）
    updated_at      VARCHAR(30),                     -- 最后更新时间（上海时区）
    CONSTRAINT pk_data_items PRIMARY KEY (id),
    CONSTRAINT fk_data_items_dataset FOREIGN KEY (dataset_id)
        REFERENCES datasets(id) ON DELETE CASCADE
);

COMMENT ON TABLE  data_items               IS '核心数据表：意图识别数据条目，随 pipeline 流转状态';
COMMENT ON COLUMN data_items.dataset_id    IS '所属数据集，不同 dataset 的数据完全隔离';
COMMENT ON COLUMN data_items.status        IS
    '状态机（线性流转）：
      raw            → 原始上传，未经处理
      processed      → 文本清洗完成
      pre_annotated  → LLM 预标注完成，等待人工审核
      labeling       → 标注员已"取走"，标注进行中
      labeled        → 人工标注完成，待冲突检测
      checked        → 通过冲突检测，可导出的高质量数据';
COMMENT ON COLUMN data_items.label         IS '人工最终标签，只有 status=labeled/checked 时有值';
COMMENT ON COLUMN data_items.model_score   IS 'LLM 置信度，0~1。高分表示模型较确定，可作为标注优先级参考';
COMMENT ON COLUMN data_items.conflict_flag IS 'TRUE 表示存在冲突（label_conflict 或 semantic_conflict），需人工审核';
COMMENT ON COLUMN data_items.conflict_detail IS
    'label_conflict 结构：
    {"text":"...", "conflicting_labels":["A","B"], "annotators":[{"annotator":"u1","label":"A"}]}
    semantic_conflict 结构：
    {"similarity":0.93, "threshold":0.9, "paired_id":123, "paired_text":"...",
     "paired_label":"B", "self_label":"A"}';

CREATE INDEX IF NOT EXISTS idx_data_items_dataset_status
    ON data_items(dataset_id, status);
CREATE INDEX IF NOT EXISTS idx_data_items_created_at
    ON data_items(created_at DESC);


-- =============================================================================
-- 7. 导出模板表（export_templates）
--    每个 dataset 独立管理模板，支持自定义字段映射
-- =============================================================================
CREATE TABLE IF NOT EXISTS export_templates (
    id          SERIAL       NOT NULL,
    dataset_id  INTEGER      NOT NULL,
    name        VARCHAR(100) NOT NULL,              -- 模板名称，如"训练集标准格式"
    description TEXT,                               -- 模板用途说明
    format      VARCHAR(20)  NOT NULL DEFAULT 'json', -- 输出格式：json / excel / csv
    columns     JSONB,                              -- 字段映射列表（见注释）
    filters     JSONB,                              -- 导出过滤条件（见注释）
    created_at  VARCHAR(30),
    updated_at  VARCHAR(30),
    CONSTRAINT pk_export_templates PRIMARY KEY (id),
    CONSTRAINT fk_export_templates_dataset FOREIGN KEY (dataset_id)
        REFERENCES datasets(id) ON DELETE CASCADE
);

COMMENT ON TABLE  export_templates            IS '导出模板：定义导出时的字段映射、格式和过滤条件，每个 dataset 独立';
COMMENT ON COLUMN export_templates.columns    IS
    '字段映射数组，每项为：
    {"source": "text", "target": "sentence", "include": true}
      source  = 数据库字段名（来自 data_items）
      target  = 输出文件中的字段名（可自定义）
      include = 是否包含在导出中';
COMMENT ON COLUMN export_templates.filters    IS
    '过滤条件：
    {"status": "checked", "include_conflicts": false}
      status            = 只导出该状态的数据
      include_conflicts = false 则排除 conflict_flag=true 的数据';
COMMENT ON COLUMN export_templates.format     IS '输出格式：json（带缩进）/ excel（xlsx）/ csv（utf-8-sig）';


-- =============================================================================
-- 8. Pipeline 状态表（pipeline_status）
--    每个 dataset 独立一行，记录最近一次 pipeline 运行状态
-- =============================================================================
CREATE TABLE IF NOT EXISTS pipeline_status (
    dataset_id   INTEGER      NOT NULL,
    status       VARCHAR(20)  DEFAULT 'idle',       -- idle / running / completed / error
    current_step VARCHAR(50),                        -- 当前执行步骤：process / pre_annotate / embed / check
    progress     INTEGER      DEFAULT 0,             -- 整体进度百分比，0~100
    detail       JSONB,                              -- 当前步骤进度详情（见注释）
    started_at   VARCHAR(30),                        -- pipeline 开始时间
    finished_at  VARCHAR(30),                        -- pipeline 完成/失败时间
    error        TEXT,                               -- 失败时的错误信息
    updated_at   VARCHAR(30),                        -- 最后更新时间
    CONSTRAINT pk_pipeline_status PRIMARY KEY (dataset_id),
    CONSTRAINT fk_pipeline_status_dataset FOREIGN KEY (dataset_id)
        REFERENCES datasets(id) ON DELETE CASCADE
);

COMMENT ON TABLE  pipeline_status             IS 'Pipeline 运行状态：每个 dataset 独立一行，记录最近一次运行';
COMMENT ON COLUMN pipeline_status.status      IS 'idle=未运行 / running=运行中 / completed=完成 / error=失败';
COMMENT ON COLUMN pipeline_status.progress    IS '整体进度 0-100，各步骤进度加权平均';
COMMENT ON COLUMN pipeline_status.detail      IS
    '当前步骤进度详情：
    {"processed":100, "total":500, "skipped":5, "pct":"20.0%",
     "speed_per_sec":12.5, "eta_seconds":32, "elapsed_seconds":8.0}';


-- =============================================================================
-- 初始数据：预置角色
-- SERIAL 自增，不指定 id，由数据库分配
-- =============================================================================
INSERT INTO roles (name, description, permissions, created_at)
VALUES
    ('admin',
     '超级管理员，拥有所有权限',
     '["*"]',
     '2026-01-01 00:00:00'),

    ('annotator',
     '标注员，可查看数据、提交标注、执行导出',
     '["data:read","annotation:read","annotation:write","pipeline:read","export:read","export:create","config:read"]',
     '2026-01-01 00:00:00'),

    ('viewer',
     '只读访问，可查看数据和导出结果，不可操作',
     '["data:read","annotation:read","pipeline:read","export:read","config:read"]',
     '2026-01-01 00:00:00')
ON CONFLICT (name) DO NOTHING;


-- =============================================================================
-- 初始数据：默认数据集 + 配置
-- SERIAL 自增，dataset 的 id 由序列分配（通常为 1）
-- system_config 通过子查询关联
-- =============================================================================
INSERT INTO datasets (name, description, is_active, created_at, updated_at)
VALUES (
    '默认数据集',
    '系统初始化创建的默认数据集',
    TRUE,
    '2026-01-01 00:00:00',
    '2026-01-01 00:00:00'
)
ON CONFLICT DO NOTHING;

INSERT INTO system_config (dataset_id, config_data, updated_at, updated_by)
SELECT
    d.id,
    '{
        "llm": {
            "use_mock": true,
            "api_url": "http://internal-llm-platform/api/v1/chat",
            "model_name": "internal-llm",
            "timeout": 30
        },
        "embedding": {
            "use_mock": true,
            "model_path": "./models/bge-base-zh",
            "batch_size": 64
        },
        "similarity": {
            "threshold_high": 0.9,
            "threshold_mid": 0.8,
            "topk": 5
        },
        "pipeline": {
            "batch_size": 32
        },
        "labels": ["寿险意图", "拒识", "健康险意图", "财险意图", "其他意图"]
    }'::jsonb,
    '2026-01-01 00:00:00',
    'system'
FROM datasets d
WHERE d.name = '默认数据集'
ON CONFLICT (dataset_id) DO NOTHING;


-- =============================================================================
-- 管理员账号
-- 请使用 tools/seed_admin.py 交互式创建，或参考以下手动方式：
--   1. 运行 tools/hash_password.py 生成 bcrypt 哈希
--   2. 将 <BCRYPT_HASH> 替换为生成的哈希值后取消注释执行
-- =============================================================================
-- INSERT INTO users (username, email, password_hash, is_active, created_at, updated_at)
-- VALUES ('admin', '', '<BCRYPT_HASH>', TRUE, NOW()::text, NOW()::text);
--
-- INSERT INTO user_roles (user_id, role_id, created_at)
-- SELECT u.id, r.id, NOW()::text
-- FROM users u, roles r
-- WHERE u.username = 'admin' AND r.name = 'admin';

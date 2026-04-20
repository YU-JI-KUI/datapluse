-- =============================================================================
-- Datapulse 数据库初始化脚本 v2.0
-- 执行前请确认数据库已存在：CREATE DATABASE datapulse;
-- 执行方式：psql -h <host> -p <port> -U <user> -d datapulse -f database/init.sql
--
-- 设计规范：
--   - 表名以 t_ 开头
--   - 禁止物理外键，使用逻辑外键
--   - 所有用户字段统一使用 username（禁止 user_id）
--   - 时间字段统一 TIMESTAMP(6)
--   - 所有表包含完整审计字段
-- =============================================================================


-- =============================================================================
-- 1. 数据集表
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_dataset (
    id          BIGSERIAL    NOT NULL,
    name        VARCHAR(100) NOT NULL,
    description TEXT         NOT NULL DEFAULT '',
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(45)  NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_dataset PRIMARY KEY (id)
);

COMMENT ON TABLE  t_dataset             IS '数据集表';
COMMENT ON COLUMN t_dataset.id          IS '主键ID';
COMMENT ON COLUMN t_dataset.name        IS '数据集名称，如"保险意图 v1"';
COMMENT ON COLUMN t_dataset.description IS '数据集描述';
COMMENT ON COLUMN t_dataset.status      IS '状态：active=启用，inactive=停用';
COMMENT ON COLUMN t_dataset.created_at  IS '创建时间';
COMMENT ON COLUMN t_dataset.created_by  IS '创建人';
COMMENT ON COLUMN t_dataset.updated_at  IS '更新时间';
COMMENT ON COLUMN t_dataset.updated_by  IS '最后更新人';


-- =============================================================================
-- 2. 系统配置表（每个 dataset 独立一行，config_data 为整块 JSONB）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_system_config (
    dataset_id  BIGINT       NOT NULL,
    config_data JSONB        NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_system_config PRIMARY KEY (dataset_id)
);

COMMENT ON TABLE  t_system_config             IS '系统配置表：每个 dataset 独立一行，所有参数存于 config_data JSONB';
COMMENT ON COLUMN t_system_config.dataset_id  IS '数据集ID（逻辑外键）';
COMMENT ON COLUMN t_system_config.config_data IS 'JSON 配置结构：{llm:{use_mock,api_url,model_name,timeout}, embedding:{use_mock,model_path,batch_size}, similarity:{threshold_high,threshold_mid,topk}, pipeline:{batch_size}, labels:[...]}';
COMMENT ON COLUMN t_system_config.updated_at  IS '最后保存时间';
COMMENT ON COLUMN t_system_config.updated_by  IS '最后保存的用户名';


-- =============================================================================
-- 3. 角色表
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_role (
    id          BIGSERIAL    NOT NULL,
    name        VARCHAR(50)  NOT NULL,
    description TEXT         NOT NULL DEFAULT '',
    permissions JSONB        NOT NULL DEFAULT '[]',
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(45)  NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_role      PRIMARY KEY (id),
    CONSTRAINT uq_t_role_name UNIQUE (name)
);

COMMENT ON TABLE  t_role             IS 'RBAC 角色表';
COMMENT ON COLUMN t_role.id          IS '主键ID';
COMMENT ON COLUMN t_role.name        IS '角色标识符：admin / annotator / viewer';
COMMENT ON COLUMN t_role.description IS '角色说明';
COMMENT ON COLUMN t_role.permissions IS '权限字符串数组，["*"] 表示全部权限';
COMMENT ON COLUMN t_role.created_at  IS '创建时间';
COMMENT ON COLUMN t_role.created_by  IS '创建人';
COMMENT ON COLUMN t_role.updated_at  IS '更新时间';
COMMENT ON COLUMN t_role.updated_by  IS '最后更新人';


-- =============================================================================
-- 4. 用户表
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_user (
    id            BIGSERIAL    NOT NULL,
    username      VARCHAR(100) NOT NULL,
    email         VARCHAR(200) NOT NULL DEFAULT '',
    password_hash VARCHAR(200) NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMP(6),
    created_at    TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by    VARCHAR(45)  NOT NULL DEFAULT '',
    updated_at    TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by    VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_user          PRIMARY KEY (id),
    CONSTRAINT uq_t_user_username UNIQUE (username)
);

COMMENT ON TABLE  t_user               IS '用户账号表';
COMMENT ON COLUMN t_user.id            IS '主键ID';
COMMENT ON COLUMN t_user.username      IS '登录用户名，全局唯一，大小写敏感';
COMMENT ON COLUMN t_user.email         IS '邮箱，可选';
COMMENT ON COLUMN t_user.password_hash IS 'bcrypt 哈希密码，不存明文';
COMMENT ON COLUMN t_user.is_active     IS '账号是否可登录：TRUE=正常，FALSE=已停用';
COMMENT ON COLUMN t_user.last_login_at IS '最近登录时间，用于安全审计';
COMMENT ON COLUMN t_user.created_at    IS '创建时间';
COMMENT ON COLUMN t_user.created_by    IS '创建人';
COMMENT ON COLUMN t_user.updated_at    IS '更新时间';
COMMENT ON COLUMN t_user.updated_by    IS '最后更新人';


-- =============================================================================
-- 5. 用户-角色关联表（使用 username 逻辑外键，不使用 user_id）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_user_role (
    username   VARCHAR(100) NOT NULL,
    role_name  VARCHAR(50)  NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_user_role PRIMARY KEY (username, role_name)
);

COMMENT ON TABLE  t_user_role           IS '用户与角色的多对多关联（username 逻辑外键）';
COMMENT ON COLUMN t_user_role.username  IS '用户名（逻辑外键 → t_user.username）';
COMMENT ON COLUMN t_user_role.role_name IS '角色名（逻辑外键 → t_role.name）';
COMMENT ON COLUMN t_user_role.created_at IS '授权时间';
COMMENT ON COLUMN t_user_role.created_by IS '授权操作人';


-- =============================================================================
-- 6. 数据条目表（核心，纯数据层，不含标注信息）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_data_item (
    id           BIGSERIAL    NOT NULL,
    dataset_id   BIGINT       NOT NULL,
    content      TEXT         NOT NULL,
    content_hash VARCHAR(64)  NOT NULL,
    source       VARCHAR(50)  NOT NULL DEFAULT '',
    source_ref   VARCHAR(255) NOT NULL DEFAULT '',
    status       VARCHAR(30)  NOT NULL DEFAULT 'raw',
    created_at   TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by   VARCHAR(45)  NOT NULL DEFAULT '',
    updated_at   TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by   VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_data_item PRIMARY KEY (id)
);

COMMENT ON TABLE  t_data_item              IS '数据条目表（纯数据层，标注信息在 t_annotation 中）';
COMMENT ON COLUMN t_data_item.id           IS '主键ID';
COMMENT ON COLUMN t_data_item.dataset_id   IS '数据集ID（逻辑外键）';
COMMENT ON COLUMN t_data_item.content      IS '原始文本内容';
COMMENT ON COLUMN t_data_item.content_hash IS '文本内容 SHA-256 哈希，用于去重';
COMMENT ON COLUMN t_data_item.source       IS '数据来源：excel=Excel文件，csv=CSV文件，json=JSON文件，manual=手动录入';
COMMENT ON COLUMN t_data_item.source_ref   IS '来源引用，如文件名或接口地址';
COMMENT ON COLUMN t_data_item.status       IS '当前阶段（冗余字段，与 t_data_state.stage 保持同步）：raw、cleaned、pre_annotated、annotated、checked';
COMMENT ON COLUMN t_data_item.created_at   IS '创建时间';
COMMENT ON COLUMN t_data_item.created_by   IS '创建人';
COMMENT ON COLUMN t_data_item.updated_at   IS '更新时间';
COMMENT ON COLUMN t_data_item.updated_by   IS '最后更新人';

CREATE UNIQUE INDEX IF NOT EXISTS uk_t_data_item_hash ON t_data_item(dataset_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_t_data_item_dataset_status ON t_data_item(dataset_id, status);


-- =============================================================================
-- 7. 数据流转状态表（控制流，与 t_data_item 一对一）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_data_state (
    data_id    BIGINT       NOT NULL,
    stage      VARCHAR(50)  NOT NULL DEFAULT 'raw',
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_data_state PRIMARY KEY (data_id)
);

COMMENT ON TABLE  t_data_state           IS '数据流转状态表（控制流，与 t_data_item 一对一）';
COMMENT ON COLUMN t_data_state.data_id   IS '数据ID（逻辑外键 → t_data_item.id）';
COMMENT ON COLUMN t_data_state.stage     IS '当前阶段：raw=原始上传，cleaned=清洗完成，pre_annotated=LLM预标注完成，annotated=人工标注完成，checked=冲突检测通过';
COMMENT ON COLUMN t_data_state.updated_at IS '状态更新时间';
COMMENT ON COLUMN t_data_state.updated_by IS '状态更新操作人';


-- =============================================================================
-- 8. LLM 预标注表（记录每次预标注结果，支持多版本）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_pre_annotation (
    id         BIGSERIAL      NOT NULL,
    data_id    BIGINT         NOT NULL,
    model_name VARCHAR(100)   NOT NULL,
    label      VARCHAR(200)   NOT NULL,
    score      NUMERIC(5, 4),
    cot        TEXT,
    version    INT            NOT NULL DEFAULT 1,
    created_at TIMESTAMP(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)    NOT NULL DEFAULT '',
    CONSTRAINT pk_t_pre_annotation PRIMARY KEY (id)
);

COMMENT ON TABLE  t_pre_annotation            IS 'LLM 预标注表';
COMMENT ON COLUMN t_pre_annotation.id         IS '主键ID';
COMMENT ON COLUMN t_pre_annotation.data_id    IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_pre_annotation.model_name IS '模型名称';
COMMENT ON COLUMN t_pre_annotation.label      IS '预测标签';
COMMENT ON COLUMN t_pre_annotation.score      IS '置信度，范围 0~1';
COMMENT ON COLUMN t_pre_annotation.cot        IS 'Chain of Thought 推理过程，记录模型决策依据';
COMMENT ON COLUMN t_pre_annotation.version    IS '预标注版本号，同一数据多次预标注递增';
COMMENT ON COLUMN t_pre_annotation.created_at IS '创建时间';
COMMENT ON COLUMN t_pre_annotation.created_by IS '触发人（pipeline 操作者）';

CREATE INDEX IF NOT EXISTS idx_t_pre_annotation_data ON t_pre_annotation(data_id);


-- =============================================================================
-- 9. 人工标注表（核心，支持多人标注 + 多版本历史）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_annotation (
    id         BIGSERIAL    NOT NULL,
    data_id    BIGINT       NOT NULL,
    username   VARCHAR(100) NOT NULL,
    label      VARCHAR(200) NOT NULL,
    cot        TEXT,
    version    INT          NOT NULL DEFAULT 1,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_annotation PRIMARY KEY (id)
);

COMMENT ON TABLE  t_annotation           IS '人工标注表（支持多人标注，每人可多版本）';
COMMENT ON COLUMN t_annotation.id        IS '主键ID';
COMMENT ON COLUMN t_annotation.data_id   IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_annotation.username  IS '标注人用户名（逻辑外键）';
COMMENT ON COLUMN t_annotation.label     IS '标注标签';
COMMENT ON COLUMN t_annotation.cot       IS 'Chain of Thought 标注理由，标注员填写的决策依据';
COMMENT ON COLUMN t_annotation.version   IS '版本号，同一用户对同一数据多次标注时递增';
COMMENT ON COLUMN t_annotation.is_active IS '是否为有效版本：TRUE=当前版本，FALSE=历史版本';
COMMENT ON COLUMN t_annotation.created_at IS '标注时间';
COMMENT ON COLUMN t_annotation.created_by IS '操作人（通常与 username 相同）';

CREATE INDEX IF NOT EXISTS idx_t_annotation_data    ON t_annotation(data_id);
CREATE INDEX IF NOT EXISTS idx_t_annotation_user    ON t_annotation(data_id, username);
CREATE INDEX IF NOT EXISTS idx_t_annotation_active  ON t_annotation(data_id, is_active);


-- =============================================================================
-- 10. 标注结果汇总表（每条数据一行，由标注写入自动触发聚合）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_annotation_result (
    id              BIGSERIAL    NOT NULL,
    data_id         BIGINT       NOT NULL,
    dataset_id      BIGINT       NOT NULL,
    final_label     VARCHAR(200),
    label_source    VARCHAR(20)  NOT NULL DEFAULT 'auto',
    annotator_count INT          NOT NULL DEFAULT 0,
    resolver        VARCHAR(100),
    cot             TEXT,
    updated_at      TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by      VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_annotation_result        PRIMARY KEY (id),
    CONSTRAINT uq_t_annotation_result_data   UNIQUE (data_id)
);

COMMENT ON TABLE  t_annotation_result                  IS '标注结果汇总表：每条数据一行，由 t_annotation 写入触发聚合维护';
COMMENT ON COLUMN t_annotation_result.id               IS '主键ID';
COMMENT ON COLUMN t_annotation_result.data_id          IS '数据ID（逻辑外键 → t_data_item.id），全局唯一';
COMMENT ON COLUMN t_annotation_result.dataset_id       IS '数据集ID（冗余，方便按 dataset 聚合查询）';
COMMENT ON COLUMN t_annotation_result.final_label      IS '最终标注标签；auto=多数投票结果，manual=冲突裁决结果；无标注时为 NULL';
COMMENT ON COLUMN t_annotation_result.label_source     IS '标签来源：auto=多数投票自动计算，manual=冲突裁决手动设定';
COMMENT ON COLUMN t_annotation_result.annotator_count  IS '当前有效标注人数（is_active=TRUE 的行数）';
COMMENT ON COLUMN t_annotation_result.resolver         IS '冲突裁决人用户名；仅 label_source=manual 时有值';
COMMENT ON COLUMN t_annotation_result.cot              IS '裁决时的 Chain of Thought 理由（manual 时由裁决人填写，auto 时为 NULL）';
COMMENT ON COLUMN t_annotation_result.updated_at       IS '最后更新时间';
COMMENT ON COLUMN t_annotation_result.updated_by       IS '最后更新操作人';

CREATE INDEX IF NOT EXISTS idx_t_annotation_result_dataset ON t_annotation_result(dataset_id);


-- =============================================================================
-- 11. 数据评论表（标注讨论 / 说明原因）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_data_comment (
    id         BIGSERIAL    NOT NULL,
    data_id    BIGINT       NOT NULL,
    username   VARCHAR(100) NOT NULL,
    comment    TEXT         NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_data_comment PRIMARY KEY (id)
);

COMMENT ON TABLE  t_data_comment           IS '数据评论表（标注讨论 / 说明原因）';
COMMENT ON COLUMN t_data_comment.id        IS '主键ID';
COMMENT ON COLUMN t_data_comment.data_id   IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_data_comment.username  IS '评论人用户名';
COMMENT ON COLUMN t_data_comment.comment   IS '评论内容';
COMMENT ON COLUMN t_data_comment.created_at IS '评论时间';
COMMENT ON COLUMN t_data_comment.created_by IS '操作人';

CREATE INDEX IF NOT EXISTS idx_t_data_comment_data ON t_data_comment(data_id);


-- =============================================================================
-- 12. 冲突检测表（标注冲突 + 语义冲突，独立可追溯）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_conflict (
    id            BIGSERIAL    NOT NULL,
    data_id       BIGINT       NOT NULL,
    conflict_type VARCHAR(50)  NOT NULL,
    detail        JSONB        NOT NULL DEFAULT '{}',
    status        VARCHAR(20)  NOT NULL DEFAULT 'open',
    created_at    TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by    VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_conflict PRIMARY KEY (id)
);

COMMENT ON TABLE  t_conflict               IS '冲突检测记录表';
COMMENT ON COLUMN t_conflict.id            IS '主键ID';
COMMENT ON COLUMN t_conflict.data_id       IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_conflict.conflict_type IS '冲突类型：label_conflict=标注冲突，semantic_conflict=语义冲突';
COMMENT ON COLUMN t_conflict.detail        IS '冲突详情 JSON：label_conflict 包含 conflicting_labels/annotators；semantic_conflict 包含 similarity/threshold/paired_id/paired_text/paired_label';
COMMENT ON COLUMN t_conflict.status        IS '冲突状态：open=待处理，resolved=已解决';
COMMENT ON COLUMN t_conflict.created_at    IS '创建时间';
COMMENT ON COLUMN t_conflict.created_by    IS '检测触发人';

CREATE INDEX IF NOT EXISTS idx_t_conflict_data   ON t_conflict(data_id);
CREATE INDEX IF NOT EXISTS idx_t_conflict_status ON t_conflict(status);


-- =============================================================================
-- 13. 导出模板表
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_export_template (
    id          BIGSERIAL    NOT NULL,
    dataset_id  BIGINT       NOT NULL,
    name        VARCHAR(100) NOT NULL,
    description TEXT         NOT NULL DEFAULT '',
    format      VARCHAR(20)  NOT NULL DEFAULT 'json',
    columns     JSONB,
    filters     JSONB,
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(45)  NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_export_template PRIMARY KEY (id)
);

COMMENT ON TABLE  t_export_template             IS '导出模板表';
COMMENT ON COLUMN t_export_template.id          IS '主键ID';
COMMENT ON COLUMN t_export_template.dataset_id  IS '所属数据集ID（逻辑外键）';
COMMENT ON COLUMN t_export_template.name        IS '模板名称';
COMMENT ON COLUMN t_export_template.description IS '模板描述';
COMMENT ON COLUMN t_export_template.format      IS '输出格式：json / excel / csv';
COMMENT ON COLUMN t_export_template.columns     IS '字段映射数组：[{"source":"content","target":"text","include":true},...]';
COMMENT ON COLUMN t_export_template.filters     IS '过滤条件：{"status":"checked","include_conflicts":false}';
COMMENT ON COLUMN t_export_template.created_at  IS '创建时间';
COMMENT ON COLUMN t_export_template.created_by  IS '创建人';
COMMENT ON COLUMN t_export_template.updated_at  IS '更新时间';
COMMENT ON COLUMN t_export_template.updated_by  IS '最后更新人';

CREATE INDEX IF NOT EXISTS idx_t_export_template_dataset ON t_export_template(dataset_id);


-- =============================================================================
-- 14. Pipeline 运行状态表（每个 dataset 独立一行）
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_pipeline_status (
    dataset_id   BIGINT       NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'idle',
    current_step VARCHAR(50)  NOT NULL DEFAULT '',
    progress     INT          NOT NULL DEFAULT 0,
    detail       JSONB,
    started_at   TIMESTAMP(6),
    finished_at  TIMESTAMP(6),
    error        TEXT,
    updated_at   TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by   VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_pipeline_status PRIMARY KEY (dataset_id)
);

COMMENT ON TABLE  t_pipeline_status              IS 'Pipeline 运行状态表，每个 dataset 独立一行';
COMMENT ON COLUMN t_pipeline_status.dataset_id   IS '数据集ID（逻辑外键）';
COMMENT ON COLUMN t_pipeline_status.status       IS 'Pipeline 状态：idle=未运行，running=运行中，completed=完成，error=失败';
COMMENT ON COLUMN t_pipeline_status.current_step IS '当前执行步骤：process / pre_annotate / embed / check';
COMMENT ON COLUMN t_pipeline_status.progress     IS '整体进度 0~100';
COMMENT ON COLUMN t_pipeline_status.detail       IS '当前步骤详情：{processed,total,skipped,pct,speed_per_sec,eta_seconds,elapsed_seconds}';
COMMENT ON COLUMN t_pipeline_status.started_at   IS 'Pipeline 启动时间';
COMMENT ON COLUMN t_pipeline_status.finished_at  IS 'Pipeline 完成或失败时间';
COMMENT ON COLUMN t_pipeline_status.error        IS '失败时的错误信息';
COMMENT ON COLUMN t_pipeline_status.updated_at   IS '最后更新时间';
COMMENT ON COLUMN t_pipeline_status.updated_by   IS '最后更新人';


-- =============================================================================
-- 15. 数据向量表
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_embedding (
    id         BIGSERIAL    NOT NULL,
    dataset_id BIGINT       NOT NULL,
    data_id    BIGINT       NOT NULL,
    vector     BYTEA        NOT NULL,
    dim        SMALLINT     NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT pk_t_embedding             PRIMARY KEY (id),
    CONSTRAINT uq_t_embedding_dataset_data UNIQUE (dataset_id, data_id)
);

COMMENT ON TABLE  t_embedding            IS '数据向量表（embedding），按 dataset 隔离，BYTEA 存储 numpy float32 数组';
COMMENT ON COLUMN t_embedding.id         IS '主键 ID';
COMMENT ON COLUMN t_embedding.dataset_id IS '所属数据集 ID（逻辑外键 → t_dataset.id）';
COMMENT ON COLUMN t_embedding.data_id    IS '数据条目 ID（逻辑外键 → t_data_item.id）';
COMMENT ON COLUMN t_embedding.vector     IS '向量字节，numpy float32 数组经 ndarray.tobytes() 序列化，np.frombuffer 还原';
COMMENT ON COLUMN t_embedding.dim        IS '向量维度（float32 元素个数）';
COMMENT ON COLUMN t_embedding.created_at IS '最近一次向量化时间（UPSERT 时刷新）';

CREATE INDEX IF NOT EXISTS idx_t_embedding_dataset ON t_embedding(dataset_id);


-- =============================================================================
-- 16. 用户-数据集访问权限关联表
-- =============================================================================
CREATE TABLE IF NOT EXISTS t_user_dataset (
    id         BIGSERIAL    NOT NULL,
    username   VARCHAR(100) NOT NULL,
    dataset_id BIGINT       NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_user_dataset    PRIMARY KEY (id),
    CONSTRAINT uq_t_user_dataset    UNIQUE (username, dataset_id)
);

COMMENT ON TABLE  t_user_dataset            IS '用户-数据集访问权限关联表：admin 无需记录，普通用户仅能访问分配给自己的数据集';
COMMENT ON COLUMN t_user_dataset.id         IS '主键ID';
COMMENT ON COLUMN t_user_dataset.username   IS '用户名（逻辑外键 → t_user.username）';
COMMENT ON COLUMN t_user_dataset.dataset_id IS '数据集ID（逻辑外键 → t_dataset.id）';
COMMENT ON COLUMN t_user_dataset.created_at IS '分配时间';
COMMENT ON COLUMN t_user_dataset.created_by IS '分配操作人';

-- username 单列查询已由 UNIQUE(username, dataset_id) 约束索引覆盖，无需单独创建
CREATE INDEX IF NOT EXISTS idx_t_user_dataset_dataset_id ON t_user_dataset(dataset_id);


-- =============================================================================
-- 初始数据：预置角色
-- =============================================================================
INSERT INTO t_role (name, description, permissions, created_by, updated_by)
VALUES
    ('admin',
     '超级管理员，拥有所有权限',
     '["*"]',
     'system', 'system'),

    ('annotator',
     '标注员，可查看数据、提交标注、执行导出',
     '["data:read","annotation:read","annotation:write","pipeline:read","export:read","export:create","config:read"]',
     'system', 'system'),

    ('viewer',
     '只读访问，可查看数据和导出结果，不可操作',
     '["data:read","annotation:read","pipeline:read","export:read","config:read"]',
     'system', 'system')
ON CONFLICT (name) DO NOTHING;


-- =============================================================================
-- 初始数据：默认数据集 + 配置
-- =============================================================================
INSERT INTO t_dataset (name, description, status, created_by, updated_by)
VALUES (
    '默认数据集',
    '系统初始化创建的默认数据集',
    'active',
    'system', 'system'
)
ON CONFLICT DO NOTHING;

INSERT INTO t_system_config (dataset_id, config_data, updated_by)
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
        "labels": ["寿险意图", "拒识"]
    }'::jsonb,
    'system'
FROM t_dataset d
WHERE d.name = '默认数据集'
ON CONFLICT (dataset_id) DO NOTHING;


-- =============================================================================
-- 管理员账号（交互式创建，见 tools/seed_admin.py）
-- =============================================================================
-- INSERT INTO t_user (username, email, password_hash, is_active, created_by, updated_by)
-- VALUES ('admin', '', '<BCRYPT_HASH>', TRUE, 'system', 'system');
--
-- INSERT INTO t_user_role (username, role_name, created_by)
-- VALUES ('admin', 'admin', 'system');

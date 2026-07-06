DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260428_arkpgdata_init.sql -- Datapulse full init'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

-- =============================================================================
-- 建表（CREATE TABLE IF NOT EXISTS 保证幂等）
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. 数据集表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 1/16  t_dataset ...'; END $$;
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
DO $$ BEGIN RAISE NOTICE '[OK ]  t_dataset'; END $$;


-- ---------------------------------------------------------------------------
-- 2. 系统配置表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 2/16  t_system_config ...'; END $$;
CREATE TABLE IF NOT EXISTS t_system_config (
    dataset_id  BIGINT       NOT NULL,
    config_data JSONB        NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_system_config PRIMARY KEY (dataset_id)
);
COMMENT ON TABLE  t_system_config             IS '系统配置表：每个 dataset 独立一行，所有参数存于 config_data JSONB';
COMMENT ON COLUMN t_system_config.dataset_id  IS '数据集ID（逻辑外键）';
COMMENT ON COLUMN t_system_config.config_data IS 'JSON 配置结构：{llm:{use_mock,api_url,model_name,timeout}, embedding:{batch_size}, similarity:{threshold_high,topk}, pipeline:{batch_size}, labels:[...]}';
COMMENT ON COLUMN t_system_config.updated_at  IS '最后保存时间';
COMMENT ON COLUMN t_system_config.updated_by  IS '最后保存的用户名';
DO $$ BEGIN RAISE NOTICE '[OK ]  t_system_config'; END $$;


-- ---------------------------------------------------------------------------
-- 3. 角色表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 3/16  t_role ...'; END $$;
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
DO $$ BEGIN RAISE NOTICE '[OK ]  t_role'; END $$;


-- ---------------------------------------------------------------------------
-- 4. 用户表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 4/16  t_user ...'; END $$;
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
DO $$ BEGIN RAISE NOTICE '[OK ]  t_user'; END $$;


-- ---------------------------------------------------------------------------
-- 5. 用户-角色关联表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 5/16  t_user_role ...'; END $$;
CREATE TABLE IF NOT EXISTS t_user_role (
    username   VARCHAR(100) NOT NULL,
    role_name  VARCHAR(50)  NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_user_role PRIMARY KEY (username, role_name)
);
COMMENT ON TABLE  t_user_role            IS '用户与角色的多对多关联（username 逻辑外键）';
COMMENT ON COLUMN t_user_role.username   IS '用户名（逻辑外键 → t_user.username）';
COMMENT ON COLUMN t_user_role.role_name  IS '角色名（逻辑外键 → t_role.name）';
COMMENT ON COLUMN t_user_role.created_at IS '授权时间';
COMMENT ON COLUMN t_user_role.created_by IS '授权操作人';
DO $$ BEGIN RAISE NOTICE '[OK ]  t_user_role'; END $$;


-- ---------------------------------------------------------------------------
-- 6. 数据条目表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 6/16  t_data_item ...'; END $$;
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
COMMENT ON COLUMN t_data_item.status       IS '当前阶段（与 t_data_state.stage 同步）：raw、cleaned、pre_annotated、annotated、checked';
COMMENT ON COLUMN t_data_item.created_at   IS '创建时间';
COMMENT ON COLUMN t_data_item.created_by   IS '创建人';
COMMENT ON COLUMN t_data_item.updated_at   IS '更新时间';
COMMENT ON COLUMN t_data_item.updated_by   IS '最后更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_data_item_hash          ON t_data_item(dataset_id, content_hash);
CREATE        INDEX IF NOT EXISTS idx_t_data_item_dataset_status ON t_data_item(dataset_id, status);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_data_item'; END $$;


-- ---------------------------------------------------------------------------
-- 7. 数据流转状态表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 7/16  t_data_state ...'; END $$;
CREATE TABLE IF NOT EXISTS t_data_state (
    data_id    BIGINT       NOT NULL,
    stage      VARCHAR(50)  NOT NULL DEFAULT 'raw',
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_data_state PRIMARY KEY (data_id)
);
COMMENT ON TABLE  t_data_state            IS '数据流转状态表（控制流，与 t_data_item 一对一）';
COMMENT ON COLUMN t_data_state.data_id    IS '数据ID（逻辑外键 → t_data_item.id）';
COMMENT ON COLUMN t_data_state.stage      IS '当前阶段：raw=原始上传，cleaned=清洗完成，pre_annotated=LLM预标注完成，annotated=人工标注完成，checked=冲突检测通过';
COMMENT ON COLUMN t_data_state.updated_at IS '状态更新时间';
COMMENT ON COLUMN t_data_state.updated_by IS '状态更新操作人';
DO $$ BEGIN RAISE NOTICE '[OK ]  t_data_state'; END $$;


-- ---------------------------------------------------------------------------
-- 8. LLM 预标注表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 8/16  t_pre_annotation ...'; END $$;
CREATE TABLE IF NOT EXISTS t_pre_annotation (
    id         BIGSERIAL    NOT NULL,
    data_id    BIGINT       NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    label      VARCHAR(200) NOT NULL,
    score      NUMERIC(5,4),
    cot        TEXT,
    version    INT          NOT NULL DEFAULT 1,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_pre_annotation PRIMARY KEY (id)
);
COMMENT ON TABLE  t_pre_annotation            IS 'LLM 预标注表';
COMMENT ON COLUMN t_pre_annotation.id         IS '主键ID';
COMMENT ON COLUMN t_pre_annotation.data_id    IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_pre_annotation.model_name IS '模型名称';
COMMENT ON COLUMN t_pre_annotation.label      IS '预测标签';
COMMENT ON COLUMN t_pre_annotation.score      IS '置信度，范围 0~1';
COMMENT ON COLUMN t_pre_annotation.cot        IS 'Chain of Thought 推理过程';
COMMENT ON COLUMN t_pre_annotation.version    IS '版本号，同一数据多次预标注时递增';
COMMENT ON COLUMN t_pre_annotation.created_at IS '创建时间';
COMMENT ON COLUMN t_pre_annotation.created_by IS '触发人（pipeline 操作者）';
CREATE INDEX IF NOT EXISTS idx_t_pre_annotation_data ON t_pre_annotation(data_id);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_pre_annotation'; END $$;


-- ---------------------------------------------------------------------------
-- 9. 人工标注表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 9/16  t_annotation ...'; END $$;
CREATE TABLE IF NOT EXISTS t_annotation (
    id         BIGSERIAL    NOT NULL,
    data_id    BIGINT       NOT NULL,
    username   VARCHAR(100) NOT NULL,
    label      VARCHAR(200) NOT NULL,
    cot           TEXT,
    version       INT          NOT NULL DEFAULT 1,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    category      VARCHAR(200) DEFAULT NULL,
    keywords      VARCHAR(500) DEFAULT NULL,
    keywords_desc TEXT         DEFAULT NULL,
    created_at    TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by    VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_annotation PRIMARY KEY (id)
);
-- 兜底后期新增列：来源 20260508_add_annotation_cot_fields（category/keywords/keywords_desc）。
-- 老库 t_annotation 已存在 → CREATE TABLE 跳过 → 这三列由下方 ALTER 补齐；新库幂等跳过。
ALTER TABLE t_annotation ADD COLUMN IF NOT EXISTS category      VARCHAR(200) DEFAULT NULL;
ALTER TABLE t_annotation ADD COLUMN IF NOT EXISTS keywords      VARCHAR(500) DEFAULT NULL;
ALTER TABLE t_annotation ADD COLUMN IF NOT EXISTS keywords_desc TEXT         DEFAULT NULL;
COMMENT ON TABLE  t_annotation            IS '人工标注表（支持多人标注，每人可多版本）';
COMMENT ON COLUMN t_annotation.id         IS '主键ID';
COMMENT ON COLUMN t_annotation.data_id    IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_annotation.username   IS '标注人用户名（逻辑外键）';
COMMENT ON COLUMN t_annotation.label      IS '标注标签';
COMMENT ON COLUMN t_annotation.cot        IS 'Chain of Thought 标注理由';
COMMENT ON COLUMN t_annotation.version    IS '版本号，同一用户对同一数据多次标注时递增';
COMMENT ON COLUMN t_annotation.is_active  IS '是否为有效版本：TRUE=当前版本，FALSE=历史版本';
COMMENT ON COLUMN t_annotation.category      IS '业务分类名称（来自 t_category.name，标注员点选）';
COMMENT ON COLUMN t_annotation.keywords      IS '关键词（标注员从文本中提取的核心词，逗号分隔或自由输入）';
COMMENT ON COLUMN t_annotation.keywords_desc IS '关键词说明（对关键词的进一步解释，TEXT 类型）';
COMMENT ON COLUMN t_annotation.created_at IS '标注时间';
COMMENT ON COLUMN t_annotation.created_by IS '操作人（通常与 username 相同）';
CREATE INDEX IF NOT EXISTS idx_t_annotation_data   ON t_annotation(data_id);
CREATE INDEX IF NOT EXISTS idx_t_annotation_user   ON t_annotation(data_id, username);
CREATE INDEX IF NOT EXISTS idx_t_annotation_active ON t_annotation(data_id, is_active);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_annotation'; END $$;


-- ---------------------------------------------------------------------------
-- 10. 标注结果汇总表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 10/16 t_annotation_result ...'; END $$;
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
    CONSTRAINT pk_t_annotation_result      PRIMARY KEY (id),
    CONSTRAINT uq_t_annotation_result_data UNIQUE (data_id)
);
COMMENT ON TABLE  t_annotation_result                 IS '标注结果汇总表：每条数据一行，由 t_annotation 写入触发聚合维护';
COMMENT ON COLUMN t_annotation_result.id              IS '主键ID';
COMMENT ON COLUMN t_annotation_result.data_id         IS '数据ID（逻辑外键 → t_data_item.id），全局唯一';
COMMENT ON COLUMN t_annotation_result.dataset_id      IS '数据集ID（冗余，方便按 dataset 聚合查询）';
COMMENT ON COLUMN t_annotation_result.final_label     IS '最终标注标签；无标注时为 NULL';
COMMENT ON COLUMN t_annotation_result.label_source    IS '标签来源：auto=多数投票自动计算，manual=冲突裁决手动设定';
COMMENT ON COLUMN t_annotation_result.annotator_count IS '当前有效标注人数';
COMMENT ON COLUMN t_annotation_result.resolver        IS '冲突裁决人用户名；仅 label_source=manual 时有值';
COMMENT ON COLUMN t_annotation_result.cot             IS '裁决时的 Chain of Thought 理由';
COMMENT ON COLUMN t_annotation_result.updated_at      IS '最后更新时间';
COMMENT ON COLUMN t_annotation_result.updated_by      IS '最后更新操作人';
CREATE INDEX IF NOT EXISTS idx_t_annotation_result_dataset ON t_annotation_result(dataset_id);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_annotation_result'; END $$;


-- ---------------------------------------------------------------------------
-- 11. 数据评论表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 11/16 t_data_comment ...'; END $$;
CREATE TABLE IF NOT EXISTS t_data_comment (
    id         BIGSERIAL    NOT NULL,
    data_id    BIGINT       NOT NULL,
    username   VARCHAR(100) NOT NULL,
    comment    TEXT         NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_data_comment PRIMARY KEY (id)
);
COMMENT ON TABLE  t_data_comment            IS '数据评论表（标注讨论 / 说明原因）';
COMMENT ON COLUMN t_data_comment.id         IS '主键ID';
COMMENT ON COLUMN t_data_comment.data_id    IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_data_comment.username   IS '评论人用户名';
COMMENT ON COLUMN t_data_comment.comment    IS '评论内容';
COMMENT ON COLUMN t_data_comment.created_at IS '评论时间';
COMMENT ON COLUMN t_data_comment.created_by IS '操作人';
CREATE INDEX IF NOT EXISTS idx_t_data_comment_data ON t_data_comment(data_id);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_data_comment'; END $$;


-- ---------------------------------------------------------------------------
-- 12. 冲突检测表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 12/16 t_conflict ...'; END $$;
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
COMMENT ON COLUMN t_conflict.detail        IS '冲突详情 JSON';
COMMENT ON COLUMN t_conflict.status        IS '冲突状态：open=待处理，resolved=已解决';
COMMENT ON COLUMN t_conflict.created_at    IS '创建时间';
COMMENT ON COLUMN t_conflict.created_by    IS '检测触发人';
CREATE INDEX IF NOT EXISTS idx_t_conflict_data   ON t_conflict(data_id);
CREATE INDEX IF NOT EXISTS idx_t_conflict_status ON t_conflict(status);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_conflict'; END $$;


-- ---------------------------------------------------------------------------
-- 13. 导出模板表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 13/16 t_export_template ...'; END $$;
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
DO $$ BEGIN RAISE NOTICE '[OK ]  t_export_template'; END $$;


-- ---------------------------------------------------------------------------
-- 14. Pipeline 运行状态表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 14/16 t_pipeline_status ...'; END $$;
CREATE TABLE IF NOT EXISTS t_pipeline_status (
    dataset_id   BIGINT       NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'idle',
    current_step VARCHAR(50)  NOT NULL DEFAULT '',
    progress     INT          NOT NULL DEFAULT 0,
    detail       JSONB,
    embed_job    JSONB,
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
COMMENT ON COLUMN t_pipeline_status.detail       IS '当前步骤详情';
COMMENT ON COLUMN t_pipeline_status.embed_job    IS '向量化离线任务状态（与主流程解耦，独立写入）';
COMMENT ON COLUMN t_pipeline_status.started_at   IS 'Pipeline 启动时间';
COMMENT ON COLUMN t_pipeline_status.finished_at  IS 'Pipeline 完成或失败时间';
COMMENT ON COLUMN t_pipeline_status.error        IS '失败时的错误信息';
COMMENT ON COLUMN t_pipeline_status.updated_at   IS '最后更新时间';
COMMENT ON COLUMN t_pipeline_status.updated_by   IS '最后更新人';
DO $$ BEGIN RAISE NOTICE '[OK ]  t_pipeline_status'; END $$;


-- ---------------------------------------------------------------------------
-- 15. 数据向量表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 15/16 t_embedding ...'; END $$;
CREATE TABLE IF NOT EXISTS t_embedding (
    id         BIGSERIAL   NOT NULL,
    dataset_id BIGINT      NOT NULL,
    data_id    BIGINT      NOT NULL,
    vector     BYTEA       NOT NULL,
    dim        SMALLINT    NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_t_embedding              PRIMARY KEY (id),
    CONSTRAINT uq_t_embedding_dataset_data UNIQUE (dataset_id, data_id)
);
COMMENT ON TABLE  t_embedding            IS '数据向量表，按 dataset 隔离，BYTEA 存储 numpy float32 数组';
COMMENT ON COLUMN t_embedding.id         IS '主键 ID';
COMMENT ON COLUMN t_embedding.dataset_id IS '所属数据集 ID（逻辑外键 → t_dataset.id）';
COMMENT ON COLUMN t_embedding.data_id    IS '数据条目 ID（逻辑外键 → t_data_item.id）';
COMMENT ON COLUMN t_embedding.vector     IS '向量字节，numpy float32 数组经 ndarray.tobytes() 序列化';
COMMENT ON COLUMN t_embedding.dim        IS '向量维度（float32 元素个数）';
COMMENT ON COLUMN t_embedding.created_at IS '最近一次向量化时间（UPSERT 时刷新）';
CREATE INDEX IF NOT EXISTS idx_t_embedding_dataset ON t_embedding(dataset_id);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_embedding'; END $$;


-- ---------------------------------------------------------------------------
-- 16. 用户-数据集访问权限关联表
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 16/16 t_user_dataset ...'; END $$;
CREATE TABLE IF NOT EXISTS t_user_dataset (
    id         BIGSERIAL    NOT NULL,
    username   VARCHAR(100) NOT NULL,
    dataset_id BIGINT       NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_user_dataset PRIMARY KEY (id),
    CONSTRAINT uq_t_user_dataset UNIQUE (username, dataset_id)
);
COMMENT ON TABLE  t_user_dataset            IS '用户-数据集访问权限关联表';
COMMENT ON COLUMN t_user_dataset.id         IS '主键ID';
COMMENT ON COLUMN t_user_dataset.username   IS '用户名（逻辑外键 → t_user.username）';
COMMENT ON COLUMN t_user_dataset.dataset_id IS '数据集ID（逻辑外键 → t_dataset.id）';
COMMENT ON COLUMN t_user_dataset.created_at IS '分配时间';
COMMENT ON COLUMN t_user_dataset.created_by IS '分配操作人';
CREATE INDEX IF NOT EXISTS idx_t_user_dataset_dataset_id ON t_user_dataset(dataset_id);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_user_dataset'; END $$;


-- ---------------------------------------------------------------------------
-- 17. 标注员工作量明细表（每次操作一行，仅 INSERT；用于 Dashboard 统计）
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 17/17 t_work_volume ...'; END $$;
CREATE TABLE IF NOT EXISTS t_work_volume (
    id          BIGSERIAL    NOT NULL,
    username    VARCHAR(100) NOT NULL,
    dataset_id  BIGINT       NOT NULL,
    data_id     BIGINT       NOT NULL,
    action_type VARCHAR(20)  NOT NULL,
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_work_volume PRIMARY KEY (id)
);
COMMENT ON TABLE  t_work_volume             IS '标注员工作量明细表（每次操作一行，仅 INSERT）';
COMMENT ON COLUMN t_work_volume.id          IS '主键ID';
COMMENT ON COLUMN t_work_volume.username    IS '操作人用户名（逻辑外键 → t_user.username）';
COMMENT ON COLUMN t_work_volume.dataset_id  IS '数据集ID（逻辑外键 → t_dataset.id）';
COMMENT ON COLUMN t_work_volume.data_id     IS '数据ID（逻辑外键 → t_data_item.id）';
COMMENT ON COLUMN t_work_volume.action_type IS '操作类型：annotation=提交标注，conflict_resolve=冲突裁决';
COMMENT ON COLUMN t_work_volume.created_at  IS '操作时间（上海时区）';
COMMENT ON COLUMN t_work_volume.created_by  IS '操作人';
CREATE INDEX IF NOT EXISTS idx_t_work_volume_user_time
    ON t_work_volume (username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_t_work_volume_dataset_time
    ON t_work_volume (dataset_id, created_at DESC);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_work_volume'; END $$;


-- =============================================================================
-- 初始数据（所有 INSERT 均幂等）
-- =============================================================================

DO $$ BEGIN RAISE NOTICE '-----------------------------------------------------------------------'; END $$;
DO $$ BEGIN RAISE NOTICE '[DATA] seed data init ...'; END $$;

-- default roles（四角色；权限集与 core/permissions.py + base.py _PRESET_ROLES 保持同源）
DO $$ BEGIN RAISE NOTICE '[DATA] insert default roles ...'; END $$;
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
DO $$ BEGIN RAISE NOTICE '[OK ]  t_role seed data'; END $$;

-- default dataset (WHERE NOT EXISTS guards against re-run; t_dataset.name has no UNIQUE constraint)
DO $$ BEGIN RAISE NOTICE '[DATA] insert default dataset ...'; END $$;
INSERT INTO t_dataset (name, description, status, created_by, updated_by)
SELECT '默认数据集', '系统初始化创建的默认数据集', 'active', 'system', 'system'
WHERE NOT EXISTS (SELECT 1 FROM t_dataset WHERE name = '默认数据集');
DO $$ BEGIN RAISE NOTICE '[OK ]  t_dataset seed data'; END $$;

-- system config for default dataset
DO $$ BEGIN RAISE NOTICE '[DATA] insert system config for default dataset ...'; END $$;
INSERT INTO t_system_config (dataset_id, config_data, updated_by)
SELECT d.id,
    '{"llm":{"use_mock":true,"api_url":"http://internal-llm-platform/api/v1/chat","model_name":"internal-llm","timeout":30},"embedding":{"batch_size":64},"similarity":{"threshold_high":0.9,"topk":3},"pipeline":{"batch_size":32},"labels":["寿险意图","拒识"]}'::jsonb,
    'system'
FROM t_dataset d WHERE d.name = '默认数据集'
ON CONFLICT (dataset_id) DO NOTHING;
DO $$ BEGIN RAISE NOTICE '[OK ]  t_system_config seed data'; END $$;

-- initial admin user (ON CONFLICT DO NOTHING: re-runs won't overwrite a changed password)
-- NOTE: replace password_hash before running in production:
--       python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt(12)).decode())"
DO $$ BEGIN RAISE NOTICE '[DATA] insert admin user ...'; END $$;
INSERT INTO t_user (username, email, password_hash, is_active, created_by, updated_by)
VALUES ('ADMIN', '', '$2b$12$MZVv1XTKbXGmvK07C3PssON7/c0tey1LQmrtQeGoWj5./gc4KE1gu', TRUE, 'system', 'system')
ON CONFLICT (username) DO NOTHING;

INSERT INTO t_user_role (username, role_name, created_by)
VALUES ('ADMIN', 'admin', 'system')
ON CONFLICT (username, role_name) DO NOTHING;
DO $$ BEGIN RAISE NOTICE '[OK ]  admin user seed data'; END $$;


-- ---------------------------------------------------------------------------
-- 18. t_category -- business category table (per-dataset)
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 18/18 t_category ...'; END $$;
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
CREATE INDEX IF NOT EXISTS idx_t_category_dataset          ON t_category(dataset_id);
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_category_dataset_name ON t_category(dataset_id, name);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_category'; END $$;


-- ---------------------------------------------------------------------------
-- 19. t_eval_task -- AI dialog eval task (independent of dataset)
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 19/20 t_eval_task ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_task (
    id             BIGSERIAL    NOT NULL,
    task_id        VARCHAR(64)  NOT NULL,
    filename       TEXT         NOT NULL DEFAULT '',
    file_path      TEXT         NOT NULL DEFAULT '',
    bu             VARCHAR(64)  NOT NULL DEFAULT '',
    status         VARCHAR(32)  NOT NULL DEFAULT 'pending',
    stage          VARCHAR(64)  NOT NULL DEFAULT '',
    mode           VARCHAR(32)  NOT NULL DEFAULT '',
    progress_done  INTEGER      NOT NULL DEFAULT 0,
    progress_total INTEGER      NOT NULL DEFAULT 0,
    error          TEXT,
    result_json    JSONB,
    claimed_by     VARCHAR(128),
    claimed_at     TIMESTAMP(6),
    heartbeat_at   TIMESTAMP(6),
    started_at     TIMESTAMP(6),
    finished_at    TIMESTAMP(6),
    created_at     TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by     VARCHAR(100) NOT NULL DEFAULT '',
    updated_at     TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by     VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_task PRIMARY KEY (id)
);
-- 兜底后期新增列：老库 t_eval_task 已存在时 CREATE TABLE IF NOT EXISTS 整条跳过，
-- init 之外的增量脚本加的列（claimed_*/started_at）不会补上，紧随其后的 COMMENT 会报错。
-- 这里只对「init 之外新增的列」补 ADD COLUMN IF NOT EXISTS：老库补齐、新库幂等跳过。
-- 来源：20260630_eval_worker_claim（claimed_by/claimed_at/heartbeat_at）、20260704_started_at。
-- 今后再给本表加列，除了写增量脚本，也要在此追加一行。
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS claimed_by   VARCHAR(128);
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS claimed_at   TIMESTAMP(6);
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP(6);
ALTER TABLE t_eval_task ADD COLUMN IF NOT EXISTS started_at   TIMESTAMP(6);
COMMENT ON TABLE  t_eval_task                IS 'AI对话评测任务表（每个评测任务一行）';
COMMENT ON COLUMN t_eval_task.id             IS '主键ID';
COMMENT ON COLUMN t_eval_task.task_id        IS '业务任务ID（uuid截断，对外标识）';
COMMENT ON COLUMN t_eval_task.filename       IS '上传文件名';
COMMENT ON COLUMN t_eval_task.file_path      IS '上传文件存储路径';
COMMENT ON COLUMN t_eval_task.bu             IS '业务单元：securities=证券 / life=寿险';
COMMENT ON COLUMN t_eval_task.status         IS '任务状态：pending=待执行 / running=执行中 / done=完成 / failed=失败';
COMMENT ON COLUMN t_eval_task.stage          IS '执行阶段：loading=加载 / loaded=已加载 / judging=评测中 / advising=出建议 / done=完成';
COMMENT ON COLUMN t_eval_task.mode           IS '评测模式：calibration=校准(有人工金标) / production=生产(无标注)';
COMMENT ON COLUMN t_eval_task.progress_done  IS '已完成样本数';
COMMENT ON COLUMN t_eval_task.progress_total IS '样本总数';
COMMENT ON COLUMN t_eval_task.error          IS '失败原因（status=failed 时有值）';
COMMENT ON COLUMN t_eval_task.result_json    IS '聚合结果（summary/metrics/insights/advice，逐条 rows 在 t_eval_task_row）';
COMMENT ON COLUMN t_eval_task.claimed_by     IS '抢占该任务的worker标识（主机:进程:随机后缀），多POD调度用';
COMMENT ON COLUMN t_eval_task.claimed_at     IS '抢占时间';
COMMENT ON COLUMN t_eval_task.heartbeat_at   IS '最近心跳时间（运行中定期续约，超时视为持有POD已死，任务被回收重抢）';
COMMENT ON COLUMN t_eval_task.started_at     IS '任务真正开跑（pending→running）时间，排队等待不计入，用于统计单次评测耗时';
COMMENT ON COLUMN t_eval_task.finished_at    IS '完成时间';
COMMENT ON COLUMN t_eval_task.created_at     IS '创建时间';
COMMENT ON COLUMN t_eval_task.created_by     IS '创建人';
COMMENT ON COLUMN t_eval_task.updated_at     IS '更新时间';
COMMENT ON COLUMN t_eval_task.updated_by     IS '更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_task_task_id ON t_eval_task(task_id);
CREATE INDEX IF NOT EXISTS idx_t_eval_task_created ON t_eval_task(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_t_eval_task_status_created ON t_eval_task(status, created_at);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_task'; END $$;


-- ---------------------------------------------------------------------------
-- 20. t_eval_task_row -- per-row eval result (resume basis)
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 20/20 t_eval_task_row ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_task_row (
    id            BIGSERIAL    NOT NULL,
    task_id       VARCHAR(64)  NOT NULL,
    row_index     BIGINT       NOT NULL,
    session       VARCHAR(128),
    turn          INTEGER,
    question      TEXT,
    ask_time      VARCHAR(32),
    dispatched_bu VARCHAR(64),
    j_intent      VARCHAR(128),
    j_dispatch    VARCHAR(8),
    j_resolved    VARCHAR(8),
    judge_json    JSONB,
    context_json  JSONB,
    gold_json     JSONB,
    row_json      JSONB        NOT NULL,
    created_at    TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by    VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_task_row PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_task_row               IS 'AI对话评测逐条结果表（每行明细一条，断点续跑依据）';
COMMENT ON COLUMN t_eval_task_row.id            IS '主键ID';
COMMENT ON COLUMN t_eval_task_row.task_id       IS '所属评测任务ID（逻辑外键 → t_eval_task.task_id）';
COMMENT ON COLUMN t_eval_task_row.row_index     IS '行序号（在该任务内唯一）';
COMMENT ON COLUMN t_eval_task_row.session       IS '会话ID（原 Excel 应用会话ID列）';
COMMENT ON COLUMN t_eval_task_row.turn          IS '会话内客户咨询轮次';
COMMENT ON COLUMN t_eval_task_row.question      IS '客户提问原文';
COMMENT ON COLUMN t_eval_task_row.ask_time      IS '客户提问时间原文，问题洞察按日聚合';
COMMENT ON COLUMN t_eval_task_row.dispatched_bu IS 'Excel 分发BU列原值';
COMMENT ON COLUMN t_eval_task_row.j_intent      IS 'AI 判定业务分类';
COMMENT ON COLUMN t_eval_task_row.j_dispatch    IS '分发判定结果：是 / 否';
COMMENT ON COLUMN t_eval_task_row.j_resolved    IS '答案解决判定结果：是 / 否';
COMMENT ON COLUMN t_eval_task_row.judge_json    IS 'LLM 完整判定输出（11 字段）';
COMMENT ON COLUMN t_eval_task_row.context_json  IS '多轮对话上下文 [{turn,user,ai}]';
COMMENT ON COLUMN t_eval_task_row.gold_json     IS '人工金标 dict';
COMMENT ON COLUMN t_eval_task_row.row_json      IS '单行完整评测结果快照（旧行兜底 + 过渡期双写）';
COMMENT ON COLUMN t_eval_task_row.created_at    IS '落盘时间';
COMMENT ON COLUMN t_eval_task_row.created_by    IS '操作人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_task_row_task_idx ON t_eval_task_row(task_id, row_index);
-- 明细页过滤（j_dispatch/j_resolved 按 task）+ 洞察聚合（j_intent/ask_time）走平铺列原生索引
CREATE INDEX IF NOT EXISTS idx_t_eval_row_task_dispatch ON t_eval_task_row (task_id, j_dispatch);
CREATE INDEX IF NOT EXISTS idx_t_eval_row_task_resolved ON t_eval_task_row (task_id, j_resolved);
CREATE INDEX IF NOT EXISTS idx_t_eval_row_j_intent       ON t_eval_task_row (j_intent);
CREATE INDEX IF NOT EXISTS idx_t_eval_row_ask_time       ON t_eval_task_row (ask_time);
-- 需复核筛选走 row_json（查询侧读 row_json['judge']，新旧行 row_json 均完整，双写保证）
CREATE INDEX IF NOT EXISTS idx_t_eval_row_review ON t_eval_task_row (task_id)
    WHERE (row_json->'judge'->>'needs_human_review') = 'true';
-- question 不建索引：可能超长（>2704 B-tree 上限），聚合走 HashAggregate
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_task_row'; END $$;

-- 21. t_eval_prompt -- AI eval editable prompts (DB-backed, hot-editable)
DO $$ BEGIN RAISE NOTICE '[DDL] 21/21 t_eval_prompt ...'; END $$;
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

-- 22. t_eval_category -- AI eval business categories per BU (DB-backed, editable)
DO $$ BEGIN RAISE NOTICE '[DDL] 22/22 t_eval_category ...'; END $$;
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


-- ---------------------------------------------------------------------------
-- 23. t_eval_activity_question -- activity canned questions (skip in eval)
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 23/23 t_eval_activity_question ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_activity_question (
    id          BIGSERIAL    NOT NULL,
    bu          VARCHAR(64)  NOT NULL,
    question    TEXT         NOT NULL,
    note        VARCHAR(255) NOT NULL DEFAULT '',
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by  VARCHAR(100) NOT NULL DEFAULT '',
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by  VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_activity_question PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_activity_question            IS 'AI评测活动标问表（写死按钮触发的写死回复，评测时整条跳过，不计入指标）';
COMMENT ON COLUMN t_eval_activity_question.id         IS '主键ID';
COMMENT ON COLUMN t_eval_activity_question.bu         IS '所属业务单元：securities=证券 / life=寿险';
COMMENT ON COLUMN t_eval_activity_question.question   IS '活动标问全文（与客户问题精确相等即命中，整条跳过评测）';
COMMENT ON COLUMN t_eval_activity_question.note       IS '备注（说明该活动标问的用途，可选）';
COMMENT ON COLUMN t_eval_activity_question.created_at IS '创建时间';
COMMENT ON COLUMN t_eval_activity_question.created_by IS '创建人';
COMMENT ON COLUMN t_eval_activity_question.updated_at IS '更新时间';
COMMENT ON COLUMN t_eval_activity_question.updated_by IS '更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_activity_bu_question ON t_eval_activity_question(bu, question);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_activity_question'; END $$;


-- ---------------------------------------------------------------------------
-- 24. t_eval_review -- manual review override (recompute metrics by final value)
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 24/24 t_eval_review ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_review (
    id                BIGSERIAL    NOT NULL,
    task_id           VARCHAR(64)  NOT NULL,
    row_index         BIGINT       NOT NULL,
    reviewed_dispatch VARCHAR(8)   NOT NULL DEFAULT '',
    reviewed_resolved VARCHAR(8)   NOT NULL DEFAULT '',
    reviewed_intent   VARCHAR(128) NOT NULL DEFAULT '',
    comment           TEXT         NOT NULL DEFAULT '',
    reviewer          VARCHAR(100) NOT NULL DEFAULT '',
    created_at        TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by        VARCHAR(100) NOT NULL DEFAULT '',
    updated_at        TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by        VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_review PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_review                   IS 'AI评测人工复核覆盖表（人工复核结论覆盖AI判定，指标按最终值重算）';
COMMENT ON COLUMN t_eval_review.id                IS '主键ID';
COMMENT ON COLUMN t_eval_review.task_id           IS '所属评测任务ID（逻辑外键 → t_eval_task.task_id）';
COMMENT ON COLUMN t_eval_review.row_index         IS '明细行序号（逻辑外键 → t_eval_task_row.row_index）';
COMMENT ON COLUMN t_eval_review.reviewed_dispatch IS '复核后分发是否正确：是 / 否 / 空（空=该维度不改，沿用AI判定）';
COMMENT ON COLUMN t_eval_review.reviewed_resolved IS '复核后是否解决：是 / 否 / 空（空=不改；仅对实际分到本BU的样本生效）';
COMMENT ON COLUMN t_eval_review.reviewed_intent   IS '复核改的业务分类标签（空=不改）';
COMMENT ON COLUMN t_eval_review.comment           IS '复核评论';
COMMENT ON COLUMN t_eval_review.reviewer          IS '复核人';
COMMENT ON COLUMN t_eval_review.created_at        IS '创建时间';
COMMENT ON COLUMN t_eval_review.created_by        IS '创建人';
COMMENT ON COLUMN t_eval_review.updated_at        IS '更新时间';
COMMENT ON COLUMN t_eval_review.updated_by        IS '更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_review_task_row ON t_eval_review(task_id, row_index);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_review'; END $$;


-- ---------------------------------------------------------------------------
-- 25. t_eval_rule -- rule-based bypass (canned judge result, skip LLM)
-- ---------------------------------------------------------------------------
DO $$ BEGIN RAISE NOTICE '[DDL] 25/25 t_eval_rule ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_rule (
    id              BIGSERIAL    NOT NULL,
    bu              VARCHAR(64)  NOT NULL,
    question        TEXT         NOT NULL,
    expected_answer TEXT         NOT NULL DEFAULT '',
    judge_json      JSONB        NOT NULL,
    note            VARCHAR(255) NOT NULL DEFAULT '',
    created_at      TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by      VARCHAR(100) NOT NULL DEFAULT '',
    updated_at      TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_by      VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_rule PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_rule                 IS 'AI评测规则短路表（命中写死结果、免LLM调用，计入指标）';
COMMENT ON COLUMN t_eval_rule.id              IS '主键ID';
COMMENT ON COLUMN t_eval_rule.bu              IS '所属业务单元：securities=证券 / life=寿险';
COMMENT ON COLUMN t_eval_rule.question        IS '触发问题（与客户问题精确相等即命中）';
COMMENT ON COLUMN t_eval_rule.expected_answer IS '期望答案（须与样本答案一致才命中；防答案已变仍套用写死结论）';
COMMENT ON COLUMN t_eval_rule.judge_json      IS '写死的judge输出（11字段，结构同LLM output，命中即原样产出）';
COMMENT ON COLUMN t_eval_rule.note            IS '备注';
COMMENT ON COLUMN t_eval_rule.created_at      IS '创建时间';
COMMENT ON COLUMN t_eval_rule.created_by      IS '创建人';
COMMENT ON COLUMN t_eval_rule.updated_at      IS '更新时间';
COMMENT ON COLUMN t_eval_rule.updated_by      IS '更新人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_rule_bu_question ON t_eval_rule(bu, question);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_rule'; END $$;

DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[DONE] 20260428_arkpgdata_init.sql done'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

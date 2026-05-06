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
    cot        TEXT,
    version    INT          NOT NULL DEFAULT 1,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(45)  NOT NULL DEFAULT '',
    CONSTRAINT pk_t_annotation PRIMARY KEY (id)
);
COMMENT ON TABLE  t_annotation            IS '人工标注表（支持多人标注，每人可多版本）';
COMMENT ON COLUMN t_annotation.id         IS '主键ID';
COMMENT ON COLUMN t_annotation.data_id    IS '数据ID（逻辑外键）';
COMMENT ON COLUMN t_annotation.username   IS '标注人用户名（逻辑外键）';
COMMENT ON COLUMN t_annotation.label      IS '标注标签';
COMMENT ON COLUMN t_annotation.cot        IS 'Chain of Thought 标注理由';
COMMENT ON COLUMN t_annotation.version    IS '版本号，同一用户对同一数据多次标注时递增';
COMMENT ON COLUMN t_annotation.is_active  IS '是否为有效版本：TRUE=当前版本，FALSE=历史版本';
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

-- default roles
DO $$ BEGIN RAISE NOTICE '[DATA] insert default roles ...'; END $$;
INSERT INTO t_role (name, description, permissions, created_by, updated_by) VALUES
    ('admin',     '超级管理员，拥有所有权限', '["*"]', 'system', 'system'),
    ('annotator', '标注员，可查看数据、提交标注、执行导出',
     '["data:read","annotation:read","annotation:write","pipeline:read","export:read","export:create","config:read"]',
     'system', 'system'),
    ('viewer',    '只读访问，可查看数据和导出结果，不可操作',
     '["data:read","annotation:read","pipeline:read","export:read","config:read"]',
     'system', 'system')
ON CONFLICT (name) DO NOTHING;
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


DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[DONE] 20260428_arkpgdata_init.sql done'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================================='; END $$;

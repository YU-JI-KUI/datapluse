DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260505_arkpgdata_add_work_volume.sql -- 新增标注员工作量明细表 t_work_volume'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;

-- t_work_volume：每次标注 / 裁决操作产生一行（仅 INSERT，不 UPDATE）。
-- 用于 Dashboard 统计每个标注员的今日 / 本周 / 本月工作量。
-- 撤销不写记录；同一人对同一条数据反复修改也算多次 +1。

DO $$ BEGIN RAISE NOTICE '[DDL] 创建 t_work_volume 表 ...'; END $$;
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

DO $$ BEGIN RAISE NOTICE '[DONE] 20260505_arkpgdata_add_work_volume.sql 执行完成'; END $$;

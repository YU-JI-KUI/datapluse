DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;
DO $$ BEGIN RAISE NOTICE '[SCRIPT] 20260717_arkpgdata_eval_task_file.sql -- eval task multi-file subtable'; END $$;
DO $$ BEGIN RAISE NOTICE '======================================================='; END $$;

-- ---------------------------------------------------------------------------
-- Why: 运营平台单文件上限 5 万行，超出会拆成多个 Excel。评测需支持多个文件合并成
--      一个 task（跨文件按 session 拼多轮、按 ask_date 分日）。t_eval_task 原本单值
--      filename/file_path 存不下多文件，新增子表一文件一行；file_index 也给 row_index
--      分段提供依据（row_index = file_index * 10_000_000 + 文件内行号）。
-- ---------------------------------------------------------------------------

DO $$ BEGIN RAISE NOTICE '[DDL] create t_eval_task_file ...'; END $$;
CREATE TABLE IF NOT EXISTS t_eval_task_file (
    id         BIGSERIAL    NOT NULL,
    task_id    VARCHAR(64)  NOT NULL,
    file_index INTEGER      NOT NULL DEFAULT 0,
    filename   TEXT         NOT NULL DEFAULT '',
    file_path  TEXT         NOT NULL DEFAULT '',
    rows       INTEGER      NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by VARCHAR(100) NOT NULL DEFAULT '',
    CONSTRAINT pk_t_eval_task_file PRIMARY KEY (id)
);
COMMENT ON TABLE  t_eval_task_file            IS 'AI评测任务的文件清单（一个任务可含多个上传文件，合并评测）';
COMMENT ON COLUMN t_eval_task_file.id         IS '主键ID';
COMMENT ON COLUMN t_eval_task_file.task_id    IS '所属评测任务ID（逻辑外键 → t_eval_task.task_id）';
COMMENT ON COLUMN t_eval_task_file.file_index IS '文件在任务内的序号（0起），row_index 分段依据';
COMMENT ON COLUMN t_eval_task_file.filename   IS '上传文件名';
COMMENT ON COLUMN t_eval_task_file.file_path  IS '文件存储路径';
COMMENT ON COLUMN t_eval_task_file.rows       IS '该文件行数（读取后回填，仅供展示）';
COMMENT ON COLUMN t_eval_task_file.created_at IS '创建时间';
COMMENT ON COLUMN t_eval_task_file.created_by IS '操作人';
CREATE UNIQUE INDEX IF NOT EXISTS uk_t_eval_task_file_task_idx ON t_eval_task_file(task_id, file_index);
DO $$ BEGIN RAISE NOTICE '[OK ]  t_eval_task_file'; END $$;

-- 老库回填：已有 task 的单文件补进子表 file_index=0，让新读取逻辑对旧任务也生效。
DO $$ BEGIN RAISE NOTICE '[DATA] backfill existing single-file tasks into subtable ...'; END $$;
INSERT INTO t_eval_task_file (task_id, file_index, filename, file_path, rows, created_at, created_by)
SELECT t.task_id, 0, t.filename, t.file_path, 0, t.created_at, t.created_by
FROM t_eval_task t
WHERE t.file_path <> ''
  AND NOT EXISTS (SELECT 1 FROM t_eval_task_file f WHERE f.task_id = t.task_id);
DO $$ BEGIN RAISE NOTICE '[OK ]  backfill done'; END $$;

DO $$ BEGIN RAISE NOTICE '[DONE] 20260717_arkpgdata_eval_task_file.sql complete'; END $$;

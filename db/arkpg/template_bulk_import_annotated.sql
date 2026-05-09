-- ============================================================
-- 批量导入已标注数据模板（直接写入 annotated 状态）
--
-- 支持同一文本多标注员：
--   同一 content 的多行 → 1 data_item + 1 data_state + N t_annotation
--   t_annotation_result 取该 content 中 rn 最大的那行（即 VALUES 最后一行）
--
-- 列说明：
--   rn            — 行号（同一 content 内从 1 递增，rn 最大的行作为最终结果）
--   content       — 文本内容
--   label         — 标注标签
--   category      — 业务分类（可为 NULL）
--   keywords      — 关键词（可为 NULL）
--   keywords_desc — 关键词说明（可为 NULL）
--   annotator     — 标注员用户名
--   cot           — 推理链文本（可为 NULL；若填写则原样写入）
--
-- 使用方式：
--   1. 替换 <DATASET_ID> 为目标数据集 ID（共 2 处）
--   2. 在 input_data CTE 中填入实际数据行（rn 从 1 递增）
--   3. 如需写入批次备注，将 Step 5 中的 '批量标注导入' 替换为实际内容；
--      不需要备注则注释掉 Step 5 的 INSERT，并将 inserted_results 改为最终语句
--   4. 通过 psql 执行：
--        psql -h <host> -U <user> -d arkpg -f template_bulk_import_annotated.sql
--      若粘贴到 SQL 工具（AdminSQL 页面），删去首尾的 BEGIN / COMMIT 再执行
-- ============================================================

BEGIN;

WITH input_data (rn, content, label, category, keywords, keywords_desc, annotator, cot) AS (
  VALUES
    -- 格式：(行号, '文本内容', '标注标签', '业务分类', '关键词', '关键词说明', '标注员', 'COT')
    (1, '退保能退多少钱',   '寿险意图', '退保咨询', '退保金额', '用户咨询退保时可以取回的金额',   'annotator01', '退保金额｜用户咨询退保时可以取回的金额｜寿险意图｜退保咨询'),
    (2, '退保能退多少钱',   '拒识',     NULL,       NULL,       NULL,                             'annotator02', NULL),
    (3, '如何办理理赔手续', '寿险意图', '理赔流程', '理赔办理', '用户询问理赔申请的具体操作步骤', 'annotator01', '理赔办理｜用户询问理赔申请的具体操作步骤｜寿险意图｜理赔流程')
),

-- ── 辅助 CTE ─────────────────────────────────────────────────────────────────

-- 每条 content 取 rn 最小的行，用于写数据条目 / 状态（只需一行代表方）
first_per_content AS (
  SELECT DISTINCT ON (content) *
  FROM input_data
  ORDER BY content, rn
),

-- 每条 content 取 rn 最大的行，作为最终标注结果
last_per_content AS (
  SELECT DISTINCT ON (content) *
  FROM input_data
  ORDER BY content, rn DESC
),

-- 每条 content 的标注员总数（写入 annotator_count）
annotator_counts AS (
  SELECT content, COUNT(*)::int AS cnt
  FROM input_data
  GROUP BY content
),

-- ── Step 1: 写入数据条目（每条 content 唯一）────────────────────────────────
-- 用 DO UPDATE 而非 DO NOTHING，确保已存在时 RETURNING 仍能返回 id
inserted_items AS (
  INSERT INTO t_data_item (dataset_id, content, content_hash, source, source_ref, status, created_at, created_by, updated_at, updated_by)
  SELECT
    <DATASET_ID>                                    AS dataset_id,
    f.content,
    encode(sha256(f.content::bytea), 'hex')         AS content_hash,
    'manual'                                        AS source,
    '批量标注导入'                                  AS source_ref,
    'annotated'                                     AS status,
    NOW()                                           AS created_at,
    f.annotator                                     AS created_by,
    NOW()                                           AS updated_at,
    f.annotator                                     AS updated_by
  FROM first_per_content f
  ON CONFLICT (dataset_id, content_hash) DO UPDATE
    SET updated_at = EXCLUDED.updated_at    -- 触发 RETURNING，不改变实质数据
  RETURNING id, content
),

-- ── Step 2: 写入数据状态（每条 content 唯一）────────────────────────────────
inserted_states AS (
  INSERT INTO t_data_state (data_id, stage, updated_at, updated_by)
  SELECT
    i.id,
    'annotated',
    NOW(),
    f.annotator
  FROM inserted_items i
  JOIN first_per_content f ON f.content = i.content
  ON CONFLICT (data_id) DO UPDATE
    SET stage      = 'annotated',
        updated_at = NOW(),
        updated_by = EXCLUDED.updated_by
  RETURNING data_id
),

-- ── Step 3: 写入标注记录（每个标注员一行，全量 JOIN）────────────────────────
inserted_annotations AS (
  INSERT INTO t_annotation (data_id, username, label, cot, category, keywords, keywords_desc, version, is_active, created_at, created_by)
  SELECT
    i.id,
    d.annotator,
    d.label,
    d.cot,
    d.category,
    d.keywords,
    d.keywords_desc,
    1             AS version,
    TRUE          AS is_active,
    NOW()         AS created_at,
    d.annotator   AS created_by
  FROM inserted_items i
  -- 用全量 input_data JOIN，同一 content 的每个标注员都插入一行
  JOIN input_data d ON d.content = i.content
  RETURNING id, data_id
),

-- ── Step 4: 写入最终标注结果（每条 content 唯一，取 rn 最大行）──────────────
inserted_results AS (
  INSERT INTO t_annotation_result (data_id, dataset_id, final_label, label_source, annotator_count, resolver, cot, updated_at, updated_by)
  SELECT
    i.id,
    <DATASET_ID>        AS dataset_id,
    l.label             AS final_label,
    'manual'            AS label_source,
    ac.cnt              AS annotator_count,
    l.annotator         AS resolver,
    l.cot,
    NOW()               AS updated_at,
    l.annotator         AS updated_by
  FROM inserted_items i
  JOIN last_per_content  l  ON l.content  = i.content
  JOIN annotator_counts  ac ON ac.content = i.content
  ON CONFLICT (data_id) DO UPDATE
    SET final_label     = EXCLUDED.final_label,
        label_source    = 'manual',
        annotator_count = EXCLUDED.annotator_count,
        resolver        = EXCLUDED.resolver,
        cot             = EXCLUDED.cot,
        updated_at      = NOW(),
        updated_by      = EXCLUDED.updated_by
  RETURNING data_id
)

-- ── Step 5: 写入数据备注（可选）────────────────────────────────────────────
-- 自动生成备注格式：2026-05-09 14:30 annotator01 导入了「退保能退多少钱」，标签：寿险意图
-- 若不需要备注，注释掉此 INSERT 并将上方 inserted_results CTE 改为最终语句
INSERT INTO t_data_comment (data_id, username, comment, created_at, created_by)
SELECT
  i.id,
  f.annotator,
  to_char(NOW(), 'YYYY-MM-DD HH24:MI') || ' '
    || f.annotator || ' 导入了「'
    || i.content   || '」，标签：'
    || l.label     AS comment,
  NOW(),
  f.annotator
FROM inserted_items i
JOIN first_per_content f ON f.content = i.content
JOIN last_per_content  l ON l.content = i.content;

COMMIT;

-- ============================================================
-- 执行后验证（复制此块单独运行）：
-- SELECT
--   i.id, i.content, i.status,
--   ar.final_label, ar.label_source, ar.resolver, ar.annotator_count,
--   (SELECT COUNT(*) FROM t_annotation  a WHERE a.data_id = i.id AND a.is_active)  AS ann_count,
--   (SELECT COUNT(*) FROM t_data_comment c WHERE c.data_id = i.id)                  AS comment_count
-- FROM t_data_item i
-- JOIN t_annotation_result ar ON ar.data_id = i.id
-- WHERE i.dataset_id = <DATASET_ID>
-- ORDER BY i.created_at DESC LIMIT 20;
-- ============================================================

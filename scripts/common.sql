drop table if exists t_dataset;
drop table if exists t_system_config;
drop table if exists t_role;
drop table if exists t_user;
drop table if exists t_user_role;
drop table if exists t_user_dataset;
drop table if exists t_data_item;
drop table if exists t_data_state;
drop table if exists t_pre_annotation;
drop table if exists t_annotation_result;
drop table if exists t_annotation;
drop table if exists t_data_comment;
drop table if exists t_conflict;
drop table if exists t_export_template;
drop table if exists t_pipeline_status;

SELECT * FROM pg_tables WHERE schemaname = 'public';


-- =============================================================================
-- 查询：指定 dataset 下，每个用户问的「最终标签」+ 每个标注员给的「业务分类/关键词/关键词说明」
-- 用法：把 :dataset_id 替换为目标数据集 ID。
--
-- 字段来源：
--   用户问        t_data_item.content
--   最终标签      t_annotation_result.final_label（多数投票 auto / 冲突裁决 manual）
--   标注员        t_annotation.username（仅当前有效版本 is_active=TRUE）
--   业务分类      t_annotation.category
--   关键词        t_annotation.keywords
--   关键词说明    t_annotation.keywords_desc
--
-- 说明：一条数据可能有多个标注员 → 一对多，故每个标注员一行；用 LEFT JOIN，
--       即使某条数据尚无人标注，也能看到用户问 + 最终标签（标注列为 NULL）。
-- =============================================================================
SELECT
    di.id                         AS data_id,
    di.content                    AS 用户问,
    ar.final_label                AS 最终标签,
    ar.label_source               AS 标签来源,   -- auto=多数投票 / manual=冲突裁决
    a.username                    AS 标注员,
    a.category                    AS 业务分类,
    a.keywords                    AS 关键词,
    a.keywords_desc               AS 关键词说明,
    a.label                       AS 该标注员标签,
    a.created_at                  AS 标注时间
FROM t_data_item di
LEFT JOIN t_annotation_result ar
       ON ar.data_id = di.id
LEFT JOIN t_annotation a
       ON a.data_id = di.id
      AND a.is_active = TRUE
WHERE di.dataset_id = :dataset_id
ORDER BY di.id, a.username;


-- =============================================================================
-- 增强版：按「业务分类」聚合关键词说明 + 频次（提炼业务规则的原材料）
-- 把同一业务分类下所有标注员写的「关键词说明」聚到一起、去重计数，
-- 便于后续（人工或 LLM）从个案说明归纳出少量通用规则。
-- 用法：替换 :dataset_id。
-- =============================================================================

-- A) 概览：每个业务分类有多少条标注、多少条填了关键词说明
SELECT
    a.category                                   AS 业务分类,
    COUNT(*)                                     AS 标注条数,
    COUNT(a.keywords_desc) FILTER (WHERE TRIM(COALESCE(a.keywords_desc,'')) <> '') AS 有说明条数,
    COUNT(DISTINCT a.username)                   AS 标注员数
FROM t_annotation a
JOIN t_data_item di ON di.id = a.data_id
WHERE di.dataset_id = :dataset_id
  AND a.is_active = TRUE
  AND TRIM(COALESCE(a.category,'')) <> ''
GROUP BY a.category
ORDER BY 标注条数 DESC;


-- B) 明细：每个业务分类下，去重后的关键词说明及出现频次（同一说明多人写→合并计数）
SELECT
    a.category                                   AS 业务分类,
    TRIM(a.keywords_desc)                        AS 关键词说明,
    COUNT(*)                                     AS 出现次数,
    STRING_AGG(DISTINCT a.keywords, ' | ')       AS 关联关键词
FROM t_annotation a
JOIN t_data_item di ON di.id = a.data_id
WHERE di.dataset_id = :dataset_id
  AND a.is_active = TRUE
  AND TRIM(COALESCE(a.category,'')) <> ''
  AND TRIM(COALESCE(a.keywords_desc,'')) <> ''
GROUP BY a.category, TRIM(a.keywords_desc)
ORDER BY a.category, 出现次数 DESC;

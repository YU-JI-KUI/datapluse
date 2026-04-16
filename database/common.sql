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

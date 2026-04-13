drop table if exists t_dataset;
drop table if exists t_system_config;
drop table if exists t_role;
drop table if exists t_user;
drop table if exists t_user_role;
drop table if exists t_data_item;
drop table if exists t_data_state;
drop table if exists t_pre_annotation;
drop table if exists t_annotation;
drop table if exists t_data_comment;
drop table if exists t_conflict;
drop table if exists t_export_template;
drop table if exists t_pipeline_status;

SELECT * FROM pg_tables WHERE schemaname = 'public';

drop table if exists datasets;
drop table if exists system_config;
drop table if exists roles;
drop table if exists users;
drop table if exists user_roles;
drop table if exists data_items;
drop table if exists export_templates;
drop table if exists pipeline_status;



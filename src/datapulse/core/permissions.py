"""权限清单唯一真相源。

权限跟着代码接口走（接口在哪、权限在哪），因此以代码常量而非 DB 表维护。
每项含 code / module / label：module 供前端按模块分组渲染成两级树，label 是中文说明。
角色的权限集存在 t_role.permissions（JSONB 字符串数组），admin 存 ["*"] 通配全部。
"""

from __future__ import annotations

# (code, module, label) —— 顺序即前端展示顺序
PERMISSIONS: list[dict[str, str]] = [
    {"code": "data:read",           "module": "数据",     "label": "查看数据列表/详情/统计"},
    {"code": "data:write",          "module": "数据",     "label": "手动录入/上传数据文件"},
    {"code": "data:delete",         "module": "数据",     "label": "删除数据（单删/批量/按来源）"},
    {"code": "annotation:read",     "module": "标注",     "label": "查看标注结果/历史"},
    {"code": "annotation:write",    "module": "标注",     "label": "提交/撤销标注"},
    {"code": "conflict:read",       "module": "冲突",     "label": "查看冲突列表"},
    {"code": "conflict:detect",     "module": "冲突",     "label": "触发冲突检测/自检"},
    {"code": "conflict:resolve",    "module": "冲突",     "label": "裁决冲突（单条/批量）"},
    {"code": "category:read",       "module": "分类",     "label": "查看业务分类"},
    {"code": "category:write",      "module": "分类",     "label": "增删改分类/批量导入"},
    {"code": "comment:write",       "module": "评论",     "label": "发表/删除评论"},
    {"code": "pre_annotation:run",  "module": "预标注",   "label": "触发 LLM 预标注"},
    {"code": "pipeline:read",       "module": "Pipeline", "label": "查看 Pipeline 状态/步骤"},
    {"code": "pipeline:run",        "module": "Pipeline", "label": "运行 Pipeline/Embedding/重置"},
    {"code": "export:read",         "module": "导出",     "label": "查看导出字段/模板"},
    {"code": "export:create",       "module": "导出",     "label": "生成/下载导出文件"},
    {"code": "template:write",      "module": "导出",     "label": "增删改导出模板"},
    {"code": "config:read",         "module": "配置",     "label": "查看数据集配置"},
    {"code": "config:write",        "module": "配置",     "label": "改配置/重建索引/重载模型"},
    {"code": "eval:read",           "module": "AI评测",   "label": "查看评测任务/结果/明细"},
    {"code": "eval:write",          "module": "AI评测",   "label": "创建/重跑/删任务/改提示词"},
    {"code": "user:manage",         "module": "用户管理", "label": "用户增删改/重置密码"},
    {"code": "dataset:manage",      "module": "数据集",   "label": "数据集增删改/分配用户"},
    {"code": "role:manage",         "module": "角色权限", "label": "修改角色权限"},
    {"code": "system:sql",          "module": "系统",     "label": "执行任意 SQL"},
]

# 合法权限 code 集合，供改角色权限时校验入参
ALL_CODES: frozenset[str] = frozenset(p["code"] for p in PERMISSIONS)


def grouped_permissions() -> list[dict]:
    """按 module 分组，前端渲染两级树用。保持 PERMISSIONS 的原始顺序。"""
    groups: list[dict] = []
    index: dict[str, dict] = {}
    for p in PERMISSIONS:
        g = index.get(p["module"])
        if g is None:
            g = {"module": p["module"], "permissions": []}
            index[p["module"]] = g
            groups.append(g)
        g["permissions"].append({"code": p["code"], "label": p["label"]})
    return groups

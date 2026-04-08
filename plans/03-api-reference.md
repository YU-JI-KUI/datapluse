# API 路由速查

Base URL: `http://localhost:8000/api`
交互文档: `http://localhost:8000/api/docs`（Swagger UI）

所有需要认证的接口须携带：`Authorization: Bearer <token>`

**dataset_id 参数**：数据管理、Pipeline、标注、配置等接口均要求传 `?dataset_id=xxx` query 参数，默认使用 `default`。

---

## Auth `/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/auth/login` | 表单登录，返回 JWT token |
| `GET`  | `/auth/me`    | 查询当前用户信息 |

**登录请求**（`application/x-www-form-urlencoded`）：
```
username=admin&password=your_password
```

**登录响应**：
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "username": "admin",
  "roles": ["admin"]
}
```

---

## 数据集 `/datasets`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `GET`    | `/datasets`        | 登录即可 | 获取所有数据集 |
| `GET`    | `/datasets/{id}`   | 登录即可 | 获取单个数据集 |
| `POST`   | `/datasets`        | admin | 创建数据集 |
| `PUT`    | `/datasets/{id}`   | admin | 更新数据集 |
| `DELETE` | `/datasets/{id}`   | admin | 删除数据集 |

---

## 用户管理 `/users`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `GET`    | `/users`                     | admin | 获取用户列表 |
| `POST`   | `/users`                     | admin | 创建用户 |
| `PUT`    | `/users/{id}`                | admin | 更新用户（角色/状态/显示名） |
| `DELETE` | `/users/{id}`                | admin | 删除用户（不能删自己） |
| `GET`    | `/users/roles`               | 登录即可 | 获取所有角色列表 |
| `POST`   | `/users/{id}/reset-password` | admin | 重置用户密码 |

**创建用户请求体**：
```json
{
  "username": "user1",
  "password": "plaintext_password",
  "display_name": "标注员一",
  "role_name": "annotator",
  "is_active": true
}
```

---

## 数据管理 `/data`

所有接口需要 `?dataset_id=xxx`。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST`   | `/data/upload?dataset_id=xxx`         | 上传文件（xlsx/json/csv），multipart/form-data |
| `GET`    | `/data/list?dataset_id=xxx`           | 分页查询，支持 `&status=raw&page=1&page_size=20` |
| `GET`    | `/data/stats?dataset_id=xxx`          | 各状态数量统计 |
| `GET`    | `/data/{id}`                          | 查询单条 |
| `DELETE` | `/data/{id}`                          | 删除单条（同时删除 embedding） |

**stats 响应示例**：
```json
{"total": 500, "raw": 0, "processed": 0, "pre_annotated": 200, "labeled": 280, "checked": 20}
```

---

## Pipeline `/pipeline`

所有接口需要传 `dataset_id`（run/run-step 在 body，status 在 query）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/pipeline/run`        | 全量运行（后台异步），409 if already running |
| `POST` | `/pipeline/run-step`   | 单步运行（同步），body: `{"dataset_id": "xxx", "step": "process"}` |
| `GET`  | `/pipeline/status?dataset_id=xxx` | 查询当前状态 |
| `GET`  | `/pipeline/steps`      | 返回所有步骤名 |

---

## 标注 `/annotation`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET`  | `/annotation/queue?dataset_id=xxx`     | 待标注列表 |
| `GET`  | `/annotation/next?dataset_id=xxx`      | 取下一条（改为 labeling 状态） |
| `POST` | `/annotation/submit`                   | body: `{"item_id": "...", "label": "寿险意图"}` |
| `POST` | `/annotation/batch-submit`             | 批量提交 |
| `GET`  | `/annotation/labeled?dataset_id=xxx`   | 已标注历史 |

---

## 配置中心 `/config`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `GET`  | `/config?dataset_id=xxx`                | 登录即可 | 返回完整配置（密码脱敏） |
| `POST` | `/config/update?dataset_id=xxx`         | config:write | 更新配置，body: `{"config": {...}}` |
| `POST` | `/config/reload-model`                  | config:write | 重载 embedding 模型 |
| `POST` | `/config/rebuild-index`                 | config:write | 重建 FAISS 向量索引 |

---

## 导出 `/export`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/export/create` | 生成导出，body: `{"dataset_id": "xxx", "format": "json", "status_filter": "checked", "template_id": null}` |
| `GET`  | `/export/fields?dataset_id=xxx` | 可用字段列表 |

---

## 导出模板 `/templates`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET`    | `/templates?dataset_id=xxx` | 获取模板列表 |
| `GET`    | `/templates/{id}`           | 获取单个模板 |
| `POST`   | `/templates`                | 创建模板，body 含 `dataset_id` |
| `PUT`    | `/templates/{id}`           | 更新模板 |
| `DELETE` | `/templates/{id}`           | 删除模板 |

---

## Health Check

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 返回 `{"status": "ok", "version": "0.5.0"}` |

---

## 通用响应格式

**错误**（FastAPI 标准）：
```json
{"detail": "错误描述"}
```

**401 未认证**：axios interceptor 自动跳转到 `/login`
**403 无权限**：返回 403 Forbidden

# API 路由速查

Base URL: `http://localhost:8000/api`
交互文档: `http://localhost:8000/api/docs`（Swagger UI）

所有需要认证的接口须携带：`Authorization: Bearer <token>`

---

## Auth

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/auth/login` | 表单登录，返回 JWT token |
| `GET`  | `/auth/me`    | 查询当前用户信息 |

**登录请求**（`application/x-www-form-urlencoded`）：
```
username=admin&password=datapluse2024
```

**登录响应**：
```json
{"access_token": "eyJ...", "token_type": "bearer", "username": "admin"}
```

---

## 数据管理 `/data`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST`   | `/data/upload`        | 上传文件（xlsx/json/csv），multipart/form-data |
| `GET`    | `/data/list`          | 分页查询，支持 `?status=raw&page=1&page_size=20` |
| `GET`    | `/data/stats`         | 各状态数量统计 |
| `GET`    | `/data/{id}`          | 查询单条 |
| `DELETE` | `/data/{id}`          | 删除单条（同时删除 embedding） |

**stats 响应示例**：
```json
{"total": 500, "raw": 0, "processed": 0, "pre_annotated": 200, "labeled": 280, "checked": 20}
```

---

## Pipeline `/pipeline`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/pipeline/run`        | 全量运行（后台异步），409 if already running |
| `POST` | `/pipeline/run-step`   | 单步运行（同步），body: `{"step": "process"}` |
| `GET`  | `/pipeline/status`     | 查询当前状态 |
| `GET`  | `/pipeline/steps`      | 返回所有步骤名 `["process", "pre_annotate", "embed", "check"]` |

---

## 标注 `/annotation`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET`  | `/annotation/queue`        | 待标注列表（pre_annotated 状态） |
| `GET`  | `/annotation/next`         | 取下一条（自动改为 labeling 状态） |
| `POST` | `/annotation/submit`       | 提交单条：`{"item_id": "...", "label": "寿险意图"}` |
| `POST` | `/annotation/batch-submit` | 批量提交 |
| `GET`  | `/annotation/labeled`      | 已标注历史 |

---

## 配置中心 `/config`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET`  | `/config`                | 返回完整配置（密码脱敏） |
| `POST` | `/config/update`         | 更新配置，body: `{"config": {...}}` |
| `POST` | `/config/reload-model`   | 重载 embedding 模型（改 model_path 后调用） |
| `POST` | `/config/rebuild-index`  | 从 NAS 重建 FAISS 向量索引 |

---

## 导出 `/export`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/export/create`            | 生成导出，body: `{"format": "json", "status_filter": "checked"}` |
| `GET`  | `/export/list`              | 已导出文件列表 |
| `GET`  | `/export/download/{filename}` | 下载文件（流式返回） |

---

## 通用响应格式

**成功**：
```json
{"success": true, "data": {...}}
```

**错误**（FastAPI 标准）：
```json
{"detail": "错误描述"}
```

**401 未认证**：axios interceptor 自动跳转到 `/login`

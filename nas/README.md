# NAS 目录说明

本目录是 Datapluse 的数据存储根目录，**所有数据均以 JSON 文件形式存储，无数据库依赖**。

---

## 目录结构

```
nas/
├── raw/               ← 原始上传数据（入口）
├── processed/         ← 清洗后的数据
├── pre_annotated/     ← LLM 预标注完成
├── labeling/          ← 标注中（翻牌式标注时临时占用）
├── labeled/           ← 人工标注完成
├── checked/           ← 冲突检测通过，可导出
├── embeddings/        ← 向量文件（{item_id}.npy）
├── vector_index/      ← FAISS 索引文件
├── export/            ← 导出文件（.json / .xlsx）
└── _manifest.json     ← 内存索引快照（系统自动维护）
```

**数据流向**：`raw → processed → pre_annotated → labeled → checked`

---

## 每条数据的格式

每个 `{uuid}.json` 文件对应一条数据，完整字段如下：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "text": "用户输入的原始文本",
  "status": "raw",
  "label": null,
  "model_pred": null,
  "model_score": null,
  "annotator": null,
  "annotated_at": null,
  "conflict_flag": false,
  "conflict_type": null,
  "conflict_detail": null,
  "source_file": "upload_20240407.xlsx",
  "created_at": "2024-04-07 10:00:00",
  "updated_at": "2024-04-07 10:00:00"
}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `id` | UUID，全局唯一 |
| `text` | 原始文本（清洗前后均保存这里） |
| `status` | 当前所在阶段，见上方目录结构 |
| `label` | 人工标注的标签（标注完成后填充） |
| `model_pred` | LLM 预测标签 |
| `model_score` | LLM 预测置信度（0~1） |
| `annotator` | 标注人员用户名 |
| `annotated_at` | 标注时间（上海时区，格式 yyyy-mm-dd HH:mm:ss） |
| `conflict_flag` | 是否存在标注冲突 |
| `conflict_type` | 冲突类型：`label_conflict` 或 `semantic_conflict` |
| `conflict_detail` | 冲突详情（JSON 对象） |
| `source_file` | 来源文件名 |
| `created_at` | 创建时间（上海时区） |
| `updated_at` | 最后更新时间（上海时区） |

---

## 如何准备数据

### 方式一：通过 Web 界面上传（推荐）

进入「数据管理」页面，支持拖拽上传以下格式：

- **Excel（.xlsx）**：需包含 `text` 列（或 `文本` / `query` / `问题` 列），每行一条数据
- **JSON（.json）**：支持三种格式（见下方示例）
- **CSV（.csv）**：第一列视为文本列

### 方式二：直接放入 raw/ 目录

如果数据量极大，可直接将已经格式化的 JSON 文件放入 `nas/raw/` 目录，然后重启服务，系统会自动扫描并建立索引。

每个文件内容格式（二选一）：

```json
// 格式 A：字符串数组
["用户问题1", "用户问题2", "用户问题3"]

// 格式 B：对象数组
[
  {"text": "用户问题1"},
  {"text": "用户问题2"}
]
```

---

## 示例数据

`raw/example_insurance_queries.json` 提供了 15 条保险领域的意图识别示例数据，覆盖：

- 产品咨询（万能险、重疾险、年金险等）
- 理赔咨询
- 投保咨询
- 续保咨询

可以直接通过 Web 界面上传此文件，或运行 Pipeline 体验完整流程。

---

## 标签（Intent Labels）

默认标签在 `config.yaml` 的 `labels` 字段配置，例如：

```yaml
labels:
  - 产品咨询
  - 理赔咨询
  - 投保咨询
  - 续保咨询
  - 其他
```

根据你的业务场景自由修改。

---

## 注意事项

- `_manifest.json` 由系统自动维护，**请勿手动编辑**。如果损坏，删除后重启服务会自动重建。
- `nas/` 下的实际数据文件（`.json`、`.npy`）已加入 `.gitignore`，不会提交到 Git。
- 只有 `raw/example_*.json` 和各目录的 `.gitkeep` 会入库，作为初始化模板。

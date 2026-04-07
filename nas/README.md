# nas/ 目录说明

`nas/` 目录从 v0.4.0 起**只用于存放本地向量文件**。

所有业务数据（文本、标注、状态、冲突信息）均已迁移至 PostgreSQL，不再以 JSON 文件形式存放在 nas/ 中。

---

## 目录结构

```
nas/
├── embeddings/          # 向量文件（{item_id}.npy），每条数据对应一个文件
├── vector_index/        # FAISS 索引文件（faiss.index + ids.json）
└── raw/
    └── example_insurance_queries.json  # 保险意图示例数据，可通过 Web 界面上传
```

## 为什么向量文件不入库

FAISS 索引和 numpy 向量必须以本地文件形式加载，无法存储在关系型数据库中。因此向量文件保留在本地，由 `backend/storage/embeddings.py` 的 `EmbeddingStore` 统一管理。

## 示例数据

`raw/example_insurance_queries.json` 包含 15 条保险领域意图识别示例，覆盖：产品咨询、理赔咨询、投保咨询、续保咨询等场景。

可以通过「数据管理」页面直接上传此文件，然后运行 Pipeline 体验完整流程。

## 注意事项

- `embeddings/` 和 `vector_index/` 下的文件已加入 `.gitignore`，不会提交到 Git。
- 这两个目录会在首次运行 Pipeline embed 步骤时自动创建。
- 如需重建向量索引，删除 `vector_index/` 下的文件后重跑 Pipeline embed 步骤即可。

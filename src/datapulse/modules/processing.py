"""
数据处理模块：文本清洗 + 文件解析
支持 Excel / JSON / CSV 上传
字段命名：content（对应 t_data_item.content）

parse_file      — 返回 list[str]，纯文本模式（向后兼容）
parse_file_rows — 返回 list[dict]，含 content + label（可选），用于带标注的历史数据上传
"""

from __future__ import annotations

import io
import json
import re
from typing import Any

import pandas as pd


# ── 文本清洗 ───────────────────────────────────────────────────────────────


def clean_text(text: str) -> str:
    """基础文本清洗"""
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


def is_valid(text: str, min_len: int = 2, max_len: int = 512) -> bool:
    """过滤无效文本"""
    if not text or not text.strip():
        return False
    return min_len <= len(text) <= max_len


# ── 纯文本解析（原始接口，向后兼容）─────────────────────────────────────────


def parse_excel(content: bytes, text_column: str = "text") -> list[str]:
    df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    df.columns = [str(c).strip().lower() for c in df.columns]
    candidates = [text_column, "text", "content", "文本", "内容", "query", "问题", "input"]
    col = next((c for c in candidates if c in df.columns), df.columns[0])
    return [clean_text(t) for t in df[col].dropna().astype(str).tolist()]


def parse_json(content: bytes) -> list[str]:
    data = json.loads(content.decode("utf-8"))
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], str):
            return [clean_text(t) for t in data]
        if isinstance(data[0], dict):
            return [
                clean_text(str(item.get("content") or item.get("text") or item.get("query") or ""))
                for item in data
            ]
    if isinstance(data, dict):
        for key in ["data", "items", "records", "texts"]:
            if key in data and isinstance(data[key], list):
                return parse_json(json.dumps(data[key]).encode())
    raise ValueError("无法识别的 JSON 格式，请确保为 list[str] 或 list[{content:...}]")


def parse_file(filename: str, content: bytes) -> list[str]:
    """根据文件名选择解析器，返回纯文本列表（向后兼容接口）"""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return parse_excel(content)
    if name.endswith(".json"):
        return parse_json(content)
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
        col = df.columns[0]
        return [clean_text(str(t)) for t in df[col].dropna().tolist()]
    raise ValueError(f"不支持的文件格式: {filename}，请上传 xlsx / json / csv")


# ── 带标注的行解析（上传已标注历史数据专用）──────────────────────────────────


_TEXT_CANDIDATES = ["text", "content", "文本", "内容", "query", "问题", "input"]
_LABEL_CANDIDATES = ["label", "标签", "意图", "intent"]
_MIGRATION_COT = "历史数据迁移，默认为预标注结果，不再调用大模型"


def _detect_col(columns: list[str], candidates: list[str], fallback: str | None = None) -> str | None:
    """在 candidates 中按优先级找第一个存在于 columns 里的列名"""
    for c in candidates:
        if c in columns:
            return c
    return fallback


def _parse_tabular_rows(
    df: pd.DataFrame,
    text_column: str,
    label_column: str,
) -> list[dict[str, str | None]]:
    """将 DataFrame 解析为 [{"content": str, "label": str | None}, ...]"""
    cols = [str(c).strip().lower() for c in df.columns]
    df = df.copy()
    df.columns = cols

    text_col  = _detect_col(cols, [text_column] + _TEXT_CANDIDATES, fallback=cols[0])
    label_col = _detect_col(cols, [label_column] + _LABEL_CANDIDATES)  # None 表示文件中没有 label 列

    rows: list[dict[str, str | None]] = []
    for _, row in df.iterrows():
        raw_text = row.get(text_col)
        if raw_text is None or (isinstance(raw_text, float) and pd.isna(raw_text)):
            continue
        content = clean_text(str(raw_text))
        if not content:
            continue

        label: str | None = None
        if label_col:
            raw_label = row.get(label_col)
            if raw_label is not None and not (isinstance(raw_label, float) and pd.isna(raw_label)):
                lv = str(raw_label).strip()
                label = lv if lv else None

        rows.append({"content": content, "label": label})
    return rows


def parse_file_rows(
    filename: str,
    content: bytes,
    text_column: str = "text",
    label_column: str = "label",
) -> list[dict[str, str | None]]:
    """解析文件，返回 [{"content": str, "label": str | None}, ...]。

    - 若文件含 label（或等价列），则 label 字段有值；否则 label 为 None。
    - 支持 xlsx / xls / csv；JSON 文件不含标注信息，label 统一返回 None。
    """
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        return _parse_tabular_rows(df, text_column, label_column)
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
        return _parse_tabular_rows(df, text_column, label_column)
    if name.endswith(".json"):
        texts = parse_json(content)
        return [{"content": t, "label": None} for t in texts]
    raise ValueError(f"不支持的文件格式: {filename}，请上传 xlsx / json / csv")


# ── Pipeline 步骤：process ─────────────────────────────────────────────────


def process_item(item: dict[str, Any]) -> dict[str, Any]:
    """清洗单条数据内容，返回副本（stage 由 pipeline engine 更新）"""
    item = dict(item)
    item["content"] = clean_text(item.get("content", ""))
    return item

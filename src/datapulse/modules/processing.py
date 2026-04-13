"""
数据处理模块：文本清洗 + 文件解析
支持 Excel / JSON / CSV 上传
字段命名：content（对应 t_data_item.content）
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


# ── 文件解析 ───────────────────────────────────────────────────────────────


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
    """根据文件名选择解析器"""
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


# ── Pipeline 步骤：process ─────────────────────────────────────────────────


def process_item(item: dict[str, Any]) -> dict[str, Any]:
    """清洗单条数据内容，返回副本（stage 由 pipeline engine 更新）"""
    item = dict(item)
    item["content"] = clean_text(item.get("content", ""))
    return item

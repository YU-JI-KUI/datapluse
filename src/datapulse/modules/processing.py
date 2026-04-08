"""
数据处理模块：清洗 + 格式标准化
支持 Excel / JSON / CSV 上传
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
    # 去除首尾空白
    text = text.strip()
    # 合并多个空白字符
    text = re.sub(r"\s+", " ", text)
    # 去除不可见字符
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


def is_valid(text: str, min_len: int = 2, max_len: int = 512) -> bool:
    """过滤无效文本"""
    if not text or not text.strip():
        return False
    if len(text) < min_len or len(text) > max_len:
        return False
    return True


# ── 文件解析 ───────────────────────────────────────────────────────────────


def parse_excel(content: bytes, text_column: str = "text") -> list[str]:
    """解析 Excel 文件，返回文本列表"""
    df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    df.columns = [str(c).strip().lower() for c in df.columns]

    # 尝试找到文本列
    candidates = [text_column, "text", "文本", "内容", "query", "问题", "input"]
    col = None
    for c in candidates:
        if c in df.columns:
            col = c
            break
    if col is None:
        # 取第一列
        col = df.columns[0]

    texts = df[col].dropna().astype(str).tolist()
    return [clean_text(t) for t in texts]


def parse_json(content: bytes) -> list[str]:
    """解析 JSON 文件，支持 list[str] / list[{text:...}] / {data:[...]}"""
    data = json.loads(content.decode("utf-8"))

    if isinstance(data, list):
        if len(data) == 0:
            return []
        if isinstance(data[0], str):
            return [clean_text(t) for t in data]
        if isinstance(data[0], dict):
            texts = []
            for item in data:
                t = item.get("text") or item.get("query") or item.get("input") or ""
                texts.append(clean_text(str(t)))
            return texts

    if isinstance(data, dict):
        for key in ["data", "items", "records", "texts"]:
            if key in data and isinstance(data[key], list):
                return parse_json(json.dumps(data[key]).encode())

    raise ValueError("无法识别的 JSON 格式，请确保为 list[str] 或 list[{text:...}]")


def parse_file(filename: str, content: bytes) -> list[str]:
    """根据文件名选择解析器"""
    name = filename.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
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
    """对单条数据做清洗，返回新的 item（status → processed）"""
    item = dict(item)
    item["text"] = clean_text(item.get("text", ""))
    item["status"] = "processed"
    return item

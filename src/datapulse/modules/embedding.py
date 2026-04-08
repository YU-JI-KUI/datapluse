"""
Embedding 模块
use_mock=True  → 基于文本 hash 的确定性随机向量（开发用）
use_mock=False → 加载本地 SentenceTransformer 模型

配置通过 cfg dict 传入（来自 DB system_config.embedding 节点），支持热更新。
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

# 延迟加载的模型实例
_model: Any = None
_model_path: str = ""


def _get_model(model_path: str):
    """懒加载本地 embedding 模型"""
    global _model, _model_path
    if _model is None or _model_path != model_path:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(model_path)
            _model_path = model_path
        except ImportError:
            raise RuntimeError("sentence-transformers 未安装。请运行: uv add sentence-transformers")
        except Exception as e:
            raise RuntimeError(f"无法加载 embedding 模型: {model_path}\n错误: {e}")
    return _model


def _mock_embed(text: str, dim: int = 768) -> np.ndarray:
    """
    基于文本 hash 生成确定性随机向量（相同文本 → 相同向量）。
    已单位化，可用于 cosine 相似度计算。
    """
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**31)
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-8)


# ── 公共接口 ───────────────────────────────────────────────────────────────


def embed_text(text: str, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """对单条文本生成 embedding 向量"""
    emb_cfg = (cfg or {}).get("embedding", {})
    use_mock = emb_cfg.get("use_mock", True)
    model_path = emb_cfg.get("model_path", "./models/bge-base-zh")

    if use_mock:
        return _mock_embed(text)
    model = _get_model(model_path)
    vec = model.encode(text, normalize_embeddings=True)
    return vec.astype(np.float32)


def embed_batch(texts: list[str], cfg: dict[str, Any] | None = None) -> np.ndarray:
    """批量 embedding，返回 shape=(N, dim) 的 ndarray"""
    emb_cfg = (cfg or {}).get("embedding", {})
    use_mock = emb_cfg.get("use_mock", True)
    model_path = emb_cfg.get("model_path", "./models/bge-base-zh")
    batch_size = emb_cfg.get("batch_size", 64)

    if use_mock:
        return np.stack([_mock_embed(t) for t in texts])
    model = _get_model(model_path)
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vecs.astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """两个向量的 cosine 相似度（已归一化时即为点积）"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def reload_model() -> None:
    """配置更新后强制重新加载模型"""
    global _model, _model_path
    _model = None
    _model_path = ""

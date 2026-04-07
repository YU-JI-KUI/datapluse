"""
Embedding 模块
use_mock=True  → 随机单位向量（开发用）
use_mock=False → 从本地路径加载 SentenceTransformer 模型

模型路径在 config.yaml → embedding.model_path 中配置
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from config.settings import get_settings

# 延迟加载的模型实例
_model: Any = None
_model_path: str = ""


def _get_model():
    """懒加载本地 embedding 模型"""
    global _model, _model_path
    settings = get_settings()
    current_path = settings.embedding_model_path

    if _model is None or _model_path != current_path:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(current_path)
            _model_path = current_path
        except ImportError:
            raise RuntimeError(
                "sentence-transformers 未安装。"
                "请运行: pip install sentence-transformers"
            )
        except Exception as e:
            raise RuntimeError(
                f"无法从路径加载 embedding 模型: {current_path}\n错误: {e}"
            )
    return _model


def _mock_embed(text: str, dim: int = 768) -> np.ndarray:
    """
    基于文本 hash 生成确定性随机向量（相同文本 → 相同向量）
    保证单位化，可用于 cosine 相似度计算
    """
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**31)
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-8)


# ── 公共接口 ───────────────────────────────────────────────────────────────

def embed_text(text: str) -> np.ndarray:
    """对单条文本生成 embedding 向量"""
    settings = get_settings()
    if settings.embedding_use_mock:
        return _mock_embed(text)
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.astype(np.float32)


def embed_batch(texts: list[str]) -> np.ndarray:
    """批量 embedding，返回 shape=(N, dim) 的 ndarray"""
    settings = get_settings()
    if settings.embedding_use_mock:
        vecs = [_mock_embed(t) for t in texts]
        return np.stack(vecs)
    model = _get_model()
    batch_size = settings.embedding_batch_size
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

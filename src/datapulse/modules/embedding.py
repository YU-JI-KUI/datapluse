"""
Embedding 模块 — 加载本地 SentenceTransformer 模型，为文本生成向量。

模型路径通过环境变量 EMBEDDING_MODEL_PATH 统一配置（settings.py），
所有 dataset 共用同一模型，不再存储于 dataset 级配置。
batch_size 仍可通过 cfg["embedding"]["batch_size"] 按 dataset 调整。
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import structlog

# 延迟加载的模型实例（进程内单例）
_model: Any = None
_model_path: str = ""
_log = structlog.get_logger(__name__)


def _get_model_path() -> str:
    """从 settings 读取模型路径（所有 dataset 共用，通过 env 统一配置）。"""
    from datapulse.config.settings import get_settings
    return get_settings().embedding_model_path


def _get_model():
    """懒加载本地 embedding 模型（路径变化时自动重载）。"""
    global _model, _model_path
    model_path = _get_model_path()
    if _model is None or _model_path != model_path:
        _log.info("loading embedding model", model_path=model_path)
        t0 = time.time()
        try:
            from sentence_transformers import SentenceTransformer
            _model      = SentenceTransformer(model_path)
            _model_path = model_path
            _log.info("embedding model loaded", model_path=model_path,
                      elapsed_s=round(time.time() - t0, 1))
        except ImportError:
            raise RuntimeError("sentence-transformers 未安装。请运行: uv add sentence-transformers")
        except Exception as e:
            _log.error("failed to load embedding model", model_path=model_path, error=str(e))
            raise RuntimeError(f"无法加载 embedding 模型: {model_path}\n错误: {e}")
    return _model


# ── 公共接口 ───────────────────────────────────────────────────────────────


def embed_text(text: str, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """对单条文本生成 embedding 向量。"""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.astype(np.float32)


def embed_batch(texts: list[str], cfg: dict[str, Any] | None = None) -> np.ndarray:
    """批量 embedding，返回 shape=(N, dim) 的 ndarray。
    batch_size 从 cfg["embedding"]["batch_size"] 读取，默认 64。
    """
    batch_size = (cfg or {}).get("embedding", {}).get("batch_size", 64)
    model = _get_model()
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
    """强制清除模型缓存，下次调用 embed_* 时自动重新加载（EMBEDDING_MODEL_PATH 变更后调用）。"""
    global _model, _model_path
    _log.info("embedding model cache cleared (will reload on next call)", prev_path=_model_path)
    _model      = None
    _model_path = ""

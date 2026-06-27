"""提示词统一加载入口。

所有给大模型的提示词都放在 prompts/ 目录,代码里不写死提示词文本。
两种加载方式:
  - load_prompt(name)            : 读 prompts/ 根目录的共用模板(如 judge_user.md)
  - load_bu_prompt(bu_code, name): 优先 prompts/<bu_code>/,缺则回退 prompts/_default/

改提示词只动 prompts/ 下的文件,重启后端即生效(文件内容有缓存)。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """读 prompts/ 根目录下的共用模板。"""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


@lru_cache(maxsize=128)
def load_bu_prompt(bu_code: str, name: str) -> str:
    """读某 BU 某模板:优先 prompts/<bu_code>/<name>,缺则回退 prompts/_default/<name>。

    每个 BU 只需写自己有特殊要求的模板,其余自动复用通用版,无需重复维护。
    """
    bu_file = PROMPTS_DIR / bu_code / name
    if bu_file.exists():
        return bu_file.read_text(encoding="utf-8")
    return (PROMPTS_DIR / "_default" / name).read_text(encoding="utf-8")

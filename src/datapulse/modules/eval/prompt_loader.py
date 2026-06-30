"""提示词统一加载入口。

提示词以数据库表 t_eval_prompt 为准（支持页面实时编辑，改后不重启即生效），
库中无记录时回退读 prompts/ 下的同名文件（出厂默认）。两种加载方式：
  - load_prompt(name)            : 根目录共用模板（库 bu=_root，回退 prompts/<name>）
  - load_bu_prompt(bu_code, name): 优先 bu_code，缺则回退 _default（库与文件同此回退）

性能：judge 对每条样本都会取提示词，不能每条查库。改用进程内缓存 + 版本戳：
一次评测期间提示词不变，缓存稳定；用户在页面保存提示词时 bump_version() 使缓存
失效，下次评测即读到新值——既实时又不增加百万级评测的 DB 往返。
"""
from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

ROOT_SCOPE = "_root"        # load_prompt 的库作用域（对应 prompts/ 根目录）
DEFAULT_SCOPE = "_default"  # 各 BU 通用兜底（对应 prompts/_default/）

_version = 0
_cache: dict[tuple[str, str], str] = {}   # (bu_scope, name) -> content


def bump_version() -> None:
    """使全部提示词缓存失效。用户保存/删除提示词后调用。"""
    global _version
    _version += 1
    _cache.clear()


def _db_get(bu: str, name: str) -> str | None:
    """查库取提示词正文；DB 不可用（如测试环境）时静默返回 None 走文件回退。"""
    try:
        from datapulse.modules.eval import eval_db
        rec = eval_db.prompt_get(bu, name)
        return rec["content"] if rec else None
    except Exception:
        return None


def _file_read(rel: Path) -> str:
    return rel.read_text(encoding="utf-8")


def load_prompt(name: str) -> str:
    """根目录共用模板：库 bu=_root 优先，缺则读 prompts/<name>。"""
    key = (ROOT_SCOPE, name)
    if key in _cache:
        return _cache[key]
    content = _db_get(ROOT_SCOPE, name)
    if content is None:
        content = _file_read(PROMPTS_DIR / name)
    _cache[key] = content
    return content


def list_editable() -> list[dict]:
    """扫描 prompts/ 得到可编辑模板清单（出厂模板，仅 .md）。

    返回 [{bu, name}]，bu 为 _root（根目录）/ _default / 具体 BU。
    categories.json、README.md 等非提示词模板不含在内。库里的自定义状态与有效
    内容由 router 叠加。新增模板文件会自动出现在此清单。
    """
    items: list[dict] = []
    for md in sorted(PROMPTS_DIR.glob("*.md")):
        if md.name == "README.md":
            continue
        items.append({"bu": ROOT_SCOPE, "name": md.name})
    for sub in sorted(p for p in PROMPTS_DIR.iterdir() if p.is_dir()):
        for md in sorted(sub.glob("*.md")):
            items.append({"bu": sub.name, "name": md.name})
    return items


def file_default(bu: str, name: str) -> str | None:
    """读某 (bu, name) 的文件出厂默认内容（不查库、不走缓存）。重置用。"""
    rel = PROMPTS_DIR / name if bu == ROOT_SCOPE else PROMPTS_DIR / bu / name
    return _file_read(rel) if rel.exists() else None


def load_bu_prompt(bu_code: str, name: str) -> str:
    """某 BU 某模板：库/文件均优先 bu_code，缺则回退 _default。

    解析顺序：库 <bu>/<name> → 库 _default/<name> → 文件 <bu>/<name> → 文件 _default/<name>。
    每个 BU 只需维护自己有特殊要求的模板，其余自动复用通用版。
    """
    key = (bu_code, name)
    if key in _cache:
        return _cache[key]

    content = _db_get(bu_code, name)
    if content is None:
        content = _db_get(DEFAULT_SCOPE, name)
    if content is None:
        bu_file = PROMPTS_DIR / bu_code / name
        content = _file_read(bu_file if bu_file.exists() else PROMPTS_DIR / DEFAULT_SCOPE / name)

    _cache[key] = content
    return content


# 评测期间会用到的全部模板槽位(judge 每条样本 + advice 一次)。快照一次,整个
# 任务复用,避免跑到一半被 bump_version() 清缓存后前后用不同 prompt,口径不一致。
_SNAPSHOT_BU_SLOTS = (
    "judge_system.md", "task_dispatch.md", "task_business_type.md",
    "task_resolved.md", "task_review.md", "advice_system.md", "advice_user.md",
)
_SNAPSHOT_ROOT_SLOTS = ("judge_user.md",)


def snapshot_for_bu(bu_code: str) -> dict[str, str]:
    """把某 BU 评测要用的全部有效模板一次性读出,返回 {name: content}。

    在 run_evaluation 入口调一次,贯穿整个任务。BU 槽位走 load_bu_prompt(bu→_default
    回退),root 槽位走 load_prompt。读的是「当前生效内容」,此后任务内不再查库/缓存,
    用户中途改 prompt 也只影响下次评测,不污染进行中的任务。
    """
    snap = {name: load_bu_prompt(bu_code, name) for name in _SNAPSHOT_BU_SLOTS}
    for name in _SNAPSHOT_ROOT_SLOTS:
        snap[name] = load_prompt(name)
    return snap

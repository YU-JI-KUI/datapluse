"""BU(业务单元)领域知识抽象。

把「证券 / 寿险 / 产险…」各自不同的领域知识封装成一个 BUConfig,流水线骨架
(过滤→会话重组→答案解析→Judge→洞察→建议)对所有 BU 通用,只是注入不同的
BUConfig。新增一个 BU = 加一个 BUConfig + 注册,无需改引擎。

Java 类比:BUConfig 是「领域策略对象」(Strategy Pattern),引擎是上下文,
运行时按上传选择的 BU 注入对应策略。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# 业务分类定义放在 prompts/<bu>/categories.json —— 它本质是喂给模型的上下文,
# 与判定规则、人设统一收口在 prompts 目录。
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_categories_from_file(code: str) -> dict[str, str]:
    """从 prompts/<code>/categories.json 读业务分类（出厂默认），返回 {分类名: definition}。

    JSON 结构:{"categories": {"分类名": {"definition": "..."}}}。库为空时回退用它。
    """
    path = _PROMPTS_DIR / code / "categories.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {name: c["definition"] for name, c in data["categories"].items()}


# 业务分类缓存：以库为准、文件兜底；增删改时 bump_categories_version 失效。
# 评测时 get_bu 每次按当前分类动态构造 BUConfig，故改了不重启即生效。
_cat_cache: dict[str, dict[str, str]] = {}


def bump_categories_version() -> None:
    """业务分类增删改后调用，使缓存失效（下次评测/读取即拿到最新）。"""
    _cat_cache.clear()


def load_categories(code: str) -> dict[str, str]:
    """读某 BU 的业务分类：库优先、文件兜底。返回 {分类名: definition}（有序）。

    DB 不可用（如测试环境、import 期）时静默回退文件，保证离线可跑。
    """
    if code in _cat_cache:
        return _cat_cache[code]
    cats: dict[str, str] = {}
    try:
        from datapulse.modules.eval import eval_db
        rows = eval_db.category_list(code)   # 已按 sort_order 排序
        cats = {r["name"]: r["definition"] for r in rows}
    except Exception:
        cats = {}
    if not cats:
        cats = load_categories_from_file(code)
    _cat_cache[code] = cats
    return cats


# 活动标问缓存：以库为准，增删改时 bump_activity_version 失效。评测时 get_bu 把当前
# 集合快照进 BUConfig，故页面改了不重启即生效。
_activity_cache: dict[str, frozenset] = {}


def bump_activity_version() -> None:
    """活动标问增删后调用，使缓存失效（下次评测/读取即拿到最新）。"""
    _activity_cache.clear()


def load_activity_questions(code: str) -> frozenset:
    """读某 BU 的活动标问集合（与客户问题精确相等即命中）。DB 不可用时返回空集。

    返回 frozenset[str]，问题已 strip。无文件兜底——活动标问只在库里维护（区别于
    业务分类有出厂 JSON），库里没有就视为「该 BU 暂无活动标问」，不过滤任何样本。
    """
    if code in _activity_cache:
        return _activity_cache[code]
    qs: set[str] = set()
    try:
        from datapulse.modules.eval import eval_db
        qs = {q.strip() for q in eval_db.activity_list_questions(code) if q and q.strip()}
    except Exception:
        qs = set()
    fs = frozenset(qs)
    _activity_cache[code] = fs
    return fs


@dataclass(frozen=True)
class BUConfig:
    """一个 BU 的全部领域知识。"""

    code: str            # 机器标识,如 "securities" / "life"
    name: str            # 展示名,如 "证券" / "寿险"
    description: str     # 一句话定位,用于前端/Judge 上下文

    # 日志「分发BU」列里代表本 BU 的取值(可能多个,如 "证券"/"证券业务"/"PA_SEC")。
    # 与 name(展示名)解耦:真实日志列值常和中文展示名不同。空则回退到 name。
    dispatch_aliases: tuple = ()

    # 业务分类体系:分类名 -> 定义/示例。Judge 的分类标签集。
    intents: dict[str, str] = field(default_factory=dict)

    # Mock 规则桩用的关键词规则(仅 mock 后端用,真实模型不需要):
    #   mock_intent_rules: [(关键词列表, 意图), ...],顺序敏感,先具体后宽泛
    #   mock_module_map:   承接模块名 -> 该模块负责的意图列表(宽松分发匹配)
    mock_intent_rules: list = field(default_factory=list)
    mock_module_map: dict = field(default_factory=dict)

    # 内置样例文件名(校准集 / 生产集),供零配置体验
    sample_calib: str = ""
    sample_prod: str = ""

    # 评测期间的提示词快照 {模板名: 内容}。run_evaluation 入口注入,贯穿整个任务,
    # 避免中途被 bump_version 清缓存导致前后口径不一致。None 表示未快照(小数据/
    # 测试路径),此时 prompt(name) 实时回退 load_bu_prompt。
    prompts: dict | None = None

    # 活动标问集合（前端写死按钮触发的写死回复，评测时整条跳过）。get_bu 时注入当前
    # 库中该 BU 的集合，作为快照随任务固定。空集 = 不过滤任何样本。
    activity_questions: frozenset = frozenset()

    def prompt(self, name: str) -> str:
        """取某模板内容:优先用任务快照,无快照则实时加载(回退兼容)。"""
        if self.prompts is not None and name in self.prompts:
            return self.prompts[name]
        from datapulse.modules.eval.prompt_loader import load_bu_prompt, load_prompt
        # judge_user.md 是 root 共享槽位,其余按 BU
        if name == "judge_user.md":
            return load_prompt(name)
        return load_bu_prompt(self.code, name)

    def is_activity(self, question: str) -> bool:
        """客户问题是否为活动标问（与集合精确相等，去首尾空格）。集合空则恒 False。"""
        if not self.activity_questions:
            return False
        return (question or "").strip() in self.activity_questions

    def matches_dispatch(self, raw: str) -> bool:
        """日志「分发BU」列值是否代表本 BU(用于判断系统是否把这条分给了本 BU)。

        优先用 dispatch_aliases 精确相等(最安全);未配别名时回退到 name 子串匹配
        (兼容旧数据)。真实日志列值若不是中文展示名(如 PA_SEC),在对应 BU 的
        dispatch_aliases 里补一个取值即可,无需改通用代码。
        """
        raw = (raw or "").strip()
        if not raw:
            return False
        if self.dispatch_aliases:
            return raw in self.dispatch_aliases
        return self.name in raw  # 回退:展示名子串匹配

    def intent_list(self) -> list[dict]:
        """给前端:业务分类标签全集(含定义)。"""
        return [{"intent": k, "definition": v} for k, v in self.intents.items()]

    def intents_block(self) -> str:
        """渲染成 markdown 表格喂给模型(Qwen 对 table 结构更易理解)。

        分类名/定义里的 | 转义,避免破坏表格列。
        """
        def esc(s: str) -> str:
            return str(s).replace("|", "\\|").replace("\n", " ")

        lines = ["| 业务分类 | 定义 |", "| --- | --- |"]
        lines += [f"| {esc(k)} | {esc(v)} |" for k, v in self.intents.items()]
        return "\n".join(lines)

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
_activity_cache: dict[str, dict[str, str]] = {}


def bump_activity_version() -> None:
    """活动标问增删后调用，使缓存失效（下次评测/读取即拿到最新）。"""
    _activity_cache.clear()


def load_activity_questions(code: str) -> dict[str, str]:
    """读某 BU 的活动标问映射 {question(strip 后) → 活动名}。DB 不可用时返回空 dict。

    命中判断仍是「客户问题精确相等于某标问」（判 dict 的 key，等值不变）；命中后可查
    出该问题所属活动名，供报告按活动聚合。活动名为空时兜底用 question 本身。
    无文件兜底——活动标问只在库里维护，库里没有就视为该 BU 暂无活动标问，不过滤样本。
    """
    if code in _activity_cache:
        return _activity_cache[code]
    mapping: dict[str, str] = {}
    try:
        from datapulse.modules.eval import eval_db
        for q, act in eval_db.activity_list_questions(code):
            qs = (q or "").strip()
            if qs:
                mapping[qs] = (act or "").strip() or qs
    except Exception:
        mapping = {}
    _activity_cache[code] = mapping
    return mapping


# 短路规则缓存：以库为准，增删改时 bump_rules_version 失效。评测时 get_bu 把当前规则
# 快照进 BUConfig，命中即用写死结果免 LLM。
_rules_cache: dict[str, dict] = {}


def bump_rules_version() -> None:
    """短路规则增删后调用，使缓存失效（下次评测/读取即拿到最新）。"""
    _rules_cache.clear()


def _is_pattern(q: str) -> bool:
    """触发问题是否为通配/LIKE 模式：含 * 或 %（否则精确匹配，走 dict O(1)）。"""
    return "*" in q or "%" in q


def match_pattern(pattern: str, question: str) -> bool:
    """按 SQL LIKE 风格匹配触发问题（pattern 已 strip）：
      *      → 任意问题（恒真）
      %x%    → 包含 x
      x%     → 以 x 开头
      %x     → 以 x 结尾
      其它   → 精确相等（无 % 通配）
    * 视为 %% 的特例。空 pattern 恒不匹配。"""
    if not pattern:
        return False
    if pattern == "*":
        return True
    q = question or ""
    has_lead = pattern.startswith("%")
    has_trail = pattern.endswith("%")
    core = pattern.strip("%")
    if has_lead and has_trail:
        return core in q                 # %x%
    if has_trail:
        return q.startswith(core)        # x%
    if has_lead:
        return q.endswith(core)          # %x
    return q == pattern                  # 无 %：精确


def load_rules(code: str) -> dict:
    """读某 BU 的短路规则(规则集模型),扁平成 {归一化question → {rule_name, answers:set, judge}}。

    一个规则含多个触发问题,把每个问题都建成 key 挂上该规则的答案集合/规则名/judge。
    精确问题走 dict O(1) 单点查；含 */% 的模式问题额外收进内部 __patterns__ 列表,
    match_rule 精确未命中时才遍历模式规则（规则数通常几十条,遍历可忽略）。
    DB 不可用/无规则返回空 dict。
    """
    if code in _rules_cache:
        return _rules_cache[code]
    rules: dict = {}
    patterns: list = []   # [(pattern, rule_entry)]，供 match_rule 遍历
    try:
        from datapulse.modules.eval import eval_db
        for r in eval_db.rule_list_for_match(code):
            name = (r.get("name") or "").strip()
            questions = r.get("questions") or []
            answers = {(a or "").strip() for a in (r.get("answers") or [])}
            judge = r.get("judge_json") or {}
            for q in questions:
                qs = (q or "").strip()
                if not qs:
                    continue
                entry = {"rule_name": name or qs, "answers": answers, "judge": judge}
                if _is_pattern(qs):
                    patterns.append((qs, entry))
                else:
                    rules[qs] = entry
    except Exception:
        rules, patterns = {}, []
    # 模式规则挂在保留 key 上（普通问题不含 * 与 %，不会与之冲突）
    if patterns:
        rules["__patterns__"] = patterns
    _rules_cache[code] = rules
    return rules


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

    # 活动标问映射 {question(strip) → 活动名}（前端写死按钮触发的写死回复，评测时整条
    # 跳过）。get_bu 时注入当前库中该 BU 的快照随任务固定。空 = 不过滤任何样本。
    activity_questions: dict = field(default_factory=dict)

    # 短路规则 {归一化question: {rule_name, answers:set, judge}}。命中（问题精确+答案一致）
    # 即用写死 judge 结果免 LLM。get_bu 时注入快照。空 = 不短路。
    rules: dict = field(default_factory=dict)

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
        """客户问题是否为活动标问（与标问精确相等，去首尾空格）。空则恒 False。"""
        if not self.activity_questions:
            return False
        return (question or "").strip() in self.activity_questions

    def activity_of(self, question: str) -> str:
        """命中的活动标问所属的活动名（未命中返回空）。供报告按活动聚合。"""
        return self.activity_questions.get((question or "").strip(), "")

    def match_rule(self, question: str, answer: str) -> tuple[dict, str] | None:
        """短路规则匹配（规则集）：客户问题匹配某规则的触发问题 且 答案 ∈ 该规则的答案
        集合（独立组合）→ 返回 (写死judge, 规则名)，供免 LLM 产出结果 + 报告按规则名聚合。

        触发问题支持：精确相等、*（任意）、%x%（包含）、x%（前缀）、%x（后缀）。
        精确问题走 dict O(1) 快路径；未命中再遍历模式规则。答案侧始终精确 ∈ 答案集合。
        不匹配 → None，走正常 LLM 评测。"""
        if not self.rules:
            return None
        q = (question or "").strip()
        a = (answer or "").strip()
        # 1) 精确问题：O(1) 快路径（跳过保留 key __patterns__）
        rule = self.rules.get(q)
        if rule is not None and a in rule["answers"]:
            judge = rule.get("judge") or None
            if judge:
                return (judge, rule["rule_name"])
        # 2) 模式问题：遍历（含 */%like%），第一个「问匹配 且 答在集合」的命中
        for pattern, entry in self.rules.get("__patterns__", []):
            if match_pattern(pattern, q) and a in entry["answers"]:
                judge = entry.get("judge") or None
                if judge:
                    return (judge, entry["rule_name"])
        return None

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

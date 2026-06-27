"""提示词加载层测试：库优先 / 缓存 / bump 失效 / 文件回退 / 可编辑清单。"""
from datapulse.modules.eval import prompt_loader as pl


def setup_function():
    pl.bump_version()   # 每个用例前清缓存，互不污染


def test_file_fallback_when_db_empty(monkeypatch):
    # _db_get 返回 None（库空）→ 回退读文件，judge_system 文件必然存在
    monkeypatch.setattr(pl, "_db_get", lambda bu, name: None)
    content = pl.load_bu_prompt("securities", "judge_system.md")
    assert content.strip()   # 读到了文件内容


def test_db_takes_precedence(monkeypatch):
    monkeypatch.setattr(pl, "_db_get", lambda bu, name: "DB版本内容" if bu == "securities" else None)
    assert pl.load_bu_prompt("securities", "judge_system.md") == "DB版本内容"


def test_default_scope_fallback(monkeypatch):
    # bu 自身无、_default 有 → 用 _default
    def fake(bu, name):
        return "通用兜底" if bu == pl.DEFAULT_SCOPE else None
    monkeypatch.setattr(pl, "_db_get", fake)
    assert pl.load_bu_prompt("life", "task_review.md") == "通用兜底"


def test_cache_hit_then_bump(monkeypatch):
    calls = {"n": 0}

    def fake(bu, name):
        calls["n"] += 1
        return f"v{calls['n']}"
    monkeypatch.setattr(pl, "_db_get", fake)

    first = pl.load_bu_prompt("securities", "judge_system.md")
    second = pl.load_bu_prompt("securities", "judge_system.md")
    assert first == second               # 第二次命中缓存，未再查库
    assert calls["n"] == 1

    pl.bump_version()                    # 用户保存后失效
    third = pl.load_bu_prompt("securities", "judge_system.md")
    assert third != first                # 重新查库拿到新值
    assert calls["n"] == 2


def test_load_prompt_root_scope(monkeypatch):
    monkeypatch.setattr(pl, "_db_get", lambda bu, name: "ROOT" if bu == pl.ROOT_SCOPE else None)
    assert pl.load_prompt("judge_user.md") == "ROOT"


def test_list_editable_covers_md_only():
    items = pl.list_editable()
    names = {(it["bu"], it["name"]) for it in items}
    # 出厂模板应在清单内
    assert (pl.ROOT_SCOPE, "judge_user.md") in names
    assert ("securities", "judge_system.md") in names
    assert (pl.DEFAULT_SCOPE, "task_dispatch.md") in names
    # 非提示词文件不应混入
    assert all(not it["name"].endswith(".json") for it in items)
    assert all(it["name"] != "README.md" for it in items)


def test_file_default_reads_factory(monkeypatch):
    # file_default 不查库，直接读文件
    monkeypatch.setattr(pl, "_db_get", lambda bu, name: "应被忽略")
    assert pl.file_default("securities", "judge_system.md").strip()
    assert pl.file_default("securities", "不存在的.md") is None

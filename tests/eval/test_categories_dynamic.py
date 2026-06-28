"""业务分类动态注入测试：库优先 / 文件兜底 / bump 失效 / get_bu 注入。"""
from datapulse.modules.eval.bu import base as bubase
from datapulse.modules.eval.bu.registry import get_bu


def setup_function():
    bubase.bump_categories_version()


def test_file_fallback_when_db_empty(monkeypatch):
    # DB 返回空 → load_categories 回退读文件，证券分类文件必有内容
    import datapulse.modules.eval.eval_db as eval_db
    monkeypatch.setattr(eval_db, "category_list", lambda code: [])
    bubase.bump_categories_version()
    cats = bubase.load_categories("securities")
    assert cats and "资产查询" in cats


def test_get_bu_injects_categories(monkeypatch):
    # get_bu 应把当前分类注入 BUConfig.intents（这里用库返回的 mock 数据）
    import datapulse.modules.eval.eval_db as eval_db
    monkeypatch.setattr(eval_db, "category_list",
                        lambda code: [{"name": "测试分类", "definition": "def"}] if code == "securities" else [])
    bubase.bump_categories_version()
    bu = get_bu("securities")
    assert bu.intents == {"测试分类": "def"}
    assert "测试分类" in bu.intents_block()


def test_bump_invalidates_cache(monkeypatch):
    import datapulse.modules.eval.eval_db as eval_db
    calls = {"n": 0}

    def fake(code):
        calls["n"] += 1
        return [{"name": f"v{calls['n']}", "definition": "d"}]
    monkeypatch.setattr(eval_db, "category_list", fake)

    bubase.bump_categories_version()
    first = bubase.load_categories("securities")
    second = bubase.load_categories("securities")
    assert first == second and calls["n"] == 1     # 第二次命中缓存

    bubase.bump_categories_version()
    third = bubase.load_categories("securities")
    assert third != first and calls["n"] == 2      # 失效后重查

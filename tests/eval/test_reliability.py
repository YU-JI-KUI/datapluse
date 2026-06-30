"""可靠性测试：429 退避 / 限流上抛 / 启动自动恢复。"""
import asyncio

import pytest

from datapulse.modules.eval.llm import judge_runner, pingan_client
from datapulse.modules.eval.llm.judge_runner import RateLimitedError


@pytest.fixture(autouse=True)
def _stub_signing(monkeypatch):
    # 签名依赖真实 RSA key，测试环境没有；调用前桩掉，只测重试/退避逻辑
    monkeypatch.setattr(pingan_client, "get_open_api_sign", lambda *a, **k: "sig")
    monkeypatch.setattr(pingan_client, "generate_app_sign", lambda *a, **k: "sig")


class _FakeResp:
    def __init__(self, status, json_data=None, headers=None):
        self.status_code = status
        self._json = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """假 httpx client：只实现 post，供注入替换真实 _get_client()。

    真实 _get_client() 现在按 running event loop 缓存,必须在 async 上下文调用;
    测试用 monkeypatch 把 _get_client 整个换掉,避免在同步上下文取 loop 报错。"""
    def __init__(self, post_fn):
        self.post = post_fn


def _patch_client(monkeypatch, post_fn):
    monkeypatch.setattr(pingan_client, "_get_client", lambda: _FakeClient(post_fn))


def test_429_retries_then_returns_rate_limited(monkeypatch):
    """429 持续 → 退避重试，最终返回带 rate_limited 标记。"""
    calls = {"n": 0}

    async def fake_post(*a, **k):
        calls["n"] += 1
        return _FakeResp(429, headers={"Retry-After": "0"})

    _patch_client(monkeypatch, fake_post)

    async def run():
        return await pingan_client.call_bigmodel_api(
            "q", "scene", "k", "s", timeout=1, max_retries=3)

    out = asyncio.run(run())
    assert out.get("rate_limited") is True
    assert calls["n"] == 3            # 重试到上限


def test_429_then_success(monkeypatch):
    """先 429 再 200 → 退避后成功返回。"""
    seq = [_FakeResp(429, headers={"Retry-After": "0"}), _FakeResp(200, {"ok": 1})]

    async def fake_post(*a, **k):
        return seq.pop(0)

    _patch_client(monkeypatch, fake_post)
    out = asyncio.run(pingan_client.call_bigmodel_api("q", "s", "k", "s", timeout=1, max_retries=3))
    assert out == {"ok": 1}


def test_4xx_not_retried(monkeypatch):
    """非限流 4xx（如 401）→ 不重试，直接失败。"""
    calls = {"n": 0}

    async def fake_post(*a, **k):
        calls["n"] += 1
        return _FakeResp(401)

    _patch_client(monkeypatch, fake_post)
    out = asyncio.run(pingan_client.call_bigmodel_api("q", "s", "k", "s", timeout=1, max_retries=3))
    assert "error" in out and calls["n"] == 1    # 只调一次


def test_judge_batch_raises_on_rate_limit(monkeypatch):
    """单条限流 → judge_batch 整批上抛 RateLimitedError（让引擎暂停）。"""
    async def fake_judge_one(s, bu):
        raise RateLimitedError("limited")

    monkeypatch.setattr(judge_runner, "judge_one", fake_judge_one)
    with pytest.raises(RateLimitedError):
        asyncio.run(judge_runner.judge_batch([{"row_index": 0}], bu=None))


def test_recover_tasks_requeues_idle_and_reclaims_stale(monkeypatch):
    """启动恢复(多 POD 安全)：把 paused/interrupted 退回 pending + 回收心跳超时的僵尸，
    返回两者之和。绝不无条件动 running(别的 POD 可能正跑着)。"""
    from datapulse.pipeline import eval_engine

    calls = {}

    def _fake_reclaim(sec):
        calls["stale_sec"] = sec
        return 1

    monkeypatch.setattr(eval_engine.eval_db, "requeue_idle", lambda: 2)
    monkeypatch.setattr(eval_engine.eval_db, "reclaim_stale", _fake_reclaim)

    n = eval_engine.recover_tasks()
    assert n == 3                      # requeue_idle(2) + reclaim_stale(1)
    assert calls["stale_sec"] > 0      # 用心跳超时阈值回收僵尸

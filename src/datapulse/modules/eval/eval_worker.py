"""评测任务调度:多 POD 抢占式后台 worker。

原先是进程内 queue.Queue + 单 daemon 线程,任务存在某个 POD 的内存里——多副本
部署下另一个 POD 看不到、重启即丢、还会重复 recover。改为 DB 驱动:

  - 任务状态机全在 t_eval_task(pending → running → done/failed)。
  - 每个 POD 跑一个 daemon 线程,轮询用 SELECT...FOR UPDATE SKIP LOCKED 抢 pending 任务。
  - 跑评测前先抢一把进程间 advisory lock,保证「全集群同时只跑一个评测」,避免多 POD
    一起压垮内网 LLM 网关(并发由单任务内的 judge_concurrency 控制)。
  - 运行中定期心跳续约;持有任务的 POD 崩了,心跳超时后任务被回收重抢(断点续跑)。

submit() 不再入内存队列——只要任务在库里是 pending,任一 POD 的 worker 都会抢到。
"""
from __future__ import annotations

import os
import socket
import threading
import time
import uuid

import structlog

from datapulse.modules.eval import eval_db

_log = structlog.get_logger(__name__)

# 本 worker 的唯一标识:主机名 + 进程号 + 随机后缀,用于 claimed_by / 心跳归属判定。
_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"

# 空闲(无 pending 或抢不到全局锁)时的轮询间隔(秒)
_IDLE_POLL_SEC = 5
# 心跳续约间隔(秒)
_HEARTBEAT_SEC = 30
# 心跳超时阈值:running 任务超过这么久没心跳 → 视为持有 POD 已死,回收重跑
_STALE_SEC = 180

_worker: threading.Thread | None = None
_lock = threading.Lock()


def _heartbeat_loop(task_id: str, stop: threading.Event) -> None:
    """任务运行期间的心跳线程:定期续约 heartbeat_at,直到任务结束置 stop。"""
    while not stop.wait(_HEARTBEAT_SEC):
        try:
            eval_db.heartbeat(task_id, _WORKER_ID)
        except Exception:
            _log.warning("eval.worker.heartbeat_failed", task_id=task_id)


def _run_one(task_id: str, operator: str) -> None:
    """跑一个抢到的任务,期间维持心跳。resume=True:已落盘行跳过,续跑。"""
    from datapulse.pipeline.eval_engine import run_eval_sync

    stop = threading.Event()
    hb = threading.Thread(target=_heartbeat_loop, args=(task_id, stop),
                          name=f"eval-hb-{task_id}", daemon=True)
    hb.start()
    try:
        run_eval_sync(task_id, resume=True, operator=operator)
    finally:
        stop.set()


def _run_loop() -> None:
    """worker 主循环:回收僵尸 → 持全局锁 → 抢任务串行跑 → 无任务则歇。

    单个任务异常不影响后续(run_eval 内部已落盘失败态,这里兜底防线程退出)。
    """
    while True:
        try:
            # 先回收心跳超时的僵尸任务(原 POD 已死),退回 pending 供重抢
            reclaimed = eval_db.reclaim_stale(_STALE_SEC)
            if reclaimed:
                _log.info("eval.worker.reclaimed", count=reclaimed)

            with eval_db.advisory_lock() as got_lock:
                if not got_lock:
                    time.sleep(_IDLE_POLL_SEC)   # 别的 POD 在跑评测,稍后再试
                    continue
                # 持有全局锁期间,把当前能抢到的 pending 任务串行跑完
                while True:
                    task = eval_db.claim_next_task(_WORKER_ID)
                    if task is None:
                        break   # 没有 pending 了,释放锁去歇
                    operator = task.get("created_by") or "system"
                    _log.info("eval.worker.claimed", task_id=task["task_id"], worker=_WORKER_ID)
                    try:
                        _run_one(task["task_id"], operator)
                    except Exception:
                        _log.exception("eval.worker.task_failed", task_id=task["task_id"])
        except Exception:
            _log.exception("eval.worker.loop_error")
        time.sleep(_IDLE_POLL_SEC)


def start_worker() -> None:
    """启动后台 worker 线程(幂等)。应用启动时调一次。"""
    global _worker
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_run_loop, name="eval-worker", daemon=True)
        _worker.start()
        _log.info("eval.worker.started", worker=_WORKER_ID)


def submit(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """提交评测任务。DB 驱动下只需保证任务在库里是 pending(调用方已置),worker 会抢。

    保留此函数签名兼容 router/recover 调用方;不再入进程内队列。resume 参数已无意义
    (worker 统一按 resume=True 跑,已落盘行天然跳过),保留仅为兼容。
    """
    start_worker()   # 兜底:worker 未启动则现起
    _log.info("eval.worker.submitted", task_id=task_id)


def schedule_resume(task_id: str, delay: float, operator: str = "eval") -> None:
    """限流暂停后延迟 delay 秒把任务退回 pending,供 worker 重新抢占续跑。"""
    def _fire():
        try:
            eval_db.update_task(task_id, updated_by=operator, status="pending", stage="")
            _log.info("eval.worker.resume_fired", task_id=task_id)
        except Exception:
            _log.exception("eval.worker.resume_failed", task_id=task_id)

    timer = threading.Timer(delay, _fire)
    timer.daemon = True
    timer.start()
    _log.info("eval.worker.resume_scheduled", task_id=task_id, delay=delay)

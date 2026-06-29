"""评测任务的进程内后台队列（单 worker，串行执行）。

原先评测走 FastAPI BackgroundTasks（在 web 进程的请求线程池里跑 asyncio.run），
3 万条的长任务会霸占工作线程，把 datapulse 整站接口拖死。

改为：web 请求只把 task_id 入队后立即返回；一个常驻 daemon 线程从队列串行取出
执行评测。评测与 web 请求线程/事件循环完全隔离，不再占用请求线程池。并发=1
（同时只跑一个评测任务），避免多任务同时压垮 LLM 网关。
"""
from __future__ import annotations

import queue
import threading

import structlog

_log = structlog.get_logger(__name__)

# (task_id, resume, operator) 任务队列；单 worker 串行消费
_queue: "queue.Queue[tuple[str, bool, str]]" = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def _run_loop() -> None:
    """worker 主循环：串行取任务执行。单个任务异常不影响后续任务。"""
    from datapulse.pipeline.eval_engine import run_eval_sync

    while True:
        task_id, resume, operator = _queue.get()
        try:
            _log.info("eval.worker.start", task_id=task_id, resume=resume, qsize=_queue.qsize())
            run_eval_sync(task_id, resume=resume, operator=operator)
        except Exception:
            # run_eval 内部已把失败写库；这里兜底防止 worker 线程意外退出
            _log.exception("eval.worker.task_failed", task_id=task_id)
        finally:
            _queue.task_done()


def start_worker() -> None:
    """启动后台 worker 线程（幂等）。应用启动时调一次。"""
    global _worker
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_run_loop, name="eval-worker", daemon=True)
        _worker.start()
        _log.info("eval.worker.started")


def submit(task_id: str, resume: bool = False, operator: str = "eval") -> None:
    """把评测任务入队，立即返回（不阻塞 web 请求）。"""
    start_worker()   # 兜底：worker 未启动则现起
    _queue.put((task_id, resume, operator))
    _log.info("eval.worker.submitted", task_id=task_id, qsize=_queue.qsize())


def schedule_resume(task_id: str, delay: float, operator: str = "eval") -> None:
    """延迟 delay 秒后把任务重新入队续跑（限流暂停后自动恢复用）。"""
    def _fire():
        _log.info("eval.worker.resume_fired", task_id=task_id)
        submit(task_id, resume=True, operator=operator)

    timer = threading.Timer(delay, _fire)
    timer.daemon = True
    timer.start()
    _log.info("eval.worker.resume_scheduled", task_id=task_id, delay=delay)


def pending_count() -> int:
    """队列中等待执行的任务数（不含正在跑的）。"""
    return _queue.qsize()

"""定时任务管理模块，基于 APScheduler 实现。"""

from __future__ import annotations

from datetime import time
from typing import Callable, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


class ScheduleManager:
    """包装 APScheduler，提供简单的定时任务管理接口。"""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._jobs: Dict[str, str] = {}

    def start(self) -> None:
        if not self._scheduler.running:
            logger.debug("启动定时任务调度器")
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            logger.debug("关闭定时任务调度器")
            self._scheduler.shutdown(wait=False)

    def add_daily_job(self, job_id: str, at_time: str, func: Callable, *args, **kwargs) -> None:
        """添加每天固定时间执行的任务。"""

        self.remove(job_id)
        hh, mm = at_time.split(":")
        trigger = CronTrigger(hour=int(hh), minute=int(mm))
        job = self._scheduler.add_job(func, trigger, args=args, kwargs=kwargs, id=job_id, replace_existing=True)
        self._jobs[job_id] = job.id
        logger.info("新增每日定时任务: {} -> {}", job_id, at_time)

    def remove(self, job_id: str) -> None:
        job_key = self._jobs.pop(job_id, None)
        if job_key and self._scheduler.get_job(job_key):
            logger.debug("移除定时任务: {}", job_id)
            self._scheduler.remove_job(job_key)

    def get_job(self, job_id: str) -> Optional[str]:
        return self._jobs.get(job_id)

    def __del__(self) -> None:
        self.shutdown()


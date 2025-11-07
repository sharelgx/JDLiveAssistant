"""卡密验证与授权管理模块。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

DATE_FMT = "%Y-%m-%d"


class LicenseError(Exception):
    """授权异常。"""


@dataclass
class LicenseInfo:
    """授权信息结构。"""

    key: str
    expiry: datetime

    @property
    def expiry_date(self) -> str:
        return self.expiry.strftime(DATE_FMT)


DEFAULT_KEY_REGISTRY: Dict[str, str] = {
    # 示例卡密，可在部署时替换为真实数据或接入远程校验。
    "JD-DEMO-2025": "2025-12-31",
}


class LicenseManager:
    """负责卡密录入、校验、持久化与有效期判断。"""

    def __init__(self, path: Path, registry: Optional[Dict[str, str]] = None) -> None:
        self.path = path
        self.registry = {k.upper(): v for k, v in (registry or DEFAULT_KEY_REGISTRY).items()}
        self._info: Optional[LicenseInfo] = None
        self.load()

    # ---------------------------------------------------------------------
    # 基础读写
    def load(self) -> None:
        """加载本地授权文件。"""

        if not self.path.exists():
            return

        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:  # noqa: PERF203
            logger.error("读取授权文件失败: {}", exc)
            return

        key = str(data.get("key", "")).strip().upper()
        expiry_str = str(data.get("expiry", "")).strip()
        if not key or not expiry_str:
            return

        try:
            expiry = _parse_expiry(expiry_str)
        except ValueError:
            logger.warning("授权文件中的日期格式不合法: {}", expiry_str)
            return

        self._info = LicenseInfo(key=key, expiry=expiry)

    def save(self) -> None:
        """持久化当前授权信息。"""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {}
        if self._info:
            payload = {"key": self._info.key, "expiry": self._info.expiry_date}

        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    # ---------------------------------------------------------------------
    # 校验逻辑
    def validate_key(self, key: str) -> LicenseInfo:
        """校验卡密并保存授权信息。"""

        key = key.strip().upper()
        if not key:
            raise LicenseError("请输入卡密")

        expiry_str = self.registry.get(key)
        if not expiry_str:
            raise LicenseError("卡密不存在或未授权")

        expiry = _parse_expiry(expiry_str)
        if expiry < _now():
            raise LicenseError("卡密已过期，请联系管理员续期")

        self._info = LicenseInfo(key=key, expiry=expiry)
        self.save()
        logger.info("卡密 {} 验证通过，有效期至 {}", key, expiry_str)
        return self._info

    # ---------------------------------------------------------------------
    @property
    def info(self) -> Optional[LicenseInfo]:
        return self._info

    @property
    def is_valid(self) -> bool:
        if not self._info:
            return False
        return self._info.expiry >= _now()

    @property
    def remaining_days(self) -> int:
        if not self._info or not self.is_valid:
            return 0
        delta = self._info.expiry - _now()
        return max(delta.days, 0)

    def invalidate(self) -> None:
        self._info = None
        self.save()


def _parse_expiry(expiry_str: str) -> datetime:
    """将 yyyy-mm-dd 转换为时区感知的 datetime，并补至当日结束。"""

    date = datetime.strptime(expiry_str, DATE_FMT)
    # 视作当日 23:59:59 仍可使用，统一转为 UTC。
    return datetime(date.year, date.month, date.day, 23, 59, 59, tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


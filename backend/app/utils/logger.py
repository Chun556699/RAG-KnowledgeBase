"""
日志工具模块。

提供统一的日志器配置，控制台输出带时间戳与级别，便于本地调试与云端排障。
"""

import logging
import sys

from app.config import get_settings

# 全局标记，避免重复配置根日志器
_CONFIGURED = False


class _SafeStreamHandler(logging.StreamHandler):
    """编码容错的标准输出日志处理器。

    Windows 控制台默认 cp1252/GBK，中文日志会抛 UnicodeEncodeError；
    此处对编码失败的消息降级为 replace 输出，保证日志不中断业务。
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                msg = self.format(record)
                stream = self.stream
                stream.write(
                    msg.encode(stream.encoding or "utf-8", errors="replace").decode(
                        stream.encoding or "utf-8"
                    )
                    + self.terminator
                )
                self.flush()
            except Exception:  # noqa: BLE001
                self.handleError(record)


def _configure_root_logger() -> None:
    """配置根日志器：输出到标准输出，统一格式。仅执行一次。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = _SafeStreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    # 清理已有 handler，防止在热重载场景下重复输出
    root.handlers.clear()
    root.addHandler(handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    获取带统一格式的命名日志器。

    Args:
        name: 日志器名称，通常传入 __name__。

    Returns:
        logging.Logger: 配置好的日志器实例。
    """
    _configure_root_logger()
    return logging.getLogger(name)

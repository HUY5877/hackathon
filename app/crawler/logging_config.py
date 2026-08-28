"""日志配置 — 结构化日志，统一格式

提供：
- JSON 格式日志（便于日志聚合系统消费）
- 控制台彩色输出（开发环境）
- 按模块分级
- 爬虫专用 logger 配置
"""

import logging
import sys
from typing import Literal

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 爬虫相关模块的日志级别
MODULE_LEVELS = {
    "app.crawler": logging.INFO,
    "app.crawler.base": logging.INFO,
    "app.crawler.scheduler": logging.INFO,
    "app.crawler.llm_processor": logging.INFO,
    "app.crawler.apscheduler_manager": logging.INFO,
    "app.api.v1.crawler": logging.INFO,
    "httpx": logging.WARNING,        # 降低 httpx 噪音
    "sqlalchemy.engine": logging.WARNING,
    "apscheduler": logging.WARNING,
    "urllib3": logging.WARNING,
}


class CrawlerLogFilter(logging.Filter):
    """为爬虫日志添加 platform 字段（便于过滤）"""

    def filter(self, record: logging.LogRecord) -> bool:
        # 从 logger name 提取平台名
        if not hasattr(record, "platform"):
            for part in record.name.split("."):
                if part in ("dorahacks", "devpost", "mlh",
                            "eventbrite", "saikr", "tianchi", "huodongxing"):
                    record.platform = part
                    break
            else:
                record.platform = "-"
        return True


def setup_logging(
    level: str | int = logging.INFO,
    format_type: Literal["text", "json"] = "text",
) -> None:
    """配置全局日志

    Args:
        level: 根日志级别
        format_type: 输出格式（text 控制台友好 / json 日志聚合友好）
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有 handlers（避免重复）
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if format_type == "json":
        formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler.setFormatter(formatter)
    console_handler.addFilter(CrawlerLogFilter())
    root_logger.addHandler(console_handler)

    # 应用模块级别
    for module, mod_level in MODULE_LEVELS.items():
        logging.getLogger(module).setLevel(mod_level)

    # 抑制第三方库的过多日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class _JsonFormatter(logging.Formatter):
    """JSON 日志格式（便于 ELK/Loki 等聚合系统消费）"""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "platform": getattr(record, "platform", "-"),
        }

        # 异常信息
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # 额外字段
        for key in ("platform", "url", "status", "elapsed_seconds", "raw_count"):
            if hasattr(record, key) and key not in log_entry:
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, ensure_ascii=False)


def get_crawler_logger(platform: str | None = None) -> logging.Logger:
    """获取爬虫专用 logger

    Args:
        platform: 平台名（可选，用于日志过滤）
    """
    if platform:
        logger = logging.getLogger(f"app.crawler.{platform}")
        logger.platform = platform  # type: ignore
    else:
        logger = logging.getLogger("app.crawler")
    return logger

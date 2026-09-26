from __future__ import annotations

import os
import re
import sys
from typing import Any

from nonebot import logger


_AUTH_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)([^\s,;]+)"
)


def _secret_values() -> tuple[str, ...]:
    names = ("ONEBOT_ACCESS_TOKEN", "NAPCAT_WEBUI_TOKEN", "AI_API_KEY")
    return tuple(
        value
        for name in names
        if (value := os.getenv(name, "").strip()) and len(value) >= 8
    )


def configure_logging(level: str) -> None:
    normalized = level.upper()
    try:
        logger.level(normalized)
    except ValueError:
        normalized = "INFO"

    secrets = _secret_values()

    def redact(record: dict[str, Any]) -> bool:
        message = str(record["message"])
        for secret in secrets:
            message = message.replace(secret, "[REDACTED]")
        record["message"] = _AUTH_PATTERN.sub(r"\1[REDACTED]", message)
        return True

    logger.remove()
    logger.add(
        sys.stdout,
        level=normalized,
        filter=redact,
        colorize=False,
        backtrace=False,
        diagnose=False,
        enqueue=False,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
            "{name}:{function}:{line} - {message}"
        ),
    )

from __future__ import annotations

import time


_STARTED_AT = time.monotonic()


def uptime_seconds() -> int:
    return max(0, int(time.monotonic() - _STARTED_AT))


def format_uptime(seconds: int | None = None) -> str:
    remaining = uptime_seconds() if seconds is None else max(0, seconds)
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, seconds_part = divmod(remaining, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours or days:
        parts.append(f"{hours}小时")
    if minutes or hours or days:
        parts.append(f"{minutes}分钟")
    parts.append(f"{seconds_part}秒")
    return "".join(parts)

#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


GENERIC_PATTERNS = (
    re.compile(r"(?i)(二维码解码URL\s*:\s*)\S+"),
    re.compile(r"(?i)(webui\s*token\s*[:=]\s*)\S+"),
    re.compile(r'(?i)("?napcat_quick_password(?:_md5)?"?\s*[:=]\s*"?)[^"\s,}]+'),
    re.compile(r"(?i)((?:proofwaterurl|jumpurl)\s*[:=]\s*)\S+"),
    re.compile(r"(?i)(https?://[^/\s]*qq\.com/)\S+"),
    re.compile(r"(?i)(token=)[^&\s]+"),
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)\S+"),
)


def load_secrets(env_path: Path) -> tuple[str, ...]:
    if not env_path.is_file():
        return ()
    wanted = {
        "ONEBOT_ACCESS_TOKEN",
        "NAPCAT_WEBUI_TOKEN",
        "NAPCAT_QUICK_PASSWORD_MD5",
        "NAPCAT_QUICK_PASSWORD",
        "AI_API_KEY",
    }
    values: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() not in wanted:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            # Match single-quoted dotenv escaping used by set-ai-config.sh.
            value = re.sub(r"\\([\\'])", r"\1", value[1:-1])
        else:
            value = value.strip('"')
        if len(value) >= 8:
            values.append(value)
    return tuple(sorted(set(values), key=len, reverse=True))


def redact_line(line: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        line = line.replace(secret, "[REDACTED]")
    for pattern in GENERIC_PATTERNS:
        line = pattern.sub(r"\1[REDACTED]", line)
    return line


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".env")
    secrets = load_secrets(env_path)

    qr_art_redacted = False
    for raw_line in sys.stdin:
        line = raw_line
        if sum(line.count(character) for character in "▄▀█") >= 4:
            if not qr_art_redacted:
                sys.stdout.write("[QR_CODE_REDACTED]\n")
                sys.stdout.flush()
            qr_art_redacted = True
            continue
        qr_art_redacted = False
        sys.stdout.write(redact_line(line, secrets))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

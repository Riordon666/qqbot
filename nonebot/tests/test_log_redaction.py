from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "redact_logs.py"
SPEC = importlib.util.spec_from_file_location("qqbot_redact_logs", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
REDACTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REDACTOR)


def test_load_secrets_includes_password_fallback(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    credential = "a" * 32
    env_path.write_text(
        "ONEBOT_ACCESS_TOKEN=onebot-secret-value\n"
        f"NAPCAT_QUICK_PASSWORD_MD5={credential}\n"
        "BOT_NAME=not-a-secret\n",
        encoding="utf-8",
    )

    secrets = REDACTOR.load_secrets(env_path)

    assert credential in secrets
    assert "not-a-secret" not in secrets


def test_redact_line_masks_exact_and_labeled_credentials() -> None:
    credential = "b" * 32
    secrets = (credential,)

    line = REDACTOR.redact_line(f"credential={credential}\n", secrets)
    assert credential not in line
    assert "[REDACTED]" in line

    generic = REDACTOR.redact_line(f"NAPCAT_QUICK_PASSWORD_MD5={credential}\n", ())
    assert credential not in generic
    assert "[REDACTED]" in generic


def test_redact_line_masks_qq_verification_urls() -> None:
    verification_url = "https://ti.qq.com/safe/tools/captcha/sms-verify-login?sid=secret"

    labeled = REDACTOR.redact_line(f"proofWaterUrl: {verification_url}\n", ())
    assert "sid=secret" not in labeled
    assert "[REDACTED]" in labeled

    warning = REDACTOR.redact_line(f"verification required: {verification_url}\n", ())
    assert "sid=secret" not in warning
    assert "[REDACTED]" in warning


def test_load_secrets_sorts_overlapping_values_longest_first(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    shorter = "shared-secret"
    longer = f"{shorter}-with-suffix"
    env_path.write_text(
        f"ONEBOT_ACCESS_TOKEN={shorter}\n"
        f"NAPCAT_QUICK_PASSWORD={longer}\n",
        encoding="utf-8",
    )

    secrets = REDACTOR.load_secrets(env_path)
    redacted = REDACTOR.redact_line(longer, secrets)

    assert secrets == (longer, shorter)
    assert longer not in redacted
    assert "with-suffix" not in redacted


def test_redact_line_masks_json_labeled_credentials() -> None:
    credential = "c" * 32
    line = REDACTOR.redact_line(
        f'{{"NAPCAT_QUICK_PASSWORD_MD5":"{credential}"}}\n', ()
    )
    assert credential not in line
    assert "[REDACTED]" in line


def test_load_secrets_decodes_single_quoted_dotenv_values(tmp_path: Path) -> None:
    env_path = tmp_path / '.env'
    credential = "test-value-$literal-\\-quote-'"
    encoded = credential.replace('\\', '\\\\').replace("'", "\\'")
    env_path.write_text(f"AI_API_KEY='{encoded}'\n", encoding='utf-8')

    secrets = REDACTOR.load_secrets(env_path)

    assert secrets == (credential,)
    assert REDACTOR.redact_line(credential, secrets) == '[REDACTED]'

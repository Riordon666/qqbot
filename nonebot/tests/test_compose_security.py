from __future__ import annotations

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPOSITORY_ROOT / "docker-compose.yml"


def _compose() -> dict[str, object]:
    parsed = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_internal_services_are_not_published_to_the_internet() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)
    nonebot = services["nonebot"]
    napcat = services["napcat"]

    assert "ports" not in nonebot
    assert nonebot["expose"] == ["8080"]
    assert napcat["ports"] == ["127.0.0.1:6099:6099"]
    assert nonebot["networks"] == ["qqbot"]
    assert napcat["networks"] == ["qqbot"]
    assert compose["networks"]["qqbot"]["driver"] == "bridge"


def test_compose_keeps_runtime_hardening_and_pinned_images() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)

    for service in services.values():
        assert isinstance(service, dict)
        assert service.get("privileged") is not True
        assert "/var/run/docker.sock" not in str(service.get("volumes", []))
        assert "latest" not in str(service.get("image", "")).casefold()
        logging = service.get("logging")
        assert isinstance(logging, dict)
        assert logging.get("driver") == "local"

    nonebot = services["nonebot"]
    assert nonebot["read_only"] is True
    assert nonebot["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in nonebot["security_opt"]


def test_only_declared_runtime_configuration_reaches_nonebot() -> None:
    compose = _compose()
    environment = compose["services"]["nonebot"]["environment"]
    assert isinstance(environment, dict)

    assert environment["ONEBOT_ACCESS_TOKEN"].endswith(" is required}")
    assert environment["AI_API_KEY"] == "${AI_API_KEY:-}"
    assert all("PASSWORD" not in key for key in environment)
    assert all("WEBUI" not in key for key in environment)

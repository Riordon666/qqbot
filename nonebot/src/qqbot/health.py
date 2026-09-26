from __future__ import annotations

from nonebot.drivers import ASGIMixin, HTTPServerSetup, Request, Response, URL


async def healthz(_: Request) -> Response:
    return Response(
        status_code=200,
        headers={"content-type": "application/json"},
        content='{"status":"ok","scope":"process"}',
    )


def setup_health_route(driver: object) -> None:
    if not isinstance(driver, ASGIMixin):
        raise RuntimeError("QQBot requires an ASGI-compatible NoneBot driver")

    driver.setup_http_server(
        HTTPServerSetup(
            path=URL("/healthz"),
            method="GET",
            name="qqbot-healthz",
            handle_func=healthz,
        )
    )

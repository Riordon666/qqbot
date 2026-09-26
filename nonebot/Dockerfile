ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579
FROM ${PYTHON_IMAGE} AS app

ARG UV_VERSION=0.12.7

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:${PATH} \
    PYTHONPATH=/app/src \
    HOME=/home/qqbot

RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}" \
    && groupadd --gid 1001 qqbot \
    && useradd --uid 1000 --gid 1001 --create-home --home-dir /home/qqbot --shell /usr/sbin/nologin qqbot

WORKDIR /app

COPY nonebot/pyproject.toml nonebot/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY nonebot/bot.py ./
COPY nonebot/src ./src
COPY nonebot/prompts ./prompts
COPY nonebot/skills ./skills
RUN uv sync --locked --no-dev \
    && chown -R qqbot:qqbot /app /home/qqbot

USER 1000:1001

FROM app AS test
USER root
RUN uv sync --locked --group dev
COPY . /repo
WORKDIR /repo/nonebot
USER 1000:1001
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

FROM app AS runtime
CMD ["python", "bot.py"]

# QQBot Lite maintenance

Read `README.md`, `docs/DEVELOPMENT.md`, the relevant implementation, and the
current Git diff before changing code. Preserve unrelated work and runtime data.

## Scope and architecture

- This repository is the reusable public edition. Do not import operator-specific
  integrations, production identities, credentials, databases, or login state.
- Local development does not authorize changing a running server. Deployment must
  be explicitly requested for a named target.
- Keep one message router: `PluginSpec` → plugin → service → shared database or
  fixed external API. Register plugins in both `bot.py` and `pyproject.toml`.
- Chat memory belongs in SQLite. Separate groups and private conversations. Treat
  nicknames, history, summaries, and external responses as untrusted data.
- Skills are local prompt files, not executable code or unrestricted tools.
- All external requests must be asynchronous, bounded, and timeout-protected.

## Runtime and security

- Keep the existing two-container setup. Only WebUI `127.0.0.1:6099` is published;
  NoneBot 8080 and OneBot remain inside the Compose bridge network.
- Keep AI disabled until configured. Never make an API key mandatory for startup.
- Do not add remote shell, dynamic execution, arbitrary URL fetching, privileged
  containers, or Docker Socket mounts.
- Never print or commit `.env`, authentication headers, private keys, raw logs,
  databases, backups, QQ login state, or reversible copies of private identifiers.
- Keep dependencies locked; changes to NapCat require explicit version and digest.
- Do not restart NapCat for a NoneBot-only change.

## Verification and release

Run relevant tests, then the full suite for behavioral changes:

```bash
cd nonebot
uv sync --frozen --group dev
uv run --frozen pytest -q
cd ..
shellcheck scripts/*.sh
git diff --check
```

The CI workflow also validates Compose and builds/tests the Docker image. A
container health check does not prove QQ login or real message delivery; report
those separately. Review both staged content and commit history before a public
push. Preserve existing remote history and never force-push without authorization.

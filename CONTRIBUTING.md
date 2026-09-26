# Contributing to QQBot

Thanks for helping improve QQBot. Keep changes small, reviewable, safe for a
low-resource server, and independent of any one operator's account or private
service.

## Before starting

1. Read `README.md`, `SECURITY.md`, and `THIRD_PARTY_NOTICES.md`.
2. Search existing issues and pull requests.
3. For a substantial behavior or architecture change, open a design issue
   before implementing it.
4. Report vulnerabilities through GitHub Security Advisories, not a public
   issue or pull request.

## Local development

Python 3.12 and `uv` are the supported local toolchain. From the `nonebot`
directory:

```bash
uv sync --frozen --group dev
uv run pytest
```

To validate the container configuration from the repository root, create a
local `.env` from `.env.example`, fill it with non-production development
values, and run:

```bash
docker compose config --quiet
docker compose build nonebot
```

Never commit the local `.env` or generated runtime state.

## Design rules

- Keep event matchers thin: matcher to service to database or external API.
- Put each user-facing capability in its own plugin and keep reusable business
  logic in a service module.
- Use the shared asynchronous database layer. Plugins must not open ad-hoc
  SQLite connections.
- External I/O must be asynchronous and must have explicit timeouts, bounded
  concurrency, input validation, and user-safe error handling.
- Detailed exceptions belong in redacted server logs; chat replies must not
  expose paths, credentials, internal addresses, or stack traces.
- Do not add shell execution, dynamic evaluation, arbitrary URL fetching, or a
  chat-to-system-command bridge.
- AI features must start safely when disabled or when no provider key is set.
- A plugin must not consume a message after a higher-priority plugin has
  already handled it.
- Preserve isolation between users, groups, and conversations.

## Public-repository hygiene

Use synthetic identities and data in tests and examples. Do not commit:

- environment files, API credentials, password hashes, private keys, cookies,
  QR codes, or authorization headers containing live values;
- QQ login state, NapCat configuration state, databases, logs, backups, or
  conversation history;
- personal QQ or group numbers, host addresses, private domains, local user
  paths, or production screenshots;
- operator-specific business integrations, prompts, persona text, or service
  documentation;
- third-party source, binaries, images, artwork, or branding without verified
  redistribution permission.

Run the public-release tests before submitting. A secret removed in a later
commit can remain recoverable from Git history, so scan the complete branch
history before publishing a repository for the first time.

## Tests and pull requests

Every behavior change should include tests for success, failure, permission,
and malformed-input paths as applicable. Before opening a pull request, run:

```bash
cd nonebot
uv run pytest
cd ..
git diff --check
docker compose config --quiet
```

In the pull request, explain the user-visible outcome, security impact,
configuration changes, test evidence, and rollback considerations. Do not
include live logs or production message bodies.

By submitting a contribution, you agree that your contribution is licensed
under the repository's MIT License. Third-party material remains under its own
license and must be clearly identified.

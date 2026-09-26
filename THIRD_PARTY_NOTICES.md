# Third-party notices

The MIT License in this repository covers only QQBot's original source code
and documentation. It does not relicense any third-party project, container
image, client, library, protocol specification, logo, name, or trademark.

## Runtime frameworks and protocol

- [NoneBot2](https://github.com/nonebot/nonebot2) is distributed under the MIT
  License.
- [NoneBot Adapter OneBot](https://github.com/nonebot/adapter-onebot) is
  distributed under the MIT License.
- This project interoperates with the
  [OneBot 11 specification](https://github.com/botuniverse/onebot-11). OneBot
  is a protocol specification; it is not bundled into this repository as a QQ
  client.
- Python package versions are declared in `nonebot/pyproject.toml` and locked
  in `nonebot/uv.lock`. Each package remains subject to its own license and
  notices.

## NapCatQQ and Tencent QQ for Linux

NapCatQQ and Tencent QQ for Linux are not part of this repository and are not
redistributed in its source archives or releases. The deployment configuration
may instruct Docker to obtain an independently published NapCat image when an
operator explicitly starts the stack.

- NapCatQQ uses its own
  [Limited Redistribution License](https://github.com/NapNeko/NapCatQQ/blob/main/LICENSE),
  which includes restrictions that differ from the MIT License, including
  restrictions concerning redistribution and commercial use. Review the
  current upstream license before use or distribution.
- Tencent QQ for Linux is proprietary software. Obtain it only through an
  authorized distribution channel and comply with Tencent's current terms,
  platform rules, and applicable law.

Do not copy NapCatQQ source, NapCat binaries, Tencent QQ binaries, QQ login
state, or third-party branding into a QQBot release without separate, explicit
authorization and a fresh license review.

NapCatQQ, NoneBot, OneBot, QQ, Tencent, and all other third-party names and
marks belong to their respective owners. QQBot is an independent community
project and is not an official Tencent or NapCat project.

## Operational notice

An unofficial QQ access implementation may be detected or restricted by the
platform. Using this project cannot guarantee uninterrupted login or freedom
from account limitations. Operators are responsible for protecting their
accounts, credentials, chat data, and backups.

# Security policy

## Supported versions

Security fixes are applied to the latest release and the current `main`
branch. Older releases may no longer receive fixes. Before reporting a problem,
confirm that it is reproducible on a supported version when doing so is safe.

## Report a vulnerability privately

Please use this repository's **GitHub Security Advisory** form:

1. Open the repository's **Security** tab.
2. Select **Advisories**.
3. Select **Report a vulnerability**.

Do not open a public issue for an unpatched vulnerability. If the advisory
button is unavailable, open a public issue containing no exploit details or
secrets and ask the maintainers to enable a private reporting channel.

Include the affected version, impact, minimal reproduction steps, and a
suggested mitigation if available. Redact QQ numbers, group numbers, message
content, tokens, passwords, API keys, private keys, cookies, QR codes, database
contents, host addresses, and login-state files. A maintainer may ask for more
information in the private advisory.

Reports are handled on a best-effort basis. No response or remediation time is
guaranteed.

## Issues that belong in a security report

Examples include:

- authentication or authorization bypass;
- exposure of OneBot, WebUI, AI-provider, or other credentials;
- remote code execution, command injection, path traversal, or unsafe file
  access;
- server-side request forgery or unrestricted outbound requests;
- cross-group or cross-user disclosure of conversation memory;
- sensitive data leaking through logs, health endpoints, backups, or error
  messages;
- a default deployment that unexpectedly publishes an internal service.

Third-party platform enforcement, ordinary QQ login expiry, upstream NapCat
compatibility, and provider outages are generally support or upstream issues,
not vulnerabilities in QQBot. Report them as ordinary issues only after
removing personal data. If QQBot itself leaks credentials or weakens an access
boundary during such an event, report that part privately.

## Safe research expectations

- Test only systems and accounts you own or are authorized to test.
- Do not access other users' messages or data.
- Do not degrade service, evade platform controls, or persist access.
- Stop after obtaining the minimum evidence necessary to describe the issue.
- Never place a real secret in an issue, pull request, test fixture, screenshot,
  or diagnostic log.

## If a secret may have leaked

Treat it as compromised: revoke or rotate it at the issuing system, update the
server-side configuration, restart only the affected service, and review logs
and Git history for exposure. Deleting a file in a later commit does not remove
it from existing Git history or forks.

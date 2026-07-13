# Security Policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository:

1. Open the repository's **Security** tab.
2. Select **Report a vulnerability**.
3. Include affected versions, reproduction steps, impact, and any proposed mitigation.

Do not open a public issue for an unpatched vulnerability. Maintainers will acknowledge a complete report, assess severity, and coordinate disclosure through the private advisory.

## Security boundaries

ATO runs model-selected tools on a local project. Read-only tools may run automatically; mutating tools require a durable approval unless the development-only `ATO_AUTO_APPROVE_TOOLS=1` override is set.

The core resolves paths against a configured project root, denies outside-root filesystem access, runs Git in the target repository, bounds subprocess time, and redacts secret-like argument keys in persisted audit summaries. These controls reduce risk but do not make untrusted prompts or unreviewed approvals safe.

## User responsibilities

- Review the tool name, task ID, request ID, and argument summary before approving.
- Run ATO with the least filesystem and account permissions required.
- Keep API keys in environment variables or a secret manager, never task descriptions.
- Protect `ato-output` because task artifacts may contain project information.
- Do not enable automatic approval in production or on untrusted repositories.

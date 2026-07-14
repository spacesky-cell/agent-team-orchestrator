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

The root npm package includes a SHA-256 manifest for its Python wheel. First-run provisioning validates the manifest and path containment, creates an isolated versioned environment under an exclusive lock, bounds venv/pip/probe subprocesses, redacts install diagnostics, and promotes only a successfully probed runtime. npm installation itself runs no Python postinstall script.

## User responsibilities

- Review the tool name, task ID, request ID, and argument summary before approving.
- Run ATO with the least filesystem and account permissions required.
- Keep API keys in environment variables or a secret manager, never task descriptions.
- Treat Python package-index configuration as sensitive; authenticated URLs are redacted from ATO errors but still belong in your normal secret-management path.
- Protect `ato-output` because task artifacts may contain project information.
- Do not enable automatic approval in production or on untrusted repositories.

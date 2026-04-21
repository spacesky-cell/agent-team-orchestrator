# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Agent Team Orchestrator, please follow these steps:

1. **Do NOT** open a public GitHub issue for the vulnerability.

2. Send an email to: **[your-email@example.com]** (please replace with actual contact)

3. Include the following information:
   - Type of issue (e.g., buffer overflow, SQL injection, etc.)
   - Full paths of source file(s) related to the issue
   - Location of the affected source code (tag/branch/commit or direct URL)
   - Step-by-step instructions to reproduce the issue
   - Proof-of-concept or exploit code (if possible)
   - Impact of the issue, including how an attacker might exploit it

4. You should receive a response within **48 hours**. If the issue is confirmed:
   - We will acknowledge receipt within **3 working days**
   - We will aim to provide a fix/patch within **7 working days** depending on complexity
   - We will coordinate disclosure with you

## Security Best Practices for Users

### API Keys

- Never commit `.env` files to version control
- Use environment variables or secret management services for API keys
- Rotate your keys regularly

### Command Execution

The `execute_command` tool has built-in safety restrictions:
- Blocked patterns: `rm -rf /`, `sudo`, `chmod 777`, fork bombs, etc.
- Enable `safe_mode: true` (default) to activate these protections
- Always review commands before allowing execution in production environments

### File Access

File operations are restricted to allowed directories:
- By default, only files under the current working directory are accessible
- Configure `ALLOWED_DIRS` in `file_ops.py` and `code_ops.py` as needed

### Network Security

- Ensure your LLM provider's API endpoint uses HTTPS
- When using Ollama locally, bind to localhost only
- Configure firewall rules appropriately when exposing MCP servers

## Known Security Considerations

1. **Python Script Injection**: The MCP Server and CLI generate Python scripts dynamically. Ensure only trusted input is processed.
2. **LLM Output**: AI-generated code is executed directly. Review outputs before using in sensitive environments.
3. **Database**: SQLite checkpoint databases are not encrypted by default. For sensitive data, consider encryption at rest.

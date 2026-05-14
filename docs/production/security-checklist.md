# Security Checklist — Lexa AI

## Before Every Release

### Command Security
- [ ] All new commands registered in command_whitelist.json
- [ ] Correct security tier assigned (always_allowed / confirmation_required / blocked)
- [ ] No shell=True in any subprocess call
- [ ] PowerShell arguments sanitized (_sanitize_ps_arg)
- [ ] Action names validated: `[a-z_][a-z0-9_]*` regex

### Input Validation
- [ ] All user inputs sanitized through security.py
- [ ] 36 injection patterns tested
- [ ] Path traversal guards on all file operations
- [ ] URL validation (http/https only, private IPs blocked)
- [ ] String length caps on all text inputs
- [ ] Unicode normalization (NFKC) applied

### Electron Security
- [ ] CSP: `script-src 'self'` (no unsafe-inline)
- [ ] No inline event handlers in index.html
- [ ] `tests/test_csp_static.py` passes
- [ ] All fetch through preload.js bridge
- [ ] contextIsolation: true
- [ ] nodeIntegration: false
- [ ] No user content in innerHTML

### API Security
- [ ] API only on localhost (127.0.0.1:8000)
- [ ] Per-endpoint rate limiting active
- [ ] Rate limit headers present (X-RateLimit-*)
- [ ] Audit logging for all command executions
- [ ] File upload: extension blocklist + path validation

### Secrets
- [ ] No API keys in source code
- [ ] No credentials in git history: `git log --all -p | grep -i "api_key\|password\|secret" | head -20`
- [ ] .env in .gitignore
- [ ] .env.example has only placeholder values

### AI Security
- [ ] Prompt injection patterns detected (security.py)
- [ ] AI output parsed and validated (action_parser.py)
- [ ] Unknown commands require user confirmation
- [ ] AI cannot execute blocked commands regardless of output

### Plugin Security
- [ ] Plugin size limit (100KB)
- [ ] Max 20 commands per plugin
- [ ] 11 forbidden patterns checked (eval, exec, os.system, etc.)
- [ ] Plugins cannot override existing commands

## Periodic Audits
- Run `/qa` with security focus on critical features
- Review audit logs for suspicious patterns
- Test rate limiting under load
- Verify whitelist is up to date with actual commands

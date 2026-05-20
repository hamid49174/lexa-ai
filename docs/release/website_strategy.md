# Website Build and Lint Strategy

Current website path:

`C:\Users\admin\OneDrive\Desktop\lexa\lexa-website`

Observed Phase 4B state:

- not a Git repository
- no `package.json`
- static HTML/CSS/JS layer
- uses Supabase and Stripe client-side configuration placeholders in `config.js`
- includes external CDN/runtime scripts for Supabase, Stripe, and Spline
- contains `tmp_*.js` migration/scratch scripts

Phase 4C re-check:

- website remains external and not a Git repo
- no package-based build/lint can be proven yet
- static smoke is the only current website gate
- no deployment action is part of the release checks

Current smoke:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_website_smoke.ps1
```

The smoke blocks secret files and secret-looking patterns, warns about placeholders, warns about `tmp_*.js`, and lists external scripts needing CSP/vendor review. It does not deploy.
Public Supabase anon keys and Stripe publishable keys are allowed only when clearly treated as public client configuration. Supabase service-role keys and Stripe secret keys are blocking failures.

Options:

1. Keep website static and continue using static smoke.
2. Add a small website `package.json` with lint/build checks.
3. Move website to its own repository with dedicated CI.
4. Integrate website into a monorepo later.

Recommended next small step:

Keep it external for now, remove or archive `tmp_*.js` only after review, and add a minimal website `package.json` with static lint/build checks before deployment preparation. That package should not introduce a framework migration or redesign in the same patch.

Release blockers:

- committed `.env` or secret keys
- Stripe secret key or Supabase service-role key in website files
- deployment without reviewed configuration

Warn-only for now:

- static-only website without package-based lint/build
- CDN/external scripts needing CSP and pinning review
- scratch `tmp_*.js` files

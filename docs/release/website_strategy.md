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

Phase 4D re-check:

- website remains external and not a Git repo
- no package-based build/lint can be proven yet
- static smoke is the only current website gate
- no deployment action is part of the release checks
- release target is currently `static-external`
- this is acceptable for InternalRC review, but not enough for PublicRC/PublicRelease

Phase 4E decision:

- Website remains a `static-external` target for now.
- No `package.json` is added in this phase because the website is outside the Lexa Git repository and is not itself a Git repo.
- PublicRC remains blocked until a website release target is approved and package-based build/lint or an equivalent static-release validation is proven.
- InternalRC may proceed with the existing static smoke warnings.

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

Keep it external/static for now, remove or archive `tmp_*.js` only after review, and add a minimal website `package.json` with static lint/build checks before deployment preparation. That package should not introduce a framework migration or redesign in the same patch.

The safest next implementation is a dedicated website phase that either creates a separate website repository or adds a minimal website-local `package.json` with no framework migration and scripts such as `smoke`, `check:static`, and `lint:static`.

Release blockers:

- committed `.env` or secret keys
- Stripe secret key or Supabase service-role key in website files
- deployment without reviewed configuration

Warn-only for now:

- static-only website without package-based lint/build
- CDN/external scripts needing CSP and pinning review
- scratch `tmp_*.js` files

Release tier impact:

- InternalRC: static-external website is allowed with warnings.
- PublicRC: website target must be approved and package-based build/lint or an equivalent static-release workflow must be proven.
- PublicRelease: deployment path, public config, CSP/vendor strategy, and secret handling must be reviewed.

Phase 4F readiness:

- Website remains `static-external`.
- This is an explicit release decision for InternalRC only.
- PublicRC remains blocked until a build/lint target or equivalent static-release proof exists.
- `scripts\run_website_smoke.ps1 -Target PublicRC` fails by design while the website lacks package-based proof.
- No website redesign, repository migration, or deployment action is part of Phase 4F.

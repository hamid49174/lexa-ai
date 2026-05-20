# External Website Hardening Snapshot

Date: 2026-05-20
Lexa repo baseline: `7a3009a86c4c0f1b3f41cd7b8b07b5fc966ba53b`

The external website folder `../lexa-website` is not inside the Lexa Git repository and is not itself a Git repository. The previous hardening sprint edited these external files:

- `../lexa-website/index.html`
- `../lexa-website/i18n.js`

This document is the preservation step for the Lexa repo. It records the external state so the changes are not silently lost, but it is not a website release target, deployment approval, CDN/SRI approval, or Git history for the website.

## Preserved External Changes

- Fake/pre-launch testimonials were converted to beta placeholder copy and non-customer sample roles.
- The terminal animation now builds lines with DOM nodes and `textContent` instead of concatenating terminal output through `innerHTML`.
- Pricing subtitle and Spline loader fallback rendering use DOM node replacement rather than string-built HTML.
- No website deployment, package migration, release target, or public domain decision was made.

## Still Decision-Required

- `og:url` and related public metadata still reference `https://exa-ai.space`; the intended Lexa public domain is not unambiguous from repo-owned evidence.
- CDN/vendor resources still need a CSP/SRI/self-hosting decision before PublicRC.
- The website still lacks package-based build/lint proof or an approved equivalent static-release workflow.
- The website must be versioned before relying on it for release evidence, either as its own Git repository, a reviewed website-local patch, or an approved monorepo integration.

## Safe Next Step

Choose one website ownership path before treating the site as release evidence:

1. Initialize a dedicated website Git repository and commit the current hardened state.
2. Create a reviewed patch artifact for `../lexa-website/index.html` and `../lexa-website/i18n.js`.
3. Move the website into an approved repo/monorepo path with static smoke, lint/build, CSP/vendor review, and artifact policy.

Until one of those happens, Lexa can use only the repo-owned documentation and static smoke warnings for InternalRC review. PublicRC remains blocked on website ownership, release target, CDN/CSP/SRI, and domain metadata decisions.

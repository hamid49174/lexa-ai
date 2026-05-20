# Privacy and Trace Consent Checklist

This checklist is a PublicRelease review artifact. It does not collect user data, enable telemetry, upload logs, or approve any external sharing by itself.

## Data That Can Exist

| Data class | Local by default | Could leave device | Consent needed before public release | Must be redacted in reports | Never commit |
| --- | --- | --- | --- | --- | --- |
| `audit.log` | yes | no, unless user exports | yes for diagnostic sharing | yes | yes |
| `bridge-audit.log` | yes | no, unless user exports | yes for diagnostic sharing | yes | yes |
| Agent traces | yes, feature-flagged | only if user exports/uploads | yes | yes | yes |
| Eval reports | yes | only if manually shared | yes when derived from user data | yes | yes |
| Memory DB | yes | no, unless backup/sync is added | yes for backup/sync/export | yes | yes |
| OS drafts | yes, external OS | no, unless user exports | yes for sharing | yes | yes |
| Hermes logs | yes, external/local | possible if gateway is configured | yes | yes | yes |
| Voice/STT transcripts | yes unless cloud STT is enabled | yes when cloud provider is used | yes | yes | yes |
| Clipboard history | yes, explicit reveal only | no, unless shared | yes | yes | yes |
| Screenshots/Vision input | yes unless cloud vision is enabled | yes when cloud provider is used | yes | yes | yes |
| Website auth/subscription data | website/provider scoped | yes to Supabase/Stripe | yes | yes | no secrets ever |

## PublicRelease Blockers

- No user-facing consent model for traces, diagnostics, voice/STT, screenshots/vision, or optional provider use is finalized.
- No privacy UI exists for trace/log opt-in, opt-out, export, or deletion.
- Log retention and rotation policy is not fully productized for all local logs.
- Trace sampling is feature-flagged and redacted, but public consent rules are not approved.
- Public release notes do not yet explain what stays local and what may use external providers.

## Required Review Before PublicRelease

1. Define the default privacy posture for diagnostics, traces, eval reports, memory, OS drafts, Hermes logs, voice/STT transcripts, clipboard access, and screenshots.
2. Define which features are local-only, which are provider-backed, and which require explicit opt-in.
3. Confirm redaction rules for tokens, API keys, bearer strings, clipboard contents, memory contents, OS contents, conversations, and tool arguments.
4. Confirm log retention, rotation, export, and deletion behavior.
5. Confirm that eval, trace, dashboard, installer, and smoke artifacts are never committed.
6. Confirm that public website auth/subscription data is handled by the approved website release target.
7. Record release-owner approval before `PublicRelease`.

## Current Phase 5A Status

- Checklist exists.
- No consent model is approved.
- InternalRC may continue with warnings because checks are local and no telemetry is enabled.
- PublicRC is mainly blocked by CI, signing, installer, website, and OS review.
- PublicRelease remains blocked by privacy/trace consent until this checklist is reviewed and approved.

## Phase 5B Concrete Decisions Needed

| Topic | Current default | PublicRC need | PublicRelease blocker if missing |
| --- | --- | --- | --- |
| Local diagnostic logs | Local only, never committed | Explain in release notes for testers | Retention/export/delete policy not approved |
| Agent traces | Feature-flagged, redacted, local | Review whether testers may opt in | No trace opt-in/opt-out model |
| Eval reports | Synthetic/offline by default | Ensure no user-derived reports are shared | No rule for user-derived eval evidence |
| Memory and OS data | Local/external, not committed | Confirm no automatic sharing | No export/delete/backup consent policy |
| Voice/STT and screenshots | Provider-dependent if enabled | Require explicit feature consent before broad testing | No provider-use consent language |
| Clipboard access | Explicit reveal only | Keep explicit and auditable | No clipboard privacy language |
| Website auth/subscription | Provider scoped | Covered by website release target | Website privacy docs not approved |

Agent can help by keeping redaction, local-only defaults, artifact scans, and docs accurate. User/release owner must approve consent language, retention duration, provider-use defaults, export/delete expectations, and public privacy documentation.

PublicRelease remains blocked until the approval is recorded. InternalRC can proceed with warnings because these checks do not enable telemetry or external trace sharing.

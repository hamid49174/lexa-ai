# Windows Signing Plan

Phase 4D status: Lexa can build an Electron installer locally, but the installer is unsigned. Unsigned installers are acceptable for development smoke checks and InternalRC review, not for PublicRC or PublicRelease.

## Current State

- Electron packaging is configured through `frontend/electron-builder.json`.
- Local packaging smoke can create an NSIS installer.
- Installer smoke verifies artifact presence, size, and forbidden content.
- Code signing is not configured.
- No certificate, key, password, or signing secret exists in the repository.
- Phase 4E prepares the signing gates without adding keys or certificates.

## Risks

- Windows SmartScreen warnings are expected for unsigned installers.
- Users cannot verify publisher identity.
- Auto-update and distribution trust are incomplete until signing is configured.
- Signing keys in Git would be a critical security incident.

## Target Model

- Obtain a Windows code signing certificate from a trusted CA.
- Store signing secrets only in a protected secret store, never in Git.
- Use separate unsigned dev builds and signed release builds.
- CI signing must run only on protected branches or release tags.
- CI signing must require explicit release approval.
- Local test signing may use a disposable test certificate, also outside Git.

## Repository Rules

Never commit:

- `.pfx`, `.p12`, `.pem`, or private `.key` files
- certificate passwords
- signing environment files
- code-signing service tokens
- release upload tokens

The risky artifact check blocks common signing key file extensions and signing config files that look secret-bearing.

Phase 4E extends this blocklist to certificate/keystore/signing-password patterns such as `.pfx`, `.p12`, `.pem`, `.key`, `.pvk`, `.cer`, `.crt`, `.spc`, `.jks`, `.keystore`, `CSC_KEY_PASSWORD`, `CSC_LINK`, `WIN_CSC_LINK`, and `signtool` password-style variables.

## Release Gate

Release tier policy:

- Dev build: unsigned is allowed.
- InternalRC: unsigned is allowed only with a clear warning.
- PublicRC: signing is required and unsigned installers are blocking.
- PublicRelease: signing is required, installer install/uninstall must be proven, and release signing must be reviewed.

Before a public release:

1. Packaging smoke must pass.
2. Installer smoke must pass.
3. VM install/uninstall smoke must pass.
4. Signing configuration must be reviewed.
5. The installer must be signed.
6. The signed installer must be scanned for user data and secrets.

Until then, signing remains a release-review warning for InternalRC and a blocking gate for PublicRC/PublicRelease.

## Script Support

`scripts\run_installer_smoke.ps1` supports:

- `-Target InternalRC|PublicRC|PublicRelease`
- `-ExpectedPublisher <publisher-fragment>`
- `-AllowUnsignedInternal`

`scripts\run_release_candidate_check.ps1` performs a best-effort installer signing status check from the active artifact root. PublicRC/PublicRelease are blocked when the status is anything other than `signed`.

Phase 4F readiness:

- signing remains a non-code external prerequisite
- `scripts\check_risky_artifacts.ps1` blocks common signing key, certificate, keystore, and password patterns from staged files and scan paths
- `scripts\run_installer_smoke.ps1 -Target PublicRC` and `-Target PublicRelease` block unsigned or unknown signing status
- `scripts\run_release_candidate_check.ps1` reports signing as a `[Signing]` finding with a concrete next action and external prerequisite

## Phase 5A Signing Checklist

Before PublicRC:

1. Select a Windows code signing certificate type and provider.
2. Store the certificate and passphrase outside Git.
3. Decide whether signing happens locally from a secure store or in GitHub Actions with protected secrets.
4. If CI signing is used, add secrets only after remote CI exists and protected branch/tag rules are configured.
5. Configure `electron-builder` signing without committing `.pfx`, `.p12`, `.pem`, `.key`, `.crt`, passphrases, or signing env files.
6. Rebuild in an isolated packaging smoke.
7. Verify the installer signature with `Get-AuthenticodeSignature`.
8. Run `scripts\run_installer_smoke.ps1 -Target PublicRC -ExpectedPublisher <expected-name>`.
9. Run `scripts\check_risky_artifacts.ps1` before staging or release review.

Phase 5A decision: no certificate, key, passphrase, or signing secret is created in this repository. Signing remains an external blocker for PublicRC/PublicRelease.

## Phase 5B Signing Decision Checklist

Signing is ready to be decided, not performed in this repository.

Required decisions before PublicRC:

1. Certificate type: OV or EV Windows code signing certificate.
2. Certificate owner: release owner or company-controlled account.
3. Secret storage: local secure store or GitHub Secrets only after remote CI and protected branch/tag rules exist.
4. CI variables if used: `CSC_LINK`, `CSC_KEY_PASSWORD`, and any provider-specific token must be secret-scoped and never committed.
5. Local test signing: allowed only from a secure local store with no cert/key copied into the repo.
6. Verification: `Get-AuthenticodeSignature <installer>` must return a valid signer matching the expected publisher.
7. PublicRC gate: `scripts\run_installer_smoke.ps1 -Target PublicRC -ExpectedPublisher <name>` must pass.

Still forbidden:

- `.pfx`, `.p12`, `.pem`, `.key`, `.pvk`, private `.crt`/`.cer`, keystores, passphrases, signing env files, or signtool password commands in Git
- signing from an unprotected branch
- release signing before artifact scans and installer VM proof are complete

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

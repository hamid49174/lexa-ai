# Installer Smoke

The installer smoke checks an already-built installer artifact without installing it into the productive machine.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <artifact-dir>
```

Behavior:

- finds `.exe`, `.msi`, or `.msix` artifacts
- checks size is plausible
- scans the artifact directory for forbidden local data and secret-like paths
- reports signing status as `signed`, `unsigned`, or `unknown`
- does not install into the productive environment
- does not delete artifacts
- can prepare VM-only install/uninstall proof flags without executing a productive install
- supports `-PlanOnly` for a documented VM/sandbox procedure
- supports `-InstallerPath` to validate a specific generated artifact
- supports `-Target InternalRC|PublicRC|PublicRelease`
- supports `-ExpectedPublisher` for signed installers
- supports `-AllowUnsignedInternal` for explicit internal unsigned builds

Strict mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <artifact-dir> -RequireInstaller
```

If no installer exists, default mode is warn-only. `-RequireInstaller` makes missing installer artifacts release-blocking.

VM-only proof plan:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <artifact-dir> -RequireInstaller -Install -Uninstall -VMOnly
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -PlanOnly
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Target InternalRC -AllowUnsignedInternal
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Target PublicRC
```

This records that install/uninstall proof is requested, but it does not perform an automatic productive install. A real install/uninstall test must be run only inside a disposable VM or sandbox with explicit human approval.

Phase 4D status: installer existence and artifact scan are supported. Real install/uninstall testing is still not yet proven until a disposable VM run is completed. InternalRC may carry this as a warning; PublicRC and PublicRelease are blocked until the VM/sandbox procedure is proven and recorded.

Phase 4E status: unsigned installers are explicitly warn-only for `InternalRC` and blocking for `PublicRC`/`PublicRelease`. `ExpectedPublisher` is checked when a valid signer certificate is present. No certificate, key, signing password, or signing secret may be placed in Git.

Phase 4F status: VM readiness is now reported from Windows Sandbox, Hyper-V, and the explicit `LEXA_INSTALLER_VM_TEST` environment marker. Absence of all three keeps installer install/uninstall as "not yet proven". The script still refuses productive-machine install/uninstall unless `-VMOnly` is supplied, and even then it prints the proof plan rather than silently installing.

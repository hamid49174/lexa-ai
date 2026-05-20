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
- documents that signing is not verified by this smoke
- does not install into the productive environment
- does not delete artifacts

Strict mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <artifact-dir> -RequireInstaller
```

If no installer exists, default mode is warn-only. `-RequireInstaller` makes missing installer artifacts release-blocking.

Phase 4B status: installer existence and artifact scan are supported. Real install/uninstall testing should happen in a disposable VM before public release.

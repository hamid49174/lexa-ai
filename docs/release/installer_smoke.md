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
- can prepare VM-only install/uninstall proof flags without executing a productive install

Strict mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <artifact-dir> -RequireInstaller
```

If no installer exists, default mode is warn-only. `-RequireInstaller` makes missing installer artifacts release-blocking.

VM-only proof plan:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <artifact-dir> -RequireInstaller -Install -Uninstall -VMOnly
```

This records that install/uninstall proof is requested, but it does not perform an automatic productive install. A real install/uninstall test must be run only inside a disposable VM or sandbox with explicit human approval.

Phase 4C status: installer existence and artifact scan are supported. Real install/uninstall testing is still not yet proven until a disposable VM run is completed.

# VM Installer Test Plan

Phase 4D status: installer install/uninstall is prepared but not proven in this workspace. Do not install Lexa into the productive machine from release-smoke scripts.

Phase 4E status: VM/Sandbox install and uninstall remain not proven from this workstation. The script can classify signing by release target and print the VM-only plan, but it still does not perform installation automatically.

Phase 4F status: installer smoke reports Windows Sandbox, Hyper-V, and `LEXA_INSTALLER_VM_TEST` marker availability. Missing VM capability is a Needs Review state, not a fake pass. PublicRC/PublicRelease remain blocked until the proof is run in a disposable environment and recorded.

Phase 5B status: this remains the executable proof plan, not proof itself. If Windows Sandbox or another disposable VM is available, the user must approve the isolated install/uninstall run and record the evidence. Without that approval/evidence, PublicRC/PublicRelease stay blocked.

## Goal

Prove that a generated Windows installer can install, launch, and uninstall Lexa in an isolated environment without bundling user data, OS vault data, secrets, logs, or local workspaces.

## Required Environment

- disposable Windows VM or Windows Sandbox
- no real Lexa user data
- no real `personal_os/`
- no real `lexa_memory.db`
- no real `hermes_workspace/`
- no signing keys or secrets copied into the VM

## Procedure

1. Build installer in an isolated local output path:

   ```powershell
   scripts\run_packaging_smoke.ps1 -Build
   ```

2. Copy only the generated installer into the disposable VM/sandbox.
3. Install Lexa AI.
4. Launch Lexa once.
5. Run startup checks against isolated userData:
   - app starts
   - no main-process error popup
   - no EPIPE
   - preload loads
   - read-only health/status works
   - high-risk call without presence is blocked
6. Uninstall Lexa AI.
7. Check leftover files are limited to expected userData paths and contain no bundled secrets.
8. Destroy or revert the VM/sandbox.

## Release Impact

- InternalRC: VM install/uninstall not proven is warn-only.
- PublicRC: VM install/uninstall not proven is blocking.
- PublicRelease: VM install/uninstall not proven is blocking.

## Script Support

Use plan mode locally:

```powershell
scripts\run_installer_smoke.ps1 -PlanOnly
```

Use VM-only mode inside an approved disposable VM/sandbox:

```powershell
scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Install -Uninstall -VMOnly
scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Target InternalRC -AllowUnsignedInternal
scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Target PublicRC -ExpectedPublisher "Lexa"
```

The script intentionally does not automate productive-machine installation.

## Evidence Required For PublicRC

- exact installer file or build identifier
- disposable VM/Sandbox identity
- install completed
- app launched with isolated userData
- startup health smoke passed
- uninstall completed
- leftover review completed
- signing status recorded
- no bundled `.env`, user data, memory DB, OS vault data, Hermes workspace, traces, eval reports, or private logs

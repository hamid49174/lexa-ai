# Agent Context Strategy

This document defines how Codex should bootstrap project context without reading private Personal OS or Obsidian data.

## Primary Sources

Use these first:

1. `AGENTS.md`
2. `docs/codex_context_pack.md`
3. `docs/dev-testing.md`
4. `docs/release/release_candidate_checklist.md`
5. The specific source/test files required by the current task

## Forbidden Context Inputs

Do not use these as automatic context-pack input:

- `personal_os/`
- `hermes_workspace/`
- `evals/results/`
- `tmp/agent_traces/`
- `lexa_memory.db*`
- `.env` or `*.env`
- build output, installers, smoke artifacts, private logs
- signing keys, certificates, passphrases, or signing config secrets
- private OS/Obsidian content

## Context Pack Generator

`scripts\generate_codex_context_pack.ps1` is the safe generator. It uses repository metadata and fixed allowlisted project facts. It must not scan the external OS mount or generated artifacts.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\generate_codex_context_pack.ps1 -Check
```

Use `-OutputPath <path>` only for a reviewed destination. Generated temporary packs must not be committed unless they are intentionally replacing the safe tracked `docs/codex_context_pack.md`.

## Release Workflow Use

For release-hardening phases, start with the context pack, then inspect only the scripts, docs, and tests relevant to the requested release blocker. Keep facts, assumptions, decisions, evidence, risks, and tasks separate in the final report.

For PublicRC work, read `docs/release/public_rc_blocker_matrix.md` after the context pack. It separates code-solvable checks from external prerequisites such as GitHub remote access, VM proof, signing certificates, website ownership, and OS cleanup review.

For PublicRelease work, also read `docs/release/privacy_trace_consent_checklist.md`. It is a review checklist, not approval; do not treat PublicRelease privacy/trace consent as complete until the release owner explicitly approves it.

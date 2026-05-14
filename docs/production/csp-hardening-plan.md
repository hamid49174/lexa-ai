# CSP Hardening Plan

## Current State

`frontend/src/index.html` now uses:

```text
style-src 'self' https://fonts.googleapis.com
```

The app-owned static and dynamic inline style blockers have been migrated to CSS classes and bounded class buckets.

## Why `unsafe-inline` Cannot Be Removed Blindly

`unsafe-inline` was removed only after migrating these previously blocking patterns:

- static `style=""` usage in `index.html`
- show/hide and validation state writes
- modal layout `cssText` blocks
- runtime progress widths and chart heights
- dashboard/system metric colors and backgrounds
- chat input reset and snippet autocomplete positioning

Future frontend work should keep dynamic presentation in CSS classes, `data-*` attributes, or tightly bounded class buckets rather than writing inline styles.

## Migration Strategy

### Phase 1: Static HTML
- [x] Remove static inline `style=""` usage from `index.html`.

### Phase 2: Utility Classes
- [x] Replace Settings show/hide writes with `.hidden`.
- [x] Replace Settings font-size writes with `data-font-size`.
- [x] Replace Settings trial progress inline width with bounded CSS classes.
- [x] Replace Memory modal and button style writes with CSS classes.
- [x] Replace Productivity modal, button, and progress style writes with CSS classes.
- [x] Replace Modals validation and onboarding result style writes with CSS classes.
- [x] Replace Dashboard/System metric styles with CSS classes.
- [x] Replace Chat input reset and autocomplete positioning with CSS classes.

### Phase 3: Bounded Dynamic Presentation
- [x] Replace dynamic width/height/color/background assignments with known CSS classes.
- [x] Keep runtime values constrained to validated percent buckets or known status tokens.

### Phase 4: Harden CSP
- [x] Remove `'unsafe-inline'`.
- [x] Run static CSP/style scan.
- [x] Run chat rendering tests.
- [x] Run backend health smoke test.
- [ ] Run Electron smoke test.
- [ ] Manually verify Dashboard, Chat, Commands, Productivity, Memory, Settings, and Voice UI.

## Priority Order

1. Electron smoke test with the hardened CSP.
2. Manual UI pass across Dashboard, Chat, Commands, Productivity, Memory, Settings, and Voice.
3. Keep `tests/test_csp_static.py` green to prevent inline style and `unsafe-inline` regressions.

## Acceptance

The CSP change is complete only when:

- `rg -n "style=|<style|unsafe-inline|on[a-z]+=" frontend/src/index.html frontend/src -S` has no true CSP blockers.
- `venv\Scripts\python.exe -m pytest tests\test_csp_static.py -q -p no:cacheprovider` passes.
- UI smoke testing confirms no broken views.
- `node tests/test_chat_rendering.js` remains green.

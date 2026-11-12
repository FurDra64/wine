---
name: hold
about: HOLD判定の記録用。理由と解除条件を明記する
title: "[hold] <対象>"
labels: ["hold"]
assignees: []
---

## Hold notice

- Target: `<!-- patchset / fork / plan name -->`
- Date (UTC): `<!-- YYYY-MM-DDTHH:MM:SSZ -->`
- Related issues: `<!-- #NNN, #MMM -->`
- Related pins or patchset: `<!-- e.g. patches/valve-mf/ -->`

## Reason

```text
<!-- why this target is on hold (test failure, upstream conflict, scope mismatch) -->
```

## Reopen condition

- [ ] `<!-- condition 1, e.g. upstream fixes mf.c:8671 -->`
- [ ] `<!-- condition 2, e.g. --check passes on new base -->`
- [ ] Reviewer sign off before reactivation

## Repair (human or AI agent)

```bash
./scripts/apply-patches.sh --check   # confirms hold scope still fails or passes
```

1. Keep HOLD content out of tree (inventory plus raw export only, never active `patches/` entries on wrong base).
2. Recheck on each upstream move and paste the new result into a comment.
3. Reopen only when every box above is checked.

## Safety

- Hold branches are disposable (`cattle`); `master`/`upstream` are not.
- Do not activate old base patches on a new upstream to clear HOLD.

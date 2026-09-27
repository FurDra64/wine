# PROJECT KNOWLEDGE BASE

**Generated:** 2026-09-27
**Branch model:** `upstream` (pristine) + `master` (upstream + overlay)

## OVERVIEW

Personal Wine fork: upstream Wine + custom patchsets under `patches/`,
applied at build time. Daily GitHub Actions tracking of upstream.

## STRUCTURE

```
./
├── patches/    # custom patchsets (1 feature = 1 dir) + series.conf
├── scripts/    # apply-patches.sh, new-patchset.sh (CUSTOM, upstream never touches)
├── .github/    # upstream-sync.yml (daily fetch + dry-run + conflict Issue)
├── docs/       # AI-OPERATIONS.md runbook
├── tools/      # UPSTREAM-OWNED (Wine's own). Do NOT add custom files here.
├── dlls/ programs/ server/ ...  # UPSTREAM-OWNED. Never edit directly.
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add/change a patch | `patches/<name>/` | see `patches/AGENTS.md` |
| Apply/check logic | `scripts/apply-patches.sh` | see `scripts/AGENTS.md` |
| Sync workflow | `.github/workflows/upstream-sync.yml` | see `.github/AGENTS.md` |
| Daily operation | `docs/AI-OPERATIONS.md` | runbook for humans + AI |
| Wine source | `dlls/`, `programs/`, `server/` | read-only reference |

## OWNERSHIP BOUNDARY

- Custom-owned: `patches/`, `scripts/`, `.github/`, `docs/`, root `AGENTS.md`.
  Merge from `upstream` never touches these (upstream has no such paths).
- Upstream-owned: everything else. Edits here belong in a patchset,
  never as direct commits — unisolated changes cannot be rebased.

## CONVENTIONS

- Shell: `set -euo pipefail`, `--long-flags`, LF, no `.orig`/`.rej` litter
  (`--no-backup-if-mismatch`). Must pass `shellcheck`.
- YAML: pin actions to `@vN` major, `cancel-in-progress: false` for sync jobs.
- Patches: `-p1`, LF, numbered `NNNN-*.patch`, sorted apply.
- EditorConfig: 4 spaces (Makefiles: tabs). Max line 100.

## ANTI-PATTERNS (THIS PROJECT)

- Direct Wine source edits on `master` for changes that belong in `patches/`.
- Custom files inside upstream-owned dirs (`tools/`, `dlls/`, ...).
- `git push --force` on `master`/`upstream` (conflict branches only).
- Rebuilding per stage / committing build artifacts or secrets.
- `[skip ci]` in messages — use path filters instead.
- Deleting a failing patch to "pass" — fix or upstream it.

## COMMANDS

```bash
scripts/apply-patches.sh --check   # dry-run all patchsets
scripts/apply-patches.sh --list    # resolved order
scripts/new-patchset.sh <name>     # scaffold patches/<name>/
```

## NOTES

- Upstream remote: `wine-mirror/wine` on GitHub (1-line switch to
  `gitlab.winehq.org/wine/wine.git` when freshness matters).
- Merge conflicts on sync mean overlay touched an upstream path — fix by hand.
- Patch conflicts mean upstream moved — fix the `.patch` files, see runbook.

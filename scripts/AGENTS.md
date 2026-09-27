# scripts/ — custom automation (upstream never touches this dir)

## OVERVIEW

`apply-patches.sh` is the contract: CLI flags, exit codes, `FAILED` lines.
Workflow and humans both call it; keep it dependency-free (bash+patch/git).

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Apply/check engine | `apply-patches.sh` |
| Scaffold helper | `new-patchset.sh` |

## CONVENTIONS

- `set -euo pipefail`; long flags; `usage()` on `--help`.
- Failure line format (grepable by CI): `FAILED patchset=<name> file=<file>`.
- `--check` must leave the tree untouched (dry-run flags only).
- New flags stay backward-compatible (long-lived CLI).

## ANTI-PATTERNS

- New runtime dependencies (no python/node — must run on bare runners).
- Silent skip on re-apply (double-apply must fail loudly, not false-green).
- Writing outside `--destdir`.

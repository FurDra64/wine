# .github/ — CI (upstream tracking only)

## OVERVIEW

`workflows/upstream-sync.yml`: daily fetch → FF `upstream` → merge to
`master` → patch dry-run → push, or conflict branch + Issue.

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Sync job | `workflows/upstream-sync.yml` |
| Failure logs | `sync.log` artifact (14-day retention) |

## CONVENTIONS

- Cheap gate before push: dry-run passes or nothing is pushed.
- `cancel-in-progress: false`; full clone (`fetch-depth: 0`).
- Issue per upstream SHA (comment on existing, don't duplicate).
- `workflow_dispatch` with `dry_run` input for safe rehearsal.

## ANTI-PATTERNS

- Force-pushing `master`/`upstream` from any job.
- Auto-merging the conflict fix PR (human or verified AI reviews).
- Adding build jobs here — sync is fetch+check only (cheap→expensive).

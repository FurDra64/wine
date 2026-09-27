# AI-OPERATIONS — runbook for humans + AI agents

How to live with this repo day to day. Read before touching anything.

## Mental model (from project knowledge)

- `upstream` branch = pristine upstream, only the sync workflow moves it.
- `master` = `upstream` + overlay (`patches/`, `scripts/`, `.github/`, `docs/`).
  Wine source files on `master` are byte-identical to `upstream`.
- Patches live as files, applied at build time — never as tree edits.
  So merges never conflict; only patch application can fail, and the
  dry-run catches it before anything is pushed.

## Add a patch

```bash
scripts/new-patchset.sh my-feature
# 1. Fill in patches/my-feature/definition (Description, Upstream-Status).
# 2. Hack on a scratch copy, then:
git diff > patches/my-feature/0001-what-it-does.patch
rm patches/my-feature/0001-TODO.patch   # remove the stub
# 3. Verify:
scripts/apply-patches.sh --check
```

One patchset = one concern. If it can't be dropped independently, split it.

## Daily sync (automatic)

`upstream-sync.yml` runs 03:00 UTC + on manual dispatch.
Success → `upstream` + `master` pushed. Nothing to do.

## Conflict repair (Issue arrives with label `upstream-conflict`)

```bash
git fetch origin
git checkout conflict/<date>-<sha>   # from the Issue
./scripts/apply-patches.sh --check   # reproduces the failure
```

1. Fix the `.patch` hunks in `patches/<failed-name>/` (rebase onto new upstream).
2. If upstream accepted the change upstream, delete the patchset dir +
   its `series.conf` line instead (record the upstream commit in the PR text).
3. `--check` must print `check passed`.
4. Push to the conflict branch, open PR to `master`. One patchset per commit.
5. CI re-runs the check on the PR.

## Safety invariants (non-negotiable)

- Never `push --force` on `master` or `upstream`. Conflict branches are
  disposable; shared branches are not.
- Never edit Wine source on `master` — fix the `.patch` files.
- Never delete a failing patch to "pass". Fix it or upstream it.
- Verify by running (`--check`, real apply in a scratch worktree), not by reading.
- Small batches: rebase one patchset per commit so bisect keeps working.
- `workflow_dispatch` with `dry_run: true` exists — rehearse workflow
  edits there before they run on schedule.
- Secrets: none needed (public upstream fetch). Never echo tokens in logs.

## Switching upstream to GitLab (when freshness matters)

One line in `upstream-sync.yml` env + dispatch input default:

```
https://gitlab.winehq.org/wine/wine.git
```

Everything else (branches, script, Issue flow) is URL-agnostic.

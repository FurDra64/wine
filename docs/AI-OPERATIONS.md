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

## Retarget after upstream moves

Run this first, before fixing any patch by hand:

```bash
python scripts/retarget-patches.py --report retarget.md --json retarget.json [--write]
python scripts/tests/test_retarget_patches.py   # self-test on synthetic repos
```

The defaults are `--old-base $(git merge-base HEAD mirror/master)` and
`--new-base mirror/master`. The tool replays the stack twice in temporary
indexes, using only git plumbing (no checkout). The stack must be strict-green
on the old base. On the new base, a patch that fails strict apply is merged
3-way with `git merge-tree`.

- `OK`: the patch applies strictly. Its file is never touched.
- `RETARGETED`: the 3-way merge was clean and the tool regenerated the diff
  body. The header and trailer are kept. `--write` rewrites only these files.
  Review them anyway, because a clean merge does not prove the code is right.
  If the report says the hunks shrank, upstream took part of the change.
  `generated` means the tool reran `tools/make_requests`, which raises
  `SERVER_PROTOCOL_VERSION` by one per patch. A RETARGETED patch is
  `provisional` when it touches files of a skipped patch. The tool does not
  write it unless you pass `--write-provisional`, because its context may
  change once that earlier patch is fixed.
- `ABSORBED`: upstream already contains the whole change. The report gives
  the evidence commit found with `git log -S` and the `# OBSOLETE ...`
  series.conf line to use. Retiring the patch is still a human decision
  (GOVERNANCE R1).
- `CONFLICT` and `BLOCKED-BY:<patch>`: these patches are left for a human or
  AI to fix. A `BLOCKED-BY` patch conflicts in files that an earlier failed
  patch touches. Fix that earlier patch first, then rerun the tool.

Exit codes:

- 0: the gate will pass once the RETARGETED files are written.
- 1: CONFLICT, BLOCKED-BY, ABSORBED or OLD-FAIL patches remain. An ABSORBED
  patch still fails the gate until a human retires it.
- 2: usage or precondition error.
- 3: unexpected internal error.

The tool deletes old `--json` and `--report` files when it starts, and writes
patch files only after every rewrite has been verified.
`scripts/apply-patches.sh --check` is still the gate. The tool applies patches in
byte (C) order. The report has a WARN section that lists patchsets whose order
would differ under a locale-aware glob sort.

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

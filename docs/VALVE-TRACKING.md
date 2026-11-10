# VALVE-TRACKING — Valve downstream tracking (bleeding-edge line)

How Valve Wine is tracked from this repo without ever downgrading `master`.
Read `docs/AI-OPERATIONS.md` first for the overlay mental model.

## Branch / base choice (2026-11-01, user-selected)

- Tracking target: ValveSoftware/wine `bleeding-edge`,
  pinned tip `fda79a585939fb7512dc220a11249f9ffe825fcf` (2026-09-23).
- Valve delta base: Wine 11.0 `db11d0fe6a169c457e23d007e20404643d067aa8`
  (2026-01-13; byte-identical to wine-mirror tag `wine-11.0`).
- Integration base: Wine 11.21 `2528aff26208257fdbf980666a4f0e66d47563ce`
  (= local `upstream` at the time of the snapshot).
- Note: Valve's own default branch is `proton_11.0`, but the user explicitly
  selected `bleeding-edge` (= `experimental_11.0` + 13 commits). The three
  Valve lines share everything up to `dc26e61847`; `proton_11.0` diverges by
  1 commit vs 453 on the experimental side. Re-tracking a different line is
  a `--ref`/`--source` flag change, not a rewrite.

## Scale (measured, not estimated)

- `BASE..SOURCE`: **1919 commits**, 916 files, +418560/−144609 lines.
- Upstream moved `BASE..UPSTREAM`: 5315 commits (11.0 → 11.21).
- Patch-id equivalence (`git cherry`): 554 Valve commits already have an
  upstream equivalent, **1365 are Valve-unique**. "Already upstream" is a
  patch-content statement, not a merge claim.
- The range contains exactly one empty commit (`7b3ceaf`, `amend! fixup!`
  placeholder). Export/verify tooling round-trips it (`--empty=keep`).
- Never diff `UPSTREAM..SOURCE` and call it "Valve patches": that diff is
  dominated by upstream rollback 11.21 → 11.0. The only valid Valve delta
  is `BASE..SOURCE`.

## Port conflict boundary (proven, 11.21 + bleeding-edge)

- Preliminary: `git merge-tree --write-tree --name-only --no-messages
  UPSTREAM SOURCE` → **235 conflicted files** (of 916 Valve files).
- Concrete: isolated worktree at 11.21 + `git merge --no-commit --no-ff
  SOURCE` fails the same way: 206 `UU` + 12 `UD` + 6 `DU` + 11 `AA`
  = 235 unmerged paths; 343 cleanly merged, 69 cleanly added.
- The stored `docs/valve/conflicts-11.21-vs-bleeding.txt` is that file list
  (one path per line). It is a snapshot against 11.21, not a fix list.
- Consequence: no silent full-stack forward-port exists. A real port means
  resolving 235 files across `dlls` (majority), `server`, `include`,
  `programs`, `tools` — per-feature patchsets only, each verified on 11.21.
  Until then, Valve content ships as inventory + out-of-tree raw export,
  never as active `patches/` entries (old-base patches must not be
  activated on 11.21).

## Tooling (`scripts/valve-track.sh`, shell-only)

```
scripts/valve-track.sh --show-pins
scripts/valve-track.sh --pins docs/valve/pins.conf --check-pins
scripts/valve-track.sh --pins docs/valve/pins.conf --inventory /tmp/inv.tsv
scripts/valve-track.sh --pins docs/valve/pins.conf --export /tmp/valve-raw
scripts/valve-track.sh --pins docs/valve/pins.conf --verify /tmp/valve-raw
scripts/valve-track.sh --pins docs/valve/pins.conf --conflicts /tmp/conf.txt
scripts/valve-track.sh --fetch   # read-only: REF -> refs/task/valve/<name>
```

- Deterministic: repeated `--inventory`/`--export` are byte-identical
  (no timestamps in outputs; source-date comes from the pinned commit).
- `--export` refuses non-empty dirs (generations never mix silently).
- `--verify` replays the export onto BASE in an isolated worktree with
  `git am --empty=keep` (no `--whitespace=fix`: whitespace fixing mutates
  blobs and breaks tree equality) and requires
  `HEAD^{tree} == SOURCE^{tree}`. Proven 2026-11-01:
  tree `57167af0ac6f80ce7865ed7c52c6493091358a29`, 1919 patches.
- Authorship/provenance preserved: `format-patch`/`am` keep Author/Date;
  inventory records author + date + subject per commit.
- Behavioral tests: `scripts/valve-track-selftest.sh` (local fixture:
  idempotent export, update growth, stale-export rejection, empty-commit
  round-trip, whitespace round-trip, empty-range handling, ancestor gate,
  corrupt-export rejection, pins validation, CLI-over-pins order,
  ref/injection rejection, fetch no-change/advance/rewrite + path
  preservation + shared-refs-untouched, worktree cleanup). 38/38 green.
- Range gates: a BASE that is not an ancestor of SOURCE fails
  `--check-pins`/`--inventory`/`--export`/`--verify`/`--conflicts` before
  anything is emitted; an empty range (BASE == SOURCE) exports zero patches
  and verifies as an identical tree.
- `--fetch` force-updates ONLY `refs/task/valve/<full REF path>` (rewrites
  reported as `rewritten`, never silently fast-forwarded); shared branches
  are never written. Full REF paths are preserved (`feature/a` vs `other/a`
  never collide); malformed refs are rejected via `git check-ref-format`
  and leading-dash remotes/refs are refused (option-injection safe).
- Full history required: the repo must be unshallowed for merge-base and
  `git cherry` to work (`git fetch --unshallow` once; done 2026-11-01).

## Update procedure (Valve ref moved)

```bash
scripts/valve-track.sh --fetch   # force-updates refs/task/valve/<name> only
scripts/valve-track.sh --source refs/task/valve/<name> --upstream origin/upstream --check-pins
scripts/valve-track.sh --source refs/task/valve/<name> --inventory /tmp/inv.tsv
scripts/valve-track.sh --source refs/task/valve/<name> --upstream origin/upstream --conflicts /tmp/conf.txt
scripts/valve-track.sh --source refs/task/valve/<name> --export /tmp/valve-raw-new
scripts/valve-track.sh --source refs/task/valve/<name> --verify /tmp/valve-raw-new
```

Then hand-edit `docs/valve/pins.conf` (new SOURCE date/SHA), replace the
stored inventory/conflict snapshots, and report the new conflict count.
Small batches, no force-pushes, no direct Wine source edits — same
invariants as `AI-OPERATIONS.md`.

Pin refresh model: `docs/valve/pins.conf` is the single default source —
with no flags the CLI resolves BASE/SOURCE/UPSTREAM/REMOTE/REF from it,
so editing pins.conf changes default CLI behavior. `--pins FILE`
selects another file; any CLI flag overrides pins regardless of flag
order. A live ref passed via `--source` overrides the pinned SOURCE for
live reconstruction while the recorded snapshot stays immutable; likewise
`origin/upstream` (live) is distinct from the pinned UPSTREAM snapshot.
CI never greps pins.conf raw: a resolve step maps the authoritative
`--show-pins` output (which already applies pins whitespace rules) into
`VALVE_URL/VALVE_REF/VALVE_BASE/PINNED_SOURCE/PINNED_UPSTREAM` env vars,
and all later steps use only those.

## Forward-port integration (2026-11-10, Wine 11.21 + bleeding-edge)

- 12 valve groups ported to PRIMARY (`patches/valve-*/`, media-foundation
  HOLD: transform B 11 vs A 4 + `mf.c:8671` B-only hard failure).
- `patches/series.conf` 30 lines (5 existing + 12 valve appended, order match).
- Staged trees: valve-only
  `1254256910edbbbcc41a380ebde6b7f6f666e1de`, final
  `f11942beb313c5a61d844b3f5e4fd9599b01f157`.
- B-GL root cause: experimental framebuffer wrap in
  `get_window_unused_drawable()` (`dlls/win32u/opengl.c`); `emulate_modeset=TRUE`
  forced by Valve sysparams; never fires under Gamescope via steamcompmgr.
  Fix adopted in SOURCE (wrap bypass + comment), wrap lines 314→0.
- Evidence: `export-fixes-02/` (manifests 12546 each, replay13 14L OK,
  replay5 8L OK, cumulative `--check` 18 patchsets / 22 files PASS, negative
  FAIL OK), PRIMARY `--check --backend git-apply` 17 patchsets / 21 files PASS.

## CI (`valve-track.yml`, read-only)

Daily (04:00 UTC — Valve tips move any day) + manual dispatch. All steps
run under `bash -euo pipefail` (job default shell), so a tracking failure
piped through `tee` still fails the step — no false greens. Flow: syntax
gates + fixture selftest, resolve values from pins.conf, explicit
`origin/upstream` fetch (fresh checkouts have no local `upstream` branch),
live Valve fetch into the private task ref, check-pins, inventory,
conflicts, export + reconstruction verify into `$RUNNER_TEMP` (cleaned by
a final always-step), overlay `--check`, drift evaluation, artifact upload
(14-day retention), drift gate, cleanup. Drift compares live vs pinned for
BOTH source (`unchanged/appended/rewritten/unknown`) and upstream
(`unchanged/advanced/rewritten/unknown`) with exact SHAs in the step
summary; the gate is nonzero when either moved — source-unchanged never
claims "no review needed" while upstream moved. The summary separates
source-data reconstruction (VERIFY_OK) from integration (CONFLICT_FILES
at the live upstream). Permissions `contents: read`. No pushes, no
issues, no PRs, no external messages, no auto-merge.

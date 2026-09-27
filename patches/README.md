# patches/

Custom patchsets applied on top of upstream Wine.
`master` tree stays clean (upstream files + overlay only);
patches are applied at build/test time, never committed as edits.

## Layout (staging-style, Proton-GE compatible thinking)

```
patches/
  series.conf          # apply order, one <name> per line
  <name>/              # one feature = one directory
    definition         # metadata (required)
    0001-*.patch ...   # unified diffs, -p1, sorted apply
  _example/            # disabled scaffold (commented out in series.conf)
```

## definition schema (v1, plain text `Key: value`)

```
Feature: short slug, same as directory name
Description: 1-2 sentences, what and why
Author: name <mail>
Upstream-Status: none | submitted <url> | accepted <commit>
Depends-On: other patchset names, comma separated (default: none)
```

`Upstream-Status` is the deprecation path: a patch accepted upstream
should be removed here (code is liability, not asset).

## Rules

- One patchset = one concern. Never mix unrelated fixes in one dir.
- Patch files: `git diff` / `git format-patch` output, `-p1` strippable,
  LF endings, no generated files (`configure`, `*.spec` outputs, etc.).
- Numbered `NNNN-*.patch`, applied in shell sort order.
- Never edit Wine source directly on `master` for a change that belongs
  in a patchset — future you cannot rebase what was never isolated.
- New patchset: `scripts/new-patchset.sh <name>` (scaffolds + registers).

## Verify

```bash
scripts/apply-patches.sh --check   # dry-run, tree untouched
scripts/apply-patches.sh --list    # resolved order after -W filters
```

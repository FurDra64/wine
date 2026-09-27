# patches/ — patchset lifecycle

## OVERVIEW

One feature = one directory. Applied top-to-bottom per `series.conf`.

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Apply order | `series.conf` |
| Format spec | `README.md` |
| New patchset | `../scripts/new-patchset.sh <name>` |
| Disabled example | `_example/` (commented out in series.conf) |

## CONVENTIONS

- Dir name: `^[a-z0-9][a-z0-9_-]*$`, matches `Feature:` in `definition`.
- `definition` keys: `Feature, Description, Author, Upstream-Status, Depends-On`.
- Patch files `NNNN-*.patch`, `-p1`, LF, no generated files.
- Disable = comment out in `series.conf`. Delete dir only when upstream
  accepted the change (`Upstream-Status: accepted <commit>`).

## ANTI-PATTERNS

- Two concerns in one patchset (split it — revertability test:
  "can this be dropped without breaking anything else?").
- Editing the Wine tree instead of the `.patch` file when fixing conflicts.
- Absolute paths or `/tmp` references inside patch content.

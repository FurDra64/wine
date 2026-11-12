# docs/forks/ — downstream fork pins, spec v1

Multiple Valve-like downstream forks share one pins format and one
resolver (`scripts/valve-track.sh`). Valve stays canonical at
`docs/valve/pins.conf`; every fork (including a future
`docs/forks/valve/pins.conf` mirror) follows this spec.

## File layout

```
docs/forks/<fork>/pins.conf   # one fork per directory, e.g. cachyos
docs/valve/pins.conf          # canonical Valve pins (not moved by v1)
```

`<fork>` is lowercase `[a-z0-9][a-z0-9-]*` (no leading dash, no `/`,
no `.`, no traversal). The resolver rejects anything else before
touching the filesystem.

## pins.conf spec v1

Byte-format is identical to `docs/valve/pins.conf`. The parser
(`load_pins` in `scripts/valve-track.sh`) is the norm:

- Exactly these five `KEY=VALUE` keys, each exactly once:
  `REMOTE`, `REF`, `BASE`, `SOURCE`, `UPSTREAM`.
- `REMOTE`: fetch URL used by `--fetch`.
- `REF`: branch name used by `--fetch` (validated with
  `git check-ref-format --branch`; must not start with `-`).
- `BASE`: Valve/CachyOS delta base commit (must be an ancestor of
  `SOURCE`; the only valid delta is `BASE..SOURCE`).
- `SOURCE`: pinned tip commit under test.
- `UPSTREAM`: integration base commit of the stored conflict snapshot.
- Lines: `#` starts a comment (stripped before parsing), blank lines
  skipped, surrounding whitespace around values trimmed.
- Errors (exit 2, nothing emitted): missing file, `no =` line, unknown
  key, duplicate key, missing key, empty value.
- Non-`KEY=VALUE` informational lines (e.g. `VALVE_ONLY=...`) must stay
  inside `#` comments — uncommented they fail as `unknown pins key`.
- Runtime line `PINS_FROM=<path|builtin-fallback>` is NOT stored in the
  file: `--show-pins` prints it first to record which file was
  resolved (or `builtin-fallback` when no file exists).

## Resolver precedence (order-independent)

1. `--pins FILE` given → load `FILE` (`PINS_FROM=FILE`).
2. Else default file from `--fork NAME` (default `valve`):
   - `valve` → `$REPO/docs/valve/pins.conf` if present (backward
     compat), else `$REPO/docs/forks/valve/pins.conf`.
   - other `<fork>` → `$REPO/docs/forks/<fork>/pins.conf`.
3. Else (no file found) → builtin Valve fallback SHAs
   (`PINS_FROM=builtin-fallback`, last resort for fixtures only).
4. Any CLI flag (`--base/--source/--upstream/--remote/--ref`)
   overrides the resolved file regardless of flag order.

CI never greps pins.conf raw: resolve via `--show-pins` into
`VALVE_URL/VALVE_REF/VALVE_BASE/PINNED_SOURCE/PINNED_UPSTREAM`
(see `docs/VALVE-TRACKING.md`), then use only those env vars.

## Examples

Valve (canonical, `docs/valve/pins.conf` — values MUST NOT change in v1):

```
REMOTE=https://github.com/ValveSoftware/wine.git
REF=bleeding-edge
BASE=db11d0fe6a169c457e23d007e20404643d067aa8
SOURCE=fda79a585939fb7512dc220a11249f9ffe825fcf
UPSTREAM=2528aff26208257fdbf980666a4f0e66d47563ce
```

Future CachyOS (`docs/forks/cachyos/pins.conf`, same five keys):

```
REMOTE=https://github.com/CachyOS/wine-cachyos.git
REF=cachyos_11.0_release
BASE=<wine-11.0 base SHA>
SOURCE=<pinned cachyos tip SHA>
UPSTREAM=<integration base SHA>
```

(`REF` tracks the `cachyos_11.0_release`/`dev` line; exact branch name
is chosen at bring-up. Until then the directory need not exist —
the resolver reports `pins file not found` via `--pins`, or falls
back to builtin Valve SHAs for the default path, never silently
mixing forks.)

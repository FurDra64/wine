---
name: port
about: 下流forkからの移植 (patchset化) 報告用。由来と検証結果を記録する
title: "[port] <patchset名> from <由来>"
labels: ["port"]
assignees: []
---

## Port request

- Patchset name: `<!-- patches/<origin>-<feature>/ -->`
- Origin: `<!-- own / valve / ge / cachyos / staging / tkg -->`
- Source ref: `<!-- SHA or tag, ownなら - -->`
- Upstream base: `<!-- e.g. 11.21 SHA -->`
- Date (UTC): `<!-- YYYY-MM-DDTHH:MM:SSZ -->`

## Port content

```text
<!-- paste file list / --conflicts excerpt here -->
```

<details><summary>Full check log</summary>

```text
<!-- paste ./scripts/apply-patches.sh --check output (tail 80 lines) here -->
```

</details>

## Verify result

- [ ] `scripts/valve-track.sh --verify` passed (由来がValve系の場合)
- [ ] `./scripts/apply-patches.sh --check` prints `check passed`
- [ ] Series order matches `patches/series.conf`
- [ ] Ledger row added (`patchset / origin / source-ref / imported-date / upstream-status / notes`)

## Repair (human or AI agent)

```bash
./scripts/apply-patches.sh --check   # reproduces this result
```

1. Fix the `.patch` files in `patches/<name>/` (rebase hunks onto current upstream).
2. Keep one patchset per commit. Drop the patchset if upstream accepted it.
3. `./scripts/apply-patches.sh --check` must print `check passed`.

## Safety

- Conflict branches are disposable (`cattle`); `master`/`upstream` are not.
- Do not edit Wine source directly. Fix the `.patch` files.

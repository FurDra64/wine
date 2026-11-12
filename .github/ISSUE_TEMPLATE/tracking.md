---
name: tracking
about: 下流fork追従のdrift報告用。pinsの期待値と実測の差分を記録する
title: "[tracking] <fork> drift at <SHA>"
labels: ["tracking"]
assignees: []
---

## Tracking drift detected

- Target fork: `<!-- e.g. ValveSoftware/wine bleeding-edge -->`
- Expected SHA (pins.conf SOURCE): `<!-- pinned SHA -->`
- Actual SHA (live ref): `<!-- fetched SHA -->`
- Date (UTC): `<!-- YYYY-MM-DDTHH:MM:SSZ -->`
- Drift kind: `<!-- unchanged / appended / rewritten / unknown -->`
- Upstream SHA: `<!-- origin/upstream at check time -->`
- Upstream drift: `<!-- unchanged / advanced / rewritten / unknown -->`

## Drift content

```text
<!-- paste --check-pins / inventory diff / conflict count here -->
```

<details><summary>Full track log</summary>

```text
<!-- paste scripts/valve-track.sh output (tail 80 lines) here -->
```

</details>

## Repair (human or AI agent)

```bash
git fetch origin
scripts/valve-track.sh --show-pins
scripts/valve-track.sh --fetch
scripts/valve-track.sh --source refs/task/valve/<name> --inventory /tmp/inv.tsv
```

1. Confirm the live ref move (append vs rewrite) before touching `pins.conf`.
2. Update `pins.conf` SOURCE date/SHA only after export plus verify pass.
3. Replace stored inventory/conflict snapshots in the same commit.
4. Small batches: one fork pin update per commit. Never force-push `master`/`upstream`.

## Safety

- Task refs (`refs/task/valve/*`) are disposable (`cattle`); `master`/`upstream` are not.
- Do not edit Wine source directly. Fix pins and snapshots only.

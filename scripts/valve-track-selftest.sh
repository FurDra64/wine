#!/usr/bin/env bash
# Behavioral selftest for valve-track.sh using local git fixtures.
# No pinned real-world SHAs and no HOME changes: the fixtures create their
# own history and the test asserts behavior (counts grow on update, export
# is idempotent, reconstruction verifies, malformed input fails safely).
# Git is isolated via GIT_CONFIG_GLOBAL/GIT_CONFIG_NOSYSTEM plus per-repo
# local config (identity, no signing, no hooks).
#
#   scripts/valve-track-selftest.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACK="$HERE/valve-track.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/valve-selftest.XXXXXX")"
trap 'rm -rf "$ROOT"' EXIT

pass=0
fail_n=0
ok() { pass=$((pass + 1)); echo "PASS: $1"; }
bad() { fail_n=$((fail_n + 1)); echo "FAIL: $1" >&2; }

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null

new_repo() {
    git init -q -b master "$1"
    git -C "$1" config user.name "selftest"
    git -C "$1" config user.email "selftest@localhost"
    git -C "$1" config commit.gpgsign false
    git -C "$1" config core.hooksPath "$ROOT/nohooks"
}
mkdir -p "$ROOT/nohooks"

FIX="$ROOT/fixture"
new_repo "$FIX"
echo "v1" > "$FIX/a.txt"
git -C "$FIX" add a.txt
git -C "$FIX" commit -qm "base commit"
BASE_SHA="$(git -C "$FIX" rev-parse HEAD)"
echo "v2" > "$FIX/b.txt"
git -C "$FIX" add b.txt
git -C "$FIX" commit -qm "valve one"
echo "v3" >> "$FIX/a.txt"
git -C "$FIX" commit -qam "valve two"
SRC_SHA="$(git -C "$FIX" rev-parse HEAD)"

T() {
    "$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC_SHA" \
        --upstream "$BASE_SHA" "$@"
}

# 1. check-pins identifies base as merge-base and counts 2 valve commits.
out="$(T --check-pins)"
if echo "$out" | grep -q "PIN_OK"; then ok "check-pins prints PIN_OK"; else bad "check-pins prints PIN_OK"; fi
if echo "$out" | grep -q "COUNT_VALVE=2"; then ok "check-pins counts 2"; else bad "check-pins counts 2"; fi

# 2. inventory is deterministic across runs.
T --inventory "$ROOT/inv1.tsv" > /dev/null
T --inventory "$ROOT/inv2.tsv" > /dev/null
if cmp -s "$ROOT/inv1.tsv" "$ROOT/inv2.tsv"; then ok "inventory deterministic"; else bad "inventory differs"; fi
if [[ "$(grep -vc '^#' "$ROOT/inv1.tsv")" == 2 ]]; then ok "inventory has 2 commits"; else bad "inventory count"; fi

# 3. export twice is byte-identical; verify proves reconstruction.
T --export "$ROOT/exp1" > /dev/null
T --export "$ROOT/exp2" > /dev/null
if diff -r -q "$ROOT/exp1" "$ROOT/exp2" > /dev/null; then ok "export idempotent"; else bad "export differs"; fi
vout="$(T --verify "$ROOT/exp1")"
if echo "$vout" | grep -q "VERIFY_OK"; then ok "verify reconstructs source"; else bad "verify failed"; fi

# 4. changed source: advance tip, inventory grows, old export no longer verifies.
echo "v4" > "$FIX/c.txt"
git -C "$FIX" add c.txt
git -C "$FIX" commit -qm "valve three"
SRC2_SHA="$(git -C "$FIX" rev-parse HEAD)"
"$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC2_SHA" \
    --upstream "$BASE_SHA" --inventory "$ROOT/inv3.tsv" > /dev/null
if [[ "$(grep -vc '^#' "$ROOT/inv3.tsv")" == 3 ]]; then ok "update grows inventory"; else bad "inventory did not grow"; fi
if "$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC2_SHA" \
        --upstream "$BASE_SHA" --verify "$ROOT/exp1" > /dev/null 2>&1; then
    bad "stale export verified against moved source (must fail)"
else
    ok "stale export fails against moved source"
fi
"$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC2_SHA" \
    --upstream "$BASE_SHA" --export "$ROOT/exp3" > /dev/null
if "$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC2_SHA" \
        --upstream "$BASE_SHA" --verify "$ROOT/exp3" > /dev/null; then
    ok "re-export verifies after update"
else
    bad "re-export verify failed"
fi

# 4b. empty commits in range round-trip (Valve ships at least one).
git -C "$FIX" commit -q --allow-empty -m "valve empty noop"
SRC3_SHA="$(git -C "$FIX" rev-parse HEAD)"
"$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC3_SHA" \
    --upstream "$BASE_SHA" --export "$ROOT/exp4" > /dev/null
shopt -s nullglob
exp4=( "$ROOT/exp4"/*.patch )
shopt -u nullglob
if [[ "${#exp4[@]}" == 4 ]]; then ok "empty commit exported"; else bad "empty commit missing"; fi
if "$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC3_SHA" \
        --upstream "$BASE_SHA" --verify "$ROOT/exp4" > /dev/null; then
    ok "empty commit round-trips"
else
    bad "empty commit verify failed"
fi

# 4c. trailing-whitespace content round-trips exactly (past --whitespace=fix bug).
printf 'keep-trailing-space   \nsecond\n' > "$FIX/ws.txt"
git -C "$FIX" add ws.txt
git -C "$FIX" commit -qm "valve whitespace"
SRC4_SHA="$(git -C "$FIX" rev-parse HEAD)"
"$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC4_SHA" \
    --upstream "$BASE_SHA" --export "$ROOT/exp5" > /dev/null
if "$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC4_SHA" \
        --upstream "$BASE_SHA" --verify "$ROOT/exp5" > /dev/null; then
    ok "whitespace content round-trips"
else
    bad "whitespace content verify failed"
fi

# 4d. empty base..source range exports zero patches and verifies identical tree.
"$TRACK" --repo "$FIX" --base "$SRC4_SHA" --source "$SRC4_SHA" \
    --upstream "$BASE_SHA" --export "$ROOT/exp0" > /dev/null
shopt -s nullglob
exp0=( "$ROOT/exp0"/*.patch )
shopt -u nullglob
if [[ "${#exp0[@]}" == 0 ]]; then ok "empty range exports zero patches"; else bad "empty range exported patches"; fi
if "$TRACK" --repo "$FIX" --base "$SRC4_SHA" --source "$SRC4_SHA" \
        --upstream "$BASE_SHA" --verify "$ROOT/exp0" > /dev/null; then
    ok "empty range verifies identical tree"
else
    bad "empty range verify failed"
fi

# 4e. base not ancestor of source fails before emitting anything.
git -C "$FIX" checkout -q --orphan otherline
echo "other" > "$FIX/other.txt"
git -C "$FIX" add other.txt
git -C "$FIX" commit -qm "unrelated line"
OTHER_SHA="$(git -C "$FIX" rev-parse HEAD)"
git -C "$FIX" checkout -q master
if "$TRACK" --repo "$FIX" --base "$OTHER_SHA" --source "$SRC4_SHA" \
        --upstream "$BASE_SHA" --inventory "$ROOT/inv-bad.tsv" > /dev/null 2>&1; then
    bad "non-ancestor base inventory passed (must fail)"
else
    ok "non-ancestor base inventory rejected"
fi
if [[ -e "$ROOT/inv-bad.tsv" ]]; then bad "failed inventory emitted a file"; else ok "failed inventory emits nothing"; fi
if "$TRACK" --repo "$FIX" --base "$OTHER_SHA" --source "$SRC4_SHA" \
        --upstream "$BASE_SHA" --export "$ROOT/exp-bad" > /dev/null 2>&1; then
    bad "non-ancestor base export passed (must fail)"
else
    ok "non-ancestor base export rejected"
fi

# 4f. corrupted export fails verification and leaves no worktree behind.
rm -rf "$ROOT/exp-corrupt"
cp -r "$ROOT/exp1" "$ROOT/exp-corrupt"
shopt -s nullglob
corrupt=( "$ROOT/exp-corrupt"/*.patch )
shopt -u nullglob
half="$(( $(wc -c < "${corrupt[0]}") / 2 ))"
head -c "$half" "${corrupt[0]}" > "$ROOT/exp-corrupt/trunc.tmp"
mv "$ROOT/exp-corrupt/trunc.tmp" "${corrupt[0]}"
if T --verify "$ROOT/exp-corrupt" > /dev/null 2>&1; then
    bad "corrupted export verified (must fail)"
else
    ok "corrupted export fails verification"
fi

# 5. malformed / untrusted input fails safely (non-zero, no leftovers).
if "$TRACK" --bogus-flag > /dev/null 2>&1; then bad "unknown flag accepted"; else ok "unknown flag rejected"; fi
if "$TRACK" --repo "$FIX" --check-pins > /dev/null 2>&1; then
    bad "fixture check-pins with foreign defaults passed"
else
    ok "foreign pins fail safely in fixture"
fi
if "$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "deadbeef" --check-pins > /dev/null 2>&1; then
    bad "bogus rev accepted"
else
    ok "bogus rev rejected"
fi
if "$TRACK" --repo "$FIX" --base "$BASE_SHA" --source "$SRC2_SHA" \
        --upstream "$BASE_SHA" --export "$ROOT/exp1" > /dev/null 2>&1; then
    bad "export into non-empty dir accepted (must refuse)"
else
    ok "export into non-empty dir refused"
fi

# 5b. pins file validation: unknown / duplicate / missing / empty keys rejected.
printf 'REMOTE=x\nREF=y\nBASE=%s\nSOURCE=%s\nUPSTREAM=%s\nBOGUS=1\n' "$BASE_SHA" "$SRC_SHA" "$BASE_SHA" > "$ROOT/pins-unknown.conf"
if "$TRACK" --repo "$FIX" --pins "$ROOT/pins-unknown.conf" --show-pins > /dev/null 2>&1; then
    bad "unknown pins key accepted"
else
    ok "unknown pins key rejected"
fi
printf 'REMOTE=x\nREF=y\nBASE=%s\nBASE=%s\nSOURCE=%s\nUPSTREAM=%s\n' "$BASE_SHA" "$BASE_SHA" "$SRC_SHA" "$BASE_SHA" > "$ROOT/pins-dup.conf"
if "$TRACK" --repo "$FIX" --pins "$ROOT/pins-dup.conf" --show-pins > /dev/null 2>&1; then
    bad "duplicate pins key accepted"
else
    ok "duplicate pins key rejected"
fi
printf 'REMOTE=x\nREF=y\nBASE=%s\nSOURCE=%s\n' "$BASE_SHA" "$SRC_SHA" > "$ROOT/pins-missing.conf"
if "$TRACK" --repo "$FIX" --pins "$ROOT/pins-missing.conf" --show-pins > /dev/null 2>&1; then
    bad "missing pins key accepted"
else
    ok "missing pins key rejected"
fi
printf 'REMOTE=x\nREF=y\nBASE=\nSOURCE=%s\nUPSTREAM=%s\n' "$SRC_SHA" "$BASE_SHA" > "$ROOT/pins-empty.conf"
if "$TRACK" --repo "$FIX" --pins "$ROOT/pins-empty.conf" --show-pins > /dev/null 2>&1; then
    bad "empty pins value accepted"
else
    ok "empty pins value rejected"
fi

# 5c. CLI overrides pins regardless of flag order.
printf 'REMOTE=x\nREF=y\nBASE=%s\nSOURCE=%s\nUPSTREAM=%s\n' "$BASE_SHA" "$BASE_SHA" "$BASE_SHA" > "$ROOT/pins-zero.conf"
out1="$("$TRACK" --repo "$FIX" --source "$SRC2_SHA" --pins "$ROOT/pins-zero.conf" --show-pins)"
out2="$("$TRACK" --repo "$FIX" --pins "$ROOT/pins-zero.conf" --source "$SRC2_SHA" --show-pins)"
if echo "$out1" | grep -q "SOURCE=$SRC2_SHA"; then ok "CLI-before-pins wins"; else bad "CLI-before-pins lost"; fi
if echo "$out2" | grep -q "SOURCE=$SRC2_SHA"; then ok "CLI-after-pins wins"; else bad "CLI-after-pins lost"; fi

# 5d. malformed refs and option injection rejected.
if "$TRACK" --repo "$FIX" --ref 'a..b' --fetch > /dev/null 2>&1; then
    bad "malformed ref accepted"
else
    ok "malformed ref rejected"
fi
if "$TRACK" --repo "$FIX" --ref '-x' --fetch > /dev/null 2>&1; then
    bad "dash ref accepted"
else
    ok "dash ref rejected"
fi
if "$TRACK" --repo "$FIX" --remote '-foo' --fetch > /dev/null 2>&1; then
    bad "dash remote accepted"
else
    ok "dash remote rejected"
fi

# 6. fetch integration against a LOCAL remote: no-change, advance, rewrite,
#    full branch paths preserved, shared branches unmoved.
SRCREPO="$ROOT/srcrepo"
new_repo "$SRCREPO"
echo "r1" > "$SRCREPO/f.txt"
git -C "$SRCREPO" add f.txt
git -C "$SRCREPO" commit -qm "remote one"
git -C "$SRCREPO" branch testline
git -C "$SRCREPO" checkout -q -b "feature/a"
echo "fa" > "$SRCREPO/fa.txt"
git -C "$SRCREPO" add fa.txt
git -C "$SRCREPO" commit -qm "feature a"
git -C "$SRCREPO" checkout -q -b "other/a" master
echo "oa" > "$SRCREPO/oa.txt"
git -C "$SRCREPO" add oa.txt
git -C "$SRCREPO" commit -qm "other a"
git init -q -b master --bare "$ROOT/remote.git"
git -C "$SRCREPO" push -q "$ROOT/remote.git" testline "feature/a" "other/a" master
shared_before="$(git -C "$FIX" for-each-ref --format='%(refname) %(objectname)' | grep -v '^refs/task/' | sort | sha256sum)"

fout="$("$TRACK" --repo "$FIX" --remote "$ROOT/remote.git" --ref testline --fetch)"
if echo "$fout" | grep -q "status=new"; then ok "fetch new ref"; else bad "fetch new ref: $fout"; fi
fout="$("$TRACK" --repo "$FIX" --remote "$ROOT/remote.git" --ref testline --fetch)"
if echo "$fout" | grep -q "status=no-change"; then ok "fetch no-change"; else bad "fetch no-change: $fout"; fi
git -C "$SRCREPO" checkout -q testline
echo "r2" >> "$SRCREPO/f.txt"
git -C "$SRCREPO" commit -qam "remote two"
git -C "$SRCREPO" push -q "$ROOT/remote.git" testline
fout="$("$TRACK" --repo "$FIX" --remote "$ROOT/remote.git" --ref testline --fetch)"
if echo "$fout" | grep -q "status=advanced"; then ok "fetch advance"; else bad "fetch advance: $fout"; fi
git -C "$SRCREPO" reset -q --hard HEAD~1
echo "r2b" >> "$SRCREPO/f.txt"
git -C "$SRCREPO" commit -qam "remote two rewritten"
git -C "$SRCREPO" push -q --force "$ROOT/remote.git" testline
fout="$("$TRACK" --repo "$FIX" --remote "$ROOT/remote.git" --ref testline --fetch)"
if echo "$fout" | grep -q "status=rewritten"; then ok "fetch rewrite reported"; else bad "fetch rewrite: $fout"; fi
"$TRACK" --repo "$FIX" --remote "$ROOT/remote.git" --ref "feature/a" --fetch > /dev/null
"$TRACK" --repo "$FIX" --remote "$ROOT/remote.git" --ref "other/a" --fetch > /dev/null
if git -C "$FIX" rev-parse --verify --quiet "refs/task/valve/feature/a" > /dev/null \
    && git -C "$FIX" rev-parse --verify --quiet "refs/task/valve/other/a" > /dev/null; then
    if [[ "$(git -C "$FIX" rev-parse 'refs/task/valve/feature/a')" != "$(git -C "$FIX" rev-parse 'refs/task/valve/other/a')" ]]; then
        ok "full branch paths preserved (no basename collision)"
    else
        bad "branch paths collided"
    fi
else
    bad "full branch paths missing"
fi
shared_after="$(git -C "$FIX" for-each-ref --format='%(refname) %(objectname)' | grep -v '^refs/task/' | sort | sha256sum)"
if [[ "$shared_before" == "$shared_after" ]]; then ok "shared branches unmoved by fetch"; else bad "shared refs moved"; fi

if [[ "$(git -C "$FIX" worktree list --porcelain | grep -c '^worktree')" == 1 ]]; then
    ok "no worktree leftovers"
else
    bad "worktree leftover detected"
fi

echo "selftest: $pass passed, $fail_n failed"
[[ "$fail_n" == 0 ]]

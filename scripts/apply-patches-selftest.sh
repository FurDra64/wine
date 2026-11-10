#!/usr/bin/env bash
# Selftest: apply-patches.sh content-fidelity (whitespace + binary seed).
# No commits, no HOME/shared config, own mktemp + trap cleanup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

RUNROOT="$(mktemp -d "${TMPDIR:-/tmp}/apply-selftest.XXXXXX")"
trap 'rm -rf "$RUNROOT"' EXIT
export HOME="$RUNROOT/home"
export GIT_CONFIG_NOSYSTEM=1
mkdir -p "$HOME"

FAKE="$RUNROOT/repo"
DEST="$RUNROOT/dest"
mkdir -p "$FAKE/patches" "$FAKE/scripts" "$DEST"
cp -p "$SCRIPT_DIR/apply-patches.sh" "$FAKE/scripts/apply-patches.sh"
APPLY="$FAKE/scripts/apply-patches.sh"
# Run from inside FAKE so `git rev-parse --show-toplevel` cannot see the
# primary repo; the script then falls back to its own dir (= FAKE).
run_apply() { (cd "$FAKE" && "$APPLY" "$@"); }

reset_tree() {
    rm -rf "$FAKE/patches" "$DEST"
    mkdir -p "$FAKE/patches" "$DEST"
}

# --- A: trailing whitespace fidelity (git-apply backend) ---
reset_tree
printf 'keep \nbase\n' > "$DEST/foo.txt"
mkdir -p "$FAKE/patches/wsset"
printf 'Feature: wsset\nDescription: fixture\n' > "$FAKE/patches/wsset/definition"
echo "wsset" > "$FAKE/patches/series.conf"
printf -- '--- a/foo.txt\n+++ b/foo.txt\n@@ -1,2 +1,3 @@\n keep \n base\n+new \n' > "$FAKE/patches/wsset/0001.patch"
printf 'keep \nbase\nnew \n' > "$RUNROOT/expected-a.txt"
if run_apply --destdir "$DEST" --backend git-apply --check >/dev/null 2>&1; then
    ok "A1 check passes"
else
    bad "A1 check passes"
fi
if cmp -s "$DEST/foo.txt" "$RUNROOT/expected-a.txt"; then
    bad "A0 RED probe: pristine foo.txt must differ from expected (setup sanity)"
else
    ok "A0 setup sanity (pristine differs from expected)"
fi
if run_apply --destdir "$DEST" --backend git-apply >/dev/null 2>&1; then
    if cmp -s "$DEST/foo.txt" "$RUNROOT/expected-a.txt"; then
        ok "A2 exact bytes preserved (trailing SP)"
    else
        bad "A2 exact bytes preserved (trailing SP altered)"
    fi
else
    bad "A2 apply succeeded"
fi

# --- B: MODIFIED binary patch (no --- lines) ---
reset_tree
printf '\x00\x01\x02old-binary\xff\xfe\n' > "$RUNROOT/o.bin"
printf '\x00\x01\x02new-binary-data\xff\xfe\x00\n' > "$RUNROOT/n.bin"
cp -p "$RUNROOT/o.bin" "$DEST/f.bin"
mkdir -p "$FAKE/patches/binset"
printf 'Feature: binset\nDescription: fixture\n' > "$FAKE/patches/binset/definition"
echo "binset" > "$FAKE/patches/series.conf"
env GIT_PAGER=cat git diff --binary --no-index -- "$RUNROOT/o.bin" "$RUNROOT/n.bin" 2>/dev/null \
    | sed 's|^diff --git .*|diff --git a/f.bin b/f.bin|' > "$FAKE/patches/binset/0001.patch" || true
if grep -q '^--- ' "$FAKE/patches/binset/0001.patch"; then
    bad "B0 fixture has no --- lines (MODIFIED binary assumption)"
else
    ok "B0 fixture is a ---less MODIFIED binary patch"
fi
if run_apply --destdir "$DEST" --backend git-apply --check >/dev/null 2>&1; then
    ok "B1 binary --check passes (old file seeded)"
else
    bad "B1 binary --check passes (old file seeded)"
fi
if run_apply --destdir "$DEST" --backend git-apply >/dev/null 2>&1; then
    if cmp -s "$DEST/f.bin" "$RUNROOT/n.bin"; then
        ok "B2 binary exact bytes after apply"
    else
        bad "B2 binary exact bytes after apply"
    fi
else
    bad "B2 binary apply succeeded"
fi

# --- C: legacy CLI contract (default backend) ---
reset_tree
printf 'one\n' > "$DEST/base.txt"
mkdir -p "$FAKE/patches/ps1" "$FAKE/patches/ps2"
printf 'Feature: ps1\nDescription: fixture\n' > "$FAKE/patches/ps1/definition"
printf 'Feature: ps2\nDescription: fixture\n' > "$FAKE/patches/ps2/definition"
printf 'ps1\nps2\n' > "$FAKE/patches/series.conf"
printf -- '--- a/base.txt\n+++ b/base.txt\n@@ -1 +1 @@\n-one\n+two\n' > "$FAKE/patches/ps1/0001.patch"
printf -- '--- a/base.txt\n+++ b/base.txt\n@@ -1 +1 @@\n-two\n+three\n' > "$FAKE/patches/ps2/0001.patch"
cp -p "$DEST/base.txt" "$RUNROOT/before-c.txt"
if run_apply --destdir "$DEST" --check >/dev/null 2>&1; then
    ok "C1 stacked --check passes (cumulative)"
else
    bad "C1 stacked --check passes (cumulative)"
fi
if cmp -s "$DEST/base.txt" "$RUNROOT/before-c.txt"; then
    ok "C2 --check leaves tree untouched"
else
    bad "C2 --check leaves tree untouched"
fi
if run_apply --destdir "$DEST" --exclude 2>/dev/null; then
    bad "C3 unknown flag rejected"
else
    ok "C3 unknown flag rejected"
fi
if run_apply --destdir "$DEST" -W ps2 --check >/dev/null 2>&1; then
    ok "C4 exclusion (-W ps2) check passes"
else
    bad "C4 exclusion (-W ps2) check passes"
fi
if run_apply --destdir "$DEST" >/dev/null 2>&1; then
    if [[ "$(cat "$DEST/base.txt")" == "three" ]]; then
        ok "C5 stacked apply result correct"
    else
        bad "C5 stacked apply result correct"
    fi
else
    bad "C5 apply succeeded"
fi
if run_apply --destdir "$DEST" >"$RUNROOT/c-double.log" 2>&1; then
    bad "C6 double-apply fails loudly"
else
    if grep -q 'FAILED patchset=' "$RUNROOT/c-double.log"; then
        ok "C6 double-apply fails loudly (FAILED line)"
    else
        bad "C6 double-apply fails loudly (FAILED line)"
    fi
fi

echo "----"
echo "selftest: $PASS passed, $FAIL failed"
[[ "$FAIL" == 0 ]]

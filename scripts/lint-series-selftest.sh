#!/usr/bin/env bash
# Selftest for lint-series.sh. TDD style: every rule has a RED case
# (failing fixture must print LINT_FAILED <rule> and exit non-zero)
# followed by a GREEN case (fixed fixture must exit 0 with no output).
# No commits, no network, own mktemp tree + trap cleanup.
#
#   scripts/lint-series-selftest.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINT="$SCRIPT_DIR/lint-series.sh"
PASS=0
FAILN=0

ok() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAILN=$((FAILN + 1)); echo "FAIL: $1" >&2; }

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/lint-series-selftest.XXXXXX")"
trap 'rm -rf "$ROOT"' EXIT

# new_tree <dir>: minimal valid tree (one patchset "good").
new_tree() {
    mkdir -p "$1/patches/good"
    cat > "$1/patches/good/definition" <<'EOF'
Feature: good
Description: valid fixture patchset
Author: Selftest <selftest@localhost>
Upstream-Status: none
Depends-On: none
EOF
    cat > "$1/patches/good/0001-foo.patch" <<'EOF'
diff --git a/foo.txt b/foo.txt
--- a/foo.txt
+++ b/foo.txt
@@ -1 +1 @@
-old
+new
EOF
    echo "good" > "$1/patches/series.conf"
}

# run_lint <tree>: prints lint output, relays its exit code.
run_lint() {
    "$LINT" --series "$1/patches/series.conf" --patches-dir "$1/patches" 2>&1
}

# expect_fail <label> <rule> <tree>: RED — must fail with LINT_FAILED <rule>.
expect_fail() {
    local out
    if out="$(run_lint "$3")"; then
        bad "$1 RED: lint exited 0 on bad fixture"
    elif echo "$out" | grep -q "LINT_FAILED $2"; then
        ok "$1 RED: LINT_FAILED $2"
    else
        bad "$1 RED: missing LINT_FAILED $2 (got: $out)"
    fi
}

# expect_ok <label> <tree>: GREEN — must exit 0 silently.
expect_ok() {
    local out
    if out="$(run_lint "$2")"; then
        if [[ -z "$out" ]]; then
            ok "$1 GREEN: exit 0, silent"
        else
            bad "$1 GREEN: exit 0 but noisy (got: $out)"
        fi
    else
        bad "$1 GREEN: lint failed on good fixture (got: $out)"
    fi
}

# --- 0: happy path ---
T="$ROOT/t0"; new_tree "$T"
expect_ok "happy" "$T"

# --- 1: duplicate (RED: entry twice; GREEN: listed once) ---
T="$ROOT/t1"; new_tree "$T"
printf 'good\ngood\n' > "$T/patches/series.conf"
expect_fail "duplicate" "duplicate" "$T"
echo "good" > "$T/patches/series.conf"
expect_ok "duplicate" "$T"

# --- 2: missing-dir (RED: ghost entry; GREEN: entry removed) ---
T="$ROOT/t2"; new_tree "$T"
printf 'good\nghost\n' > "$T/patches/series.conf"
expect_fail "missing-dir" "missing-dir ghost" "$T"
echo "good" > "$T/patches/series.conf"
expect_ok "missing-dir" "$T"

# --- 3: missing-definition (RED: definition deleted; GREEN: restored) ---
T="$ROOT/t3"; new_tree "$T"
rm "$T/patches/good/definition"
expect_fail "missing-definition" "missing-definition good" "$T"
new_tree "$T"
expect_ok "missing-definition" "$T"

# --- 4: feature-mismatch (RED: Feature != dirname; GREEN: fixed) ---
T="$ROOT/t4"; new_tree "$T"
sed -i 's/^Feature:.*/Feature: other/' "$T/patches/good/definition"
expect_fail "feature-mismatch" "feature-mismatch good" "$T"
sed -i 's/^Feature:.*/Feature: good/' "$T/patches/good/definition"
expect_ok "feature-mismatch" "$T"

# --- 5: missing-key (RED: Author dropped; GREEN: restored) ---
T="$ROOT/t5"; new_tree "$T"
sed -i '/^Author:/d' "$T/patches/good/definition"
expect_fail "missing-key" "missing-key good:Author" "$T"
new_tree "$T"
expect_ok "missing-key" "$T"

# --- 6: patch-name-order (RED: unnumbered name; GREEN: renamed) ---
T="$ROOT/t6"; new_tree "$T"
mv "$T/patches/good/0001-foo.patch" "$T/patches/good/fix-foo.patch"
expect_fail "patch-name-order" "patch-name-order" "$T"
mv "$T/patches/good/fix-foo.patch" "$T/patches/good/0001-foo.patch"
expect_ok "patch-name-order" "$T"

# --- 7: crlf (RED: CRLF definition; GREEN: LF restored) ---
T="$ROOT/t7"; new_tree "$T"
sed -i 's/$/\r/' "$T/patches/good/definition"
expect_fail "crlf" "crlf" "$T"
new_tree "$T"
expect_ok "crlf" "$T"

# --- 8: absolute-path (RED: /tmp ref; GREEN: removed) ---
T="$ROOT/t8"; new_tree "$T"
echo '+tmpfile="/tmp/evil"' >> "$T/patches/good/0001-foo.patch"
expect_fail "absolute-path-tmp" "absolute-path" "$T"
new_tree "$T"
expect_ok "absolute-path-tmp" "$T"

# --- 8b: absolute-path header (RED: "--- /abs"; GREEN: relative) ---
T="$ROOT/t8b"; new_tree "$T"
sed -i 's|^--- a/foo.txt|--- /abs/foo.txt|' "$T/patches/good/0001-foo.patch"
expect_fail "absolute-path-header" "absolute-path" "$T"
new_tree "$T"
expect_ok "absolute-path-header" "$T"

# --- negative control: /tmpdir must NOT trip absolute-path ---
T="$ROOT/t9"; new_tree "$T"
echo '+x="/tmpdir"' >> "$T/patches/good/0001-foo.patch"
expect_ok "tmpdir-prefix" "$T"

echo "----"
echo "PASS=$PASS FAIL=$FAILN"
if ((FAILN > 0)); then
    exit 1
fi

#!/usr/bin/env bash
# Scaffold a new patchset: patches/<name>/{definition,0001-*.patch stub}
# and register <name> in patches/series.conf.
set -euo pipefail

[[ $# -eq 1 ]] || { echo "usage: new-patchset.sh <name>" >&2; exit 2; }
NAME="$1"
[[ "$NAME" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
    echo "error: name must match ^[a-z0-9][a-z0-9_-]*\$ (got: $NAME)" >&2
    exit 2
}

if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
DIR="$REPO_ROOT/patches/$NAME"
SERIES="$REPO_ROOT/patches/series.conf"

[[ -e "$DIR" ]] && { echo "error: already exists: $DIR" >&2; exit 1; }
mkdir -p "$DIR"

AUTHOR="$(git config user.name 2>/dev/null || echo 'Your Name') <$(git config user.email 2>/dev/null || echo 'you@example.com')>"
cat > "$DIR/definition" <<EOF
Feature: $NAME
Description: TODO one or two sentences, what and why
Author: $AUTHOR
Upstream-Status: none
Depends-On: none
EOF

cat > "$DIR/0001-TODO.patch" <<'EOF'
# TODO: replace this stub with a real unified diff (-p1).
# Generate with: git diff > patches/<name>/0001-what.patch
# Then delete this stub file. Empty/stub files are skipped by CI naming check.
EOF

if ! grep -qx "$NAME" "$SERIES" 2>/dev/null; then
    printf '%s\n' "$NAME" >> "$SERIES"
fi

echo "created: $DIR"
echo "next: write the Description, replace 0001-TODO.patch with a real diff,"
echo "      then run: scripts/apply-patches.sh --check"

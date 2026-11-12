#!/usr/bin/env bash
# Lint patches/series.conf and the patchsets it references.
#
#   scripts/lint-series.sh [--series FILE] [--patches-dir DIR]
#
# Rules (bash only, no extra dependencies):
#   duplicate          series.conf lists the same patchset twice
#   missing-dir        entry has no patches/<name>/ directory
#   missing-definition patches/<name>/definition is absent
#   feature-mismatch   definition "Feature:" value != directory name
#   missing-key        definition lacks a required key
#   patch-name-order   patch files must match NNNN-*.patch and sort cleanly
#   crlf               series.conf / definition / patch must be LF (no CR)
#   absolute-path      patch content must not reference /tmp or absolute paths
#
# Each violation prints one machine-grepable line:
#   LINT_FAILED <rule> <target>
# Exit 0 when clean, 1 when any violation, 2 on usage errors.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: lint-series.sh [--series FILE] [--patches-dir DIR]
  --series FILE       series.conf to lint (default: <repo>/patches/series.conf)
  --patches-dir DIR   patchset directory (default: <repo>/patches)
  -h, --help          show this help and exit
EOF
}

SERIES=""
PATCHES_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --series) SERIES="$2"; shift 2 ;;
        --patches-dir) PATCHES_DIR="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
SERIES="${SERIES:-$REPO_ROOT/patches/series.conf}"
PATCHES_DIR="${PATCHES_DIR:-$REPO_ROOT/patches}"

[[ -f "$SERIES" ]] || { echo "error: series.conf not found: $SERIES" >&2; exit 2; }
[[ -d "$PATCHES_DIR" ]] || { echo "error: patches dir not found: $PATCHES_DIR" >&2; exit 2; }

FAIL=0
fail() {
    echo "LINT_FAILED $1 $2"
    FAIL=1
}

CR=$'\r'

# series.conf itself must be LF-only.
if grep -q "$CR" "$SERIES"; then
    fail crlf series.conf
fi

# Parse order (skip blanks/comments), detect duplicates.
UNIQUE=()
declare -A SEEN=()
while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="${raw%$CR}"
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    if [[ -v SEEN["$line"] ]]; then
        fail duplicate "$line"
    else
        SEEN["$line"]=1
        UNIQUE+=("$line")
    fi
done < "$SERIES"

REQUIRED_KEYS=(Feature Description Author Upstream-Status Depends-On)

for name in ${UNIQUE[@]+"${UNIQUE[@]}"}; do
    dir="$PATCHES_DIR/$name"
    if [[ ! -d "$dir" ]]; then
        fail missing-dir "$name"
        continue
    fi
    def="$dir/definition"
    if [[ ! -f "$def" ]]; then
        fail missing-definition "$name"
        continue
    fi
    if grep -q "$CR" "$def"; then
        fail crlf "$name:definition"
    fi
    for key in "${REQUIRED_KEYS[@]}"; do
        if ! grep -qE "^${key}:[[:space:]]" "$def"; then
            fail missing-key "$name:$key"
        fi
    done
    feat="$(sed -n 's/^Feature:[[:space:]]*//p' "$def" | head -n 1)"
    feat="${feat%$CR}"
    feat="${feat%"${feat##*[![:space:]]}"}"
    if [[ "$feat" != "$name" ]]; then
        fail feature-mismatch "$name"
    fi

    shopt -s nullglob
    files=("$dir"/*.patch)
    shopt -u nullglob
    if ((${#files[@]} == 0)); then
        continue
    fi
    for f in "${files[@]}"; do
        base="$(basename "$f")"
        if [[ ! "$base" =~ ^[0-9]{4}-.+\.patch$ ]]; then
            fail patch-name-order "$name:$base"
        fi
        if grep -q "$CR" "$f"; then
            fail crlf "$name:$base"
        fi
        # "/tmp" followed by a separator (excludes longer names like /tmpdir).
        if grep -qE "/tmp([^A-Za-z0-9_.-]|$)" "$f"; then
            fail absolute-path "$name:$base"
        elif grep -E '^(---|\+\+\+) /' "$f" | grep -v '/dev/null' | grep -q .; then
            fail absolute-path "$name:$base"
        fi
    done
    if ((${#files[@]} > 1)); then
        mapfile -t sorted < <(printf '%s\n' "${files[@]}" | LC_ALL=C sort)
        if [[ "${files[*]}" != "${sorted[*]}" ]]; then
            fail patch-name-order "$name:unsorted"
        fi
    fi
done

exit "$FAIL"

#!/usr/bin/env bash
# Apply custom patchsets on top of an upstream Wine tree.
#
#   scripts/apply-patches.sh [--destdir DIR] [--all] [-W NAME]...
#                            [--check] [--backend patch|git-apply] [--list]
#
# Defaults: DESTDIR=repo root, backend=patch. Reads order from
# patches/series.conf. Exits non-zero on first failure with a
# machine-grepable line: "FAILED patchset=<name> file=<file>".
set -euo pipefail

DESTDIR=""
BACKEND="patch"
CHECK=0
LIST_ONLY=0
EXCLUDES=()

usage() {
    cat <<'EOF'
Usage: apply-patches.sh [--destdir DIR] [--all] [-W NAME] [--check]
                         [--backend patch|git-apply] [--list]
  --destdir DIR   tree to patch (default: repo root)
  --all           apply every patchset in series.conf (default behavior)
  -W NAME         exclude patchset NAME (repeatable)
  --check         dry-run only, tree untouched
  --backend NAME  patch (default) or git-apply
  --list          print resolved order and exit
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --destdir) DESTDIR="$2"; shift 2 ;;
        --all) shift ;;
        -W) EXCLUDES+=("$2"); shift 2 ;;
        --check) CHECK=1; shift ;;
        --backend) BACKEND="$2"; shift 2 ;;
        --list) LIST_ONLY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$BACKEND" in
    patch|git-apply) ;;
    *) echo "error: --backend must be patch or git-apply" >&2; exit 2 ;;
esac

if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
DESTDIR="${DESTDIR:-$REPO_ROOT}"
PATCHES_DIR="$REPO_ROOT/patches"
SERIES="$PATCHES_DIR/series.conf"

[[ -f "$SERIES" ]] || { echo "error: series.conf not found: $SERIES" >&2; exit 2; }
[[ -d "$DESTDIR" ]] || { echo "error: destdir not found: $DESTDIR" >&2; exit 2; }

# Resolve ordered patchset list (skip blanks/comments), then exclusions.
ORDER=()
while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line//[[:space:]]/}"
    [[ -z "$line" ]] && continue
    skip=0
    for ex in ${EXCLUDES[@]+"${EXCLUDES[@]}"}; do
        [[ "$line" == "$ex" ]] && { skip=1; break; }
    done
    [[ "$skip" == 1 ]] && continue
    ORDER+=("$line")
done < "$SERIES"

if [[ "${#ORDER[@]}" -eq 0 ]]; then
    echo "no patchsets enabled (series.conf empty or all excluded)"
    exit 0
fi

if [[ "$LIST_ONLY" == 1 ]]; then
    printf '%s\n' "${ORDER[@]}"
    exit 0
fi

TOTAL_FILES=0
for ps in "${ORDER[@]}"; do
    dir="$PATCHES_DIR/$ps"
    [[ -d "$dir" ]] || { echo "FAILED patchset=$ps file=(missing directory $dir)" >&2; exit 1; }
    [[ -f "$dir/definition" ]] || { echo "FAILED patchset=$ps file=(missing definition)" >&2; exit 1; }
    shopt -s nullglob
    files=("$dir"/*.patch)
    shopt -u nullglob
    [[ "${#files[@]}" -gt 0 ]] || { echo "warn: patchset=$ps has no *.patch, skipped" >&2; continue; }
    for f in "${files[@]}"; do
        base="$(basename "$f")"
        if [[ "$BACKEND" == "patch" ]]; then
            if [[ "$CHECK" == 1 ]]; then
                if ! patch -p1 --dry-run --no-backup-if-mismatch -d "$DESTDIR" < "$f" > /dev/null; then
                    echo "FAILED patchset=$ps file=$base" >&2
                    exit 1
                fi
            else
                if ! patch -p1 --no-backup-if-mismatch -d "$DESTDIR" < "$f"; then
                    echo "FAILED patchset=$ps file=$base" >&2
                    exit 1
                fi
            fi
        else
            if [[ "$CHECK" == 1 ]]; then
                if ! git -C "$DESTDIR" apply --check -p1 "$f"; then
                    echo "FAILED patchset=$ps file=$base" >&2
                    exit 1
                fi
            else
                if ! git -C "$DESTDIR" apply -p1 --whitespace=fix "$f"; then
                    echo "FAILED patchset=$ps file=$base" >&2
                    exit 1
                fi
            fi
        fi
        TOTAL_FILES=$((TOTAL_FILES + 1))
    done
    echo "ok: patchset=$ps (${#files[@]} files)"
done

if [[ "$CHECK" == 1 ]]; then
    echo "check passed: ${#ORDER[@]} patchsets, $TOTAL_FILES files (dry-run)"
else
    echo "applied: ${#ORDER[@]} patchsets, $TOTAL_FILES files to $DESTDIR"
fi

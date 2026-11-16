#!/usr/bin/env bash
# lint-series.sh — machine-enforced series.conf hygiene (R1).
#
# Usage: scripts/lint-series.sh [--help]
#
# Checks patches/series.conf plus the patchset directories it references:
#   1. Every commented-out entry carries a reason TAG plus a date.
#      Allowed TAGs: NEEDS-REBASE, OBSOLETE, DISABLED, AUDITED.
#      Format:  # TAG YYYY-MM-DD [(reason)]: <patchset-dir>
#      A bare "# <patchset-dir>" (no TAG/date) is a violation.
#   2. OBSOLETE entries additionally cite upstream commit evidence
#      (a hex commit hash, 7-40 chars) explaining what superseded them.
#   3. Every definition file's "Feature:" value equals its directory name.
#   4. Every top-level patches/*/*.patch file is named NNNN-*.patch
#      (an optional single lowercase letter after the number, e.g.
#      0012a-foo.patch, is allowed for insertions without renumbering).
#      Files under patches/*/disabled/ are inert and skipped.
#
# Violations print as "series.conf:<line>: <reason>" (or a path for
# naming/Feature violations) and the script exits 1. Clean exits 0.
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# //; s/^#//'
    exit 0
fi
if [[ $# -gt 0 ]]; then
    echo "error: unknown argument: $1 (usage: scripts/lint-series.sh [--help])" >&2
    exit 2
fi

if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
PATCHES_DIR="$REPO_ROOT/patches"
SERIES="$PATCHES_DIR/series.conf"

[[ -f "$SERIES" ]] || { echo "error: series.conf not found: $SERIES" >&2; exit 2; }
[[ -d "$PATCHES_DIR" ]] || { echo "error: patches dir not found: $PATCHES_DIR" >&2; exit 2; }

ERRORS=0
fail() { echo "$1" >&2; ERRORS=$((ERRORS + 1)); }

# Patchset dirs: directories directly under patches/ holding a definition.
declare -A KNOWN=()
for def in "$PATCHES_DIR"/*/definition; do
    [[ -f "$def" ]] || continue
    KNOWN["$(basename "$(dirname "$def")")"]=1
done

NAME_RE='[_A-Za-z0-9][_A-Za-z0-9.+@-]*'
DATE_RE='(19|20)[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])'
HASH_RE='[0-9a-f]{7,40}'

declare -A ACTIVE_SEEN=()
declare -A DISABLED_SEEN=()

lineno=0
while IFS= read -r raw || [[ -n "$raw" ]]; do
    lineno=$((lineno + 1))
    # Strip CR (keep file LF-only, but don't choke on CRLF).
    line="${raw%$'\r'}"

    # Blank line: pass.
    if [[ "$line" =~ ^[[:space:]]*$ ]]; then
        continue
    fi

    # Active entry: a bare directory name.
    if [[ ! "$line" =~ ^[[:space:]]*# ]]; then
        name="$(echo "$line" | tr -d '[:space:]')"
        if [[ ! "$name" =~ ^$NAME_RE$ ]]; then
            fail "series.conf:$lineno: malformed active entry '$line'"
            continue
        fi
        if [[ -n "${ACTIVE_SEEN[$name]:-}" ]]; then
            fail "series.conf:$lineno: duplicate active entry '$name'"
            continue
        fi
        ACTIVE_SEEN["$name"]=1
        if [[ -z "${KNOWN[$name]:-}" ]]; then
            fail "series.conf:$lineno: active entry '$name' has no patches/$name/definition"
        fi
        continue
    fi

    # Comment line: strip leading '#' run and one layer of whitespace.
    body="$(echo "$line" | sed -E 's/^[[:space:]]*#+//; s/^[[:space:]]*//; s/[[:space:]]*$//')"
    [[ -z "$body" ]] && continue  # lone '#' separator: pass.

    # Tagged form: "# TAG rest".
    if [[ "$body" =~ ^([A-Z][A-Z0-9-]*)([[:space:]:].*)?$ ]]; then
        tag="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[2]}"
        case "$tag" in
            NEEDS-REBASE|OBSOLETE|DISABLED|AUDITED) ;;
            *)
                # TAG-shaped but not allowlisted: if it also points at a
                # patchset, the author meant a TAG and misspelled it.
                if [[ "$rest" =~ :[[:space:]]*($NAME_RE)[[:space:]]*$ && -n "${KNOWN[${BASH_REMATCH[1]}]:-}" ]]; then
                    fail "series.conf:$lineno: unknown TAG '$tag' (want NEEDS-REBASE|OBSOLETE|DISABLED|AUDITED): $body"
                    continue
                fi
                # Otherwise prose starting with a capitalised word:
                # fall through to the untagged checks below.
                tag=""
                ;;
        esac
        if [[ -n "$tag" ]]; then
            if [[ ! "$rest" =~ $DATE_RE ]]; then
                fail "series.conf:$lineno: '$tag' entry lacks date (YYYY-MM-DD): $body"
                continue
            fi
            case "$tag" in
                NEEDS-REBASE|OBSOLETE|DISABLED)
                    if [[ ! "$rest" =~ :[[:space:]]*($NAME_RE)[[:space:]]*$ ]]; then
                        fail "series.conf:$lineno: '$tag' entry must end with ': <patchset-dir>': $body"
                        continue
                    fi
                    ref="${BASH_REMATCH[1]}"
                    if [[ -z "${KNOWN[$ref]:-}" ]]; then
                        fail "series.conf:$lineno: '$tag' references unknown patchset '$ref'"
                        continue
                    fi
                    DISABLED_SEEN["$ref"]=1
                    if [[ -n "${ACTIVE_SEEN[$ref]:-}" ]]; then
                        fail "series.conf:$lineno: '$ref' is both active and $tag"
                    fi
                    ;;
                AUDITED)
                    : # informational record: TAG + date suffice.
                    ;;
            esac
            if [[ "$tag" == "OBSOLETE" && ! "$rest" =~ $HASH_RE ]]; then
                fail "series.conf:$lineno: OBSOLETE entry lacks upstream commit evidence (hex hash): $body"
            fi
            continue
        fi
    fi

    # Untagged comment: violation if it names a patchset.
    if [[ "$body" =~ ^($NAME_RE)$ && -n "${KNOWN[${BASH_REMATCH[1]}]:-}" ]]; then
        fail "series.conf:$lineno: commented-out entry lacks TAG + date: $body"
        continue
    fi
    if [[ "$body" =~ :[[:space:]]*($NAME_RE)[[:space:]]*$ && -n "${KNOWN[${BASH_REMATCH[1]}]:-}" ]]; then
        fail "series.conf:$lineno: commented-out entry lacks TAG + date: $body"
        continue
    fi
    : # free prose (headers, audit bullets, explanations): pass.
done < "$SERIES"

# Active entries must not also be disabled elsewhere (forward check).
for name in "${!DISABLED_SEEN[@]}"; do
    if [[ -n "${ACTIVE_SEEN[$name]:-}" ]]; then
        fail "series.conf: '$name' is both active and disabled"
    fi
done

# Check 3: Feature: value equals directory name, for every definition.
for def in "$PATCHES_DIR"/*/definition; do
    [[ -f "$def" ]] || continue
    dir="$(basename "$(dirname "$def")")"
    feature="$(grep -m1 -E '^Feature:[[:space:]]*' "$def" | sed -E 's/^Feature:[[:space:]]*//; s/[[:space:]]*$//' || true)"
    if [[ -z "$feature" ]]; then
        fail "patches/$dir/definition: missing 'Feature:' line"
    elif [[ "$feature" != "$dir" ]]; then
        fail "patches/$dir/definition: Feature='$feature' != directory name '$dir'"
    fi
done

# Check 4: NNNN-*.patch naming for top-level patch files (disabled/ skipped).
while IFS= read -r f; do
    base="$(basename "$f")"
    if [[ ! "$base" =~ ^[0-9]{4}[a-z]?-.+\.patch$ ]]; then
        fail "$f: patch file must be named NNNN-*.patch (got '$base')"
    fi
done < <(find "$PATCHES_DIR" -maxdepth 2 -name '*.patch' -not -path '*/disabled/*' | sort)

if [[ "$ERRORS" -gt 0 ]]; then
    echo "lint-series: $ERRORS violation(s)" >&2
    exit 1
fi
echo "lint-series: clean ($(wc -l < "$SERIES") series.conf lines, ${#KNOWN[@]} patchsets)"

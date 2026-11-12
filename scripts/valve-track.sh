#!/usr/bin/env bash
# Valve downstream tracking: deterministic inventory / export / verify / conflicts.
#
#   scripts/valve-track.sh [options] ACTION
#
# Actions (exactly one per invocation):
#   --show-pins                 print effective base/source/upstream/remote/ref
#   --check-pins                verify objects exist and merge-base matches base
#   --inventory OUT             write deterministic commit inventory (TSV) to OUT
#   --export DIR                export base..source as format-patch files into DIR
#   --verify DIR                replay DIR patches onto base in an isolated
#                               worktree and require the resulting tree to equal
#                               source (exact reconstruction proof)
#   --conflicts OUT             write merge-tree conflict file list (upstream vs
#                               source) to OUT, one path per line
#   --fetch                     fetch REF from REMOTE into the private task ref
#                               refs/task/valve/<full REF path> (force-updated;
#                               shared branches are never touched)
#
# Options (order-independent; CLI values always override pins):
#   --repo DIR        git repository (default: toplevel of current repo)
#   --fork NAME       fork pins to resolve (default: valve; see docs/forks/README.md
#                     spec v1: valve -> docs/valve/pins.conf else docs/forks/<fork>/pins.conf)
#   --base REV        Valve delta base (default from pins.conf, else Wine 11.0)
#   --source REV      Valve tip under test (default from pins.conf, else pinned tip)
#   --upstream REV    integration base (default from pins.conf, else Wine 11.21)
#   --remote URL      Valve remote URL for --fetch
#   --ref REF         Valve branch for --fetch (default: bleeding-edge)
#   --pins FILE       KEY=VALUE file (REMOTE REF BASE SOURCE UPSTREAM); when
#                     omitted, the fork default file above is used if present
#
# Single source of truth: the resolved pins file (docs/valve/pins.conf for
# valve, docs/forks/<fork>/pins.conf otherwise; spec v1 in docs/forks/README.md).
# no matter where they appear on the command line (two-pass parsing).
# A live Valve ref overrides the pinned SOURCE for live reconstruction
# while the recorded snapshot in pins.conf stays immutable; pass a live
# ref explicitly (e.g. --source refs/task/valve/bleeding-edge).
#
# Conventions: set -euo pipefail, long flags, machine-grepable result lines
# (VERIFY_OK, EXPORT_OK, INVENTORY_OK, CONFLICT_FILES, PIN_OK, FETCH_OK,
# FAILED ...). Raw exports live OUTSIDE the repo (task root or user dir)
# and are never listed in patches/series.conf.
set -euo pipefail

FALLBACK_REMOTE="https://github.com/ValveSoftware/wine.git"
FALLBACK_REF="bleeding-edge"
FALLBACK_BASE="db11d0fe6a169c457e23d007e20404643d067aa8"
FALLBACK_SOURCE="fda79a585939fb7512dc220a11249f9ffe825fcf"
FALLBACK_UPSTREAM="2528aff26208257fdbf980666a4f0e66d47563ce"

CLI_REPO=""
CLI_FORK=""
CLI_BASE=""
CLI_SOURCE=""
CLI_UPSTREAM=""
CLI_REMOTE=""
CLI_REF=""
CLI_PINS=""

ACTION=""
ACTION_ARG=""

usage() {
    awk 'NR>1 && /^set -euo pipefail/{exit} NR>1{print}' "${BASH_SOURCE[0]}"
}

fail() {
    echo "FAILED $1" >&2
    exit 1
}

load_pins() {
    local file="$1" line key val seen=""
    [[ -f "$file" ]] || { echo "error: pins file not found: $file" >&2; exit 2; }
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        if [[ "$line" =~ ^[[:space:]]*$ ]]; then
            continue
        fi
        if [[ "$line" != *"="* ]]; then
            echo "error: malformed pins line (no =): $line" >&2
            exit 2
        fi
        key="${line%%=*}"
        val="${line#*=}"
        key="${key//[[:space:]]/}"
        val="${val#"${val%%[![:space:]]*}"}"
        val="${val%"${val##*[![:space:]]}"}"
        case "$key" in
            REMOTE | REF | BASE | SOURCE | UPSTREAM) ;;
            *) echo "error: unknown pins key: $key" >&2; exit 2 ;;
        esac
        if [[ "$seen" == *" $key "* ]]; then
            echo "error: duplicate pins key: $key" >&2
            exit 2
        fi
        seen="$seen $key "
        if [[ -z "$val" ]]; then
            echo "error: empty pins value: $key" >&2
            exit 2
        fi
        case "$key" in
            REMOTE) REMOTE="$val" ;;
            REF) REF="$val" ;;
            BASE) BASE="$val" ;;
            SOURCE) SOURCE="$val" ;;
            UPSTREAM) UPSTREAM="$val" ;;
        esac
    done < "$file"
    for key in REMOTE REF BASE SOURCE UPSTREAM; do
        if [[ "$seen" != *" $key "* ]]; then
            echo "error: missing pins key: $key" >&2
            exit 2
        fi
    done
}

check_branch_ref() {
    local ref="$1" what="$2"
    if [[ "$ref" == -* ]]; then
        echo "error: $what must not start with dash" >&2
        exit 2
    fi
    if ! git check-ref-format --branch "$ref" > /dev/null 2>&1; then
        echo "error: malformed $what: $ref" >&2
        exit 2
    fi
}

check_fork_name() {
    local fork="$1"
    if [[ ! "$fork" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
        echo "error: malformed fork: $fork" >&2
        exit 2
    fi
}

resolve_default_pins_file() {
    local repo="$1" fork="$2"
    if [[ "$fork" == "valve" && -f "$repo/docs/valve/pins.conf" ]]; then
        printf '%s' "$repo/docs/valve/pins.conf"
    else
        printf '%s' "$repo/docs/forks/$fork/pins.conf"
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) [[ $# -ge 2 ]] || { echo "error: --repo needs a value" >&2; exit 2; } ; CLI_REPO="$2"; shift 2 ;;
        --fork) [[ $# -ge 2 ]] || { echo "error: --fork needs a value" >&2; exit 2; } ; CLI_FORK="$2"; shift 2 ;;
        --base) [[ $# -ge 2 ]] || { echo "error: --base needs a value" >&2; exit 2; } ; CLI_BASE="$2"; shift 2 ;;
        --source) [[ $# -ge 2 ]] || { echo "error: --source needs a value" >&2; exit 2; } ; CLI_SOURCE="$2"; shift 2 ;;
        --upstream) [[ $# -ge 2 ]] || { echo "error: --upstream needs a value" >&2; exit 2; } ; CLI_UPSTREAM="$2"; shift 2 ;;
        --remote) [[ $# -ge 2 ]] || { echo "error: --remote needs a value" >&2; exit 2; } ; CLI_REMOTE="$2"; shift 2 ;;
        --ref) [[ $# -ge 2 ]] || { echo "error: --ref needs a value" >&2; exit 2; } ; CLI_REF="$2"; shift 2 ;;
        --pins) [[ $# -ge 2 ]] || { echo "error: --pins needs a value" >&2; exit 2; } ; CLI_PINS="$2"; shift 2 ;;
        --show-pins|--check-pins|--fetch)
            [[ -z "$ACTION" ]] || { echo "error: only one action per invocation" >&2; exit 2; }
            ACTION="${1#--}"; shift ;;
        --inventory|--export|--verify|--conflicts)
            [[ -z "$ACTION" ]] || { echo "error: only one action per invocation" >&2; exit 2; }
            [[ $# -ge 2 ]] || { echo "error: $1 needs a value" >&2; exit 2; }
            ACTION="${1#--}"; ACTION_ARG="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ -n "$ACTION" ]] || { echo "error: no action given" >&2; usage >&2; exit 2; }

REPO="$CLI_REPO"
if [[ -z "$REPO" ]]; then
    if ! REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; then
        echo "error: not in a git repo and --repo not given" >&2
        exit 2
    fi
fi
if [[ ! -d "$REPO/.git" && ! -f "$REPO/.git" ]]; then
    echo "error: not a git repo: $REPO" >&2
    exit 2
fi

REMOTE="$FALLBACK_REMOTE"
REF="$FALLBACK_REF"
BASE="$FALLBACK_BASE"
SOURCE="$FALLBACK_SOURCE"
UPSTREAM="$FALLBACK_UPSTREAM"
PINS_FROM="builtin-fallback"
FORK="valve"
if [[ -n "$CLI_FORK" ]]; then
    check_fork_name "$CLI_FORK"
    FORK="$CLI_FORK"
fi
if [[ -n "$CLI_PINS" ]]; then
    load_pins "$CLI_PINS"
    PINS_FROM="$CLI_PINS"
else
    default_pins="$(resolve_default_pins_file "$REPO" "$FORK")"
    if [[ -f "$default_pins" ]]; then
        load_pins "$default_pins"
        PINS_FROM="$default_pins"
    fi
fi
if [[ -n "$CLI_REMOTE" ]]; then REMOTE="$CLI_REMOTE"; fi
if [[ -n "$CLI_REF" ]]; then REF="$CLI_REF"; fi
if [[ -n "$CLI_BASE" ]]; then BASE="$CLI_BASE"; fi
if [[ -n "$CLI_SOURCE" ]]; then SOURCE="$CLI_SOURCE"; fi
if [[ -n "$CLI_UPSTREAM" ]]; then UPSTREAM="$CLI_UPSTREAM"; fi

resolve() {
    git -C "$REPO" rev-parse --verify --quiet --end-of-options "$1^{commit}" || return 1
}

require_range() {
    local act="$1"
    RANGE_BASE="$(resolve "$BASE")" || fail "action=$act missing=base rev=$BASE"
    RANGE_SRC="$(resolve "$SOURCE")" || fail "action=$act missing=source rev=$SOURCE"
    if ! git -C "$REPO" merge-base --is-ancestor "$RANGE_BASE" "$RANGE_SRC"; then
        fail "action=$act base-not-ancestor-of-source base=$RANGE_BASE source=$RANGE_SRC"
    fi
}

case "$ACTION" in
    show-pins)
        printf 'PINS_FROM=%s\nREMOTE=%s\nREF=%s\nBASE=%s\nSOURCE=%s\nUPSTREAM=%s\n' \
            "$PINS_FROM" "$REMOTE" "$REF" "$BASE" "$SOURCE" "$UPSTREAM"
        ;;
    fetch)
        if [[ -z "$REMOTE" ]]; then
            echo "error: empty remote" >&2
            exit 2
        fi
        if [[ "$REMOTE" == -* ]]; then
            echo "error: remote must not start with dash" >&2
            exit 2
        fi
        check_branch_ref "$REF" "ref"
        taskref="refs/task/valve/$REF"
        if ! git check-ref-format "$taskref" > /dev/null 2>&1; then
            echo "error: malformed task ref: $taskref" >&2
            exit 2
        fi
        old_sha=""
        if old_sha="$(git -C "$REPO" rev-parse --verify --quiet --end-of-options "$taskref")" && [[ -n "$old_sha" ]]; then
            :
        else
            old_sha=""
        fi
        if ! git -C "$REPO" fetch --no-tags -- "$REMOTE" "+$REF:$taskref"; then
            fail "action=fetch ref=$REF"
        fi
        new_sha="$(git -C "$REPO" rev-parse --verify --end-of-options "$taskref")"
        if [[ -z "$old_sha" ]]; then
            echo "FETCH_OK ref=$REF taskref=$taskref status=new sha=$new_sha"
        elif [[ "$old_sha" == "$new_sha" ]]; then
            echo "FETCH_OK ref=$REF taskref=$taskref status=no-change sha=$new_sha"
        elif git -C "$REPO" merge-base --is-ancestor "$old_sha" "$new_sha"; then
            echo "FETCH_OK ref=$REF taskref=$taskref status=advanced old=$old_sha new=$new_sha"
        else
            echo "FETCH_OK ref=$REF taskref=$taskref status=rewritten old=$old_sha new=$new_sha"
        fi
        ;;
    check-pins)
        require_range "check-pins"
        base_sha="$RANGE_BASE"
        src_sha="$RANGE_SRC"
        ups_sha="$(resolve "$UPSTREAM")" || fail "action=check-pins missing=upstream rev=$UPSTREAM"
        mb="$(git -C "$REPO" merge-base "$ups_sha" "$src_sha")" \
            || fail "action=check-pins no-merge-base upstream=$ups_sha source=$src_sha"
        if [[ "$mb" != "$base_sha" ]]; then
            fail "action=check-pins base-mismatch merge-base=$mb base=$base_sha"
        fi
        n_valve="$(git -C "$REPO" rev-list --count "$base_sha..$src_sha")"
        n_ups="$(git -C "$REPO" rev-list --count "$base_sha..$ups_sha")"
        cherry_out="$(mktemp "${TMPDIR:-/tmp}/valve-cherry.XXXXXX")"
        trap 'rm -f "$cherry_out"' EXIT
        git -C "$REPO" cherry "$ups_sha" "$src_sha" "$base_sha" > "$cherry_out"
        n_minus="$(grep -c '^-' "$cherry_out" || true)"
        n_plus="$(grep -c '^+' "$cherry_out" || true)"
        rm -f "$cherry_out"
        trap - EXIT
        echo "PIN_OK base=$base_sha source=$src_sha upstream=$ups_sha merge-base=$mb"
        echo "COUNT_VALVE=$n_valve COUNT_UPSTREAM=$n_ups CHERRY_MINUS=$n_minus CHERRY_PLUS=$n_plus"
        ;;
    inventory)
        out="$ACTION_ARG"
        [[ -n "$out" ]] || { echo "error: --inventory needs a path" >&2; exit 2; }
        require_range "inventory"
        base_sha="$RANGE_BASE"
        src_sha="$RANGE_SRC"
        mkdir -p "$(dirname "$out")"
        tmp="$(mktemp "${TMPDIR:-/tmp}/valve-inv.XXXXXX")"
        trap 'rm -f "$tmp"' EXIT
        {
            echo "# valve-inventory v1"
            echo "# remote: $REMOTE"
            echo "# ref: $REF"
            echo "# base: $base_sha"
            echo "# source: $src_sha"
            echo "# source-date: $(git -C "$REPO" log -1 --format='%ad' --date=short "$src_sha")"
            echo -e "# sha\tauthor\tdate\tsubject"
            git -C "$REPO" log --reverse --format='%H%x09%an <%ae>%x09%ad%x09%s' \
                --date=short "$base_sha..$src_sha"
        } > "$tmp"
        n="$(( $(wc -l < "$tmp") - 7 ))"
        mv "$tmp" "$out"
        trap - EXIT
        echo "INVENTORY_OK file=$out commits=$n base=$base_sha source=$src_sha"
        ;;
    export)
        dir="$ACTION_ARG"
        [[ -n "$dir" ]] || { echo "error: --export needs a directory" >&2; exit 2; }
        require_range "export"
        base_sha="$RANGE_BASE"
        src_sha="$RANGE_SRC"
        shopt -s nullglob
        pre=( "$dir"/* )
        shopt -u nullglob
        if [[ -e "$dir" && "${#pre[@]}" -gt 0 ]]; then
            echo "error: export dir not empty (refusing to mix generations): $dir" >&2
            exit 1
        fi
        mkdir -p "$dir"
        expected="$(git -C "$REPO" rev-list --count "$base_sha..$src_sha")"
        if ! git -C "$REPO" format-patch --no-signature --output-directory="$dir" \
                "$base_sha..$src_sha" > /dev/null; then
            fail "action=export source=$src_sha"
        fi
        shopt -s nullglob
        made=( "$dir"/*.patch )
        shopt -u nullglob
        got="${#made[@]}"
        if [[ "$got" != "$expected" ]]; then
            fail "action=export count-mismatch patches=$got commits=$expected"
        fi
        {
            echo "valve-export v1"
            echo "base: $base_sha"
            echo "source: $src_sha"
            echo "patches: $got"
        } > "$dir/export.meta"
        echo "EXPORT_OK dir=$dir patches=$got base=$base_sha source=$src_sha"
        ;;
    verify)
        dir="$ACTION_ARG"
        [[ -n "$dir" ]] || { echo "error: --verify needs a directory" >&2; exit 2; }
        [[ -d "$dir" ]] || fail "action=verify missing-dir dir=$dir"
        require_range "verify"
        base_sha="$RANGE_BASE"
        src_sha="$RANGE_SRC"
        shopt -s nullglob
        patches=( "$dir"/*.patch )
        shopt -u nullglob
        expected="$(git -C "$REPO" rev-list --count "$base_sha..$src_sha")"
        if [[ "${#patches[@]}" != "$expected" ]]; then
            fail "action=verify count-mismatch patches=${#patches[@]} commits=$expected"
        fi
        wt="$(mktemp -d "${TMPDIR:-/tmp}/valve-verify.XXXXXX")"
        rmdir "$wt"
        cleanup() { git -C "$REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"; }
        trap cleanup EXIT
        git -C "$REPO" worktree add --detach "$wt" "$base_sha" > /dev/null \
            || fail "action=verify worktree-add base=$base_sha"
        for f in ${patches[@]+"${patches[@]}"}; do
            if ! git -C "$wt" -c user.name="valve-track" -c user.email="valve-track@localhost" \
                    am --quiet --empty=keep "$f" > /dev/null 2>&1; then
                git -C "$wt" am --abort > /dev/null 2>&1 || true
                fail "action=verify apply file=$(basename "$f")"
            fi
        done
        t_got="$(git -C "$wt" rev-parse 'HEAD^{tree}')"
        t_want="$(git -C "$REPO" rev-parse "$src_sha^{tree}")"
        if [[ "$t_got" != "$t_want" ]]; then
            fail "action=verify tree-mismatch got=$t_got want=$t_want"
        fi
        git -C "$REPO" worktree remove --force "$wt"
        trap - EXIT
        echo "VERIFY_OK dir=$dir patches=${#patches[@]} tree=$t_got source=$src_sha"
        ;;
    conflicts)
        out="$ACTION_ARG"
        [[ -n "$out" ]] || { echo "error: --conflicts needs a path" >&2; exit 2; }
        require_range "conflicts"
        src_sha="$RANGE_SRC"
        ups_sha="$(resolve "$UPSTREAM")" || fail "action=conflicts missing=upstream rev=$UPSTREAM"
        mkdir -p "$(dirname "$out")"
        tmp="$(mktemp "${TMPDIR:-/tmp}/valve-conf.XXXXXX")"
        trap 'rm -f "$tmp"' EXIT
        status=0
        git -C "$REPO" merge-tree --write-tree --name-only --no-messages \
            "$ups_sha" "$src_sha" > "$tmp" 2>/dev/null || status=$?
        if [[ "$status" != 0 && "$status" != 1 ]]; then
            fail "action=conflicts merge-tree status=$status"
        fi
        tail -n +2 "$tmp" > "$out"
        n="$(wc -l < "$out")"
        rm -f "$tmp"
        trap - EXIT
        echo "CONFLICT_FILES=$n file=$out upstream=$ups_sha source=$src_sha"
        ;;
    *)
        echo "error: unknown action: $ACTION" >&2
        exit 2
        ;;
esac

#!/usr/bin/env python3

import argparse
import collections
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

GENERATED = (
    "include/wine/server_protocol.h",
    "server/request_handlers.h",
    "server/request_trace.h",
)
APPLY_FLAGS = ["apply", "--cached", "-p1", "--whitespace=fix"]
DEFAULT_ABBREV = 11


class Fatal(Exception):
    pass


class Git:
    def __init__(self, repo, tmpdir):
        self.repo = repo
        empty = os.path.join(tmpdir, "empty.gitconfig")
        open(empty, "wb").close()
        self.env = dict(os.environ)
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"
        self.env["GIT_CONFIG_GLOBAL"] = empty
        self.env.pop("GIT_INDEX_FILE", None)
        self.env["LC_ALL"] = "C"

    def run(self, args, index=None, input=None, ok=(0,)):
        env = self.env
        if index is not None:
            env = dict(env)
            env["GIT_INDEX_FILE"] = index
        p = subprocess.run(["git"] + args, cwd=self.repo, env=env, input=input,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ok is not None and p.returncode not in ok:
            raise Fatal("git %s failed (%d): %s" % (
                " ".join(args[:4]), p.returncode,
                p.stderr.decode("utf-8", "replace").strip()))
        return p

    def out(self, args, **kw):
        return self.run(args, **kw).stdout

    def rev(self, name):
        p = self.run(["rev-parse", "--verify", "-q", name + "^{commit}"], ok=None)
        if p.returncode != 0:
            raise Fatal("cannot resolve commit: %s" % name)
        return p.stdout.decode().strip()

    def tree_of(self, rev):
        return self.out(["rev-parse", rev + "^{tree}"]).decode().strip()

    def changed_paths(self, a, b):
        if a == b:
            return []
        raw = self.out(["diff-tree", "-r", "-z", "--name-only", "--no-renames", a, b])
        return [x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x]



class PatchSource:

    def __init__(self, git, ref=None):
        self.git, self.ref = git, ref

    def read(self, rel):
        if self.ref is None:
            path = os.path.join(self.git.repo, rel)
            if not os.path.isfile(path):
                return None
            with open(path, "rb") as f:
                return f.read()
        p = self.git.run(["cat-file", "blob", "%s:%s" % (self.ref, rel)], ok=None)
        return p.stdout if p.returncode == 0 else None

    def isdir(self, rel):
        if self.ref is None:
            return os.path.isdir(os.path.join(self.git.repo, rel))
        p = self.git.run(["cat-file", "-t", "%s:%s" % (self.ref, rel)], ok=None)
        return p.returncode == 0 and p.stdout.strip() == b"tree"

    def patch_files(self, d):
        if self.ref is None:
            names = os.listdir(os.path.join(self.git.repo, d))
            names = [n for n in names if os.path.isfile(os.path.join(self.git.repo, d, n))]
        else:
            raw = self.git.out(["ls-tree", "-z", "--name-only", "%s:%s" % (self.ref, d)])
            names = [x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x]
        names = [n for n in names if n.endswith(".patch") and not n.startswith(".")]
        return sorted(names, key=lambda n: n.encode("utf-8", "surrogateescape"))


def parse_series(text, excludes):
    order = []
    for line in text.decode("utf-8", "surrogateescape").split("\n"):
        line = line.split("#", 1)[0]
        line = re.sub(r"\s", "", line)
        if line and line not in excludes:
            order.append(line)
    return order


def load_stack(src, excludes):
    series = src.read("patches/series.conf")
    if series is None:
        raise Fatal("series.conf not found")
    stack, warnings = [], []
    for ps in parse_series(series, excludes):
        d = "patches/" + ps
        if not src.isdir(d):
            raise Fatal("FAILED patchset=%s file=(missing directory %s)" % (ps, d))
        if src.read(d + "/definition") is None:
            raise Fatal("FAILED patchset=%s file=(missing definition)" % ps)
        files = src.patch_files(d)
        if not files:
            warnings.append("patchset=%s has no *.patch, skipped" % ps)
        for f in files:
            stack.append(Patch(ps, f, src.read(d + "/" + f)))
    return stack, warnings


class Patch:
    def __init__(self, patchset, name, data):
        self.patchset, self.name, self.data = patchset, name, data
        self.path = "patches/%s/%s" % (patchset, name)
        self.status, self.detail = None, ""
        self.conflicts, self.blocked_by, self.evidence = [], [], []
        self.touched = []
        self.new_data = None
        self.generated = False
        self.provisional = False

    def label(self):
        return "%s/%s" % (self.patchset, self.name)



DIFF_START = re.compile(rb"^(diff --git |diff |Index: )")
TRAILER = re.compile(rb"\n(-- \n[0-9][0-9A-Za-z.\-+]*\n\n*)\Z")
INDEX_LINE = re.compile(rb"^index ([0-9a-f]+)\.\.([0-9a-f]+)((?: [0-7]+)?)$")


def split_patch(data):
    lines = data.split(b"\n")
    start = None
    for i, l in enumerate(lines):
        if DIFF_START.match(l):
            start = i
            break
        if l.startswith(b"--- ") and i + 1 < len(lines) and lines[i + 1].startswith(b"+++ "):
            start = i
            break
    if start is None:
        return data, b"", b""
    header = b"\n".join(lines[:start]) + (b"\n" if start else b"")
    rest = b"\n".join(lines[start:])
    trailer = b""
    m = TRAILER.search(rest)
    if m:
        trailer = m.group(1)
        rest = rest[:m.start() + 1]
    return header, rest, trailer


def abbrev_of(data):
    c = collections.Counter(len(m.group(1)) for m in
                            (INDEX_LINE.match(l) for l in data.split(b"\n")) if m)
    return c.most_common(1)[0][0] if c else DEFAULT_ABBREV


def count_changes(body):
    add = rem = 0
    for l in body.split(b"\n"):
        if l.startswith(b"+++ ") or l.startswith(b"--- "):
            continue
        if l.startswith(b"+"):
            add += 1
        elif l.startswith(b"-"):
            rem += 1
    return add, rem


def render_body(git, a, b, renames, abbrev):
    args = ["-c", "core.quotepath=false", "-c", "diff.noprefix=false",
            "-c", "diff.mnemonicPrefix=false", "-c", "color.ui=false",
            "diff-tree", "-p", "-r", "--full-index", "--binary", "-U3",
            "--diff-algorithm=myers", "--no-color", "--no-ext-diff", "--no-textconv",
            "--src-prefix=a/", "--dst-prefix=b/"]
    args.append("-M" if renames else "--no-renames")
    raw = git.out(args + [a, b])
    out = []
    sections = re.split(rb"(?m)^(?=diff --git )", raw)
    for sec in sections:
        if not sec:
            continue
        keep_full = b"\nGIT binary patch\n" in sec
        lines = sec.split(b"\n")
        for i, l in enumerate(lines):
            m = INDEX_LINE.match(l)
            if m and not keep_full:
                lines[i] = b"index %s..%s%s" % (m.group(1)[:abbrev], m.group(2)[:abbrev], m.group(3))
                break
        out.append(b"\n".join(lines))
    return b"".join(out)



def regenerate(git, tmpdir, index, tree):
    work = tempfile.mkdtemp(prefix="mkreq-", dir=tmpdir)
    try:
        listing = git.out(["ls-tree", "-z", tree, "--", "server/", "tools/make_requests",
                           "include/wine/server_protocol.h"])
        entries = []
        for rec in listing.split(b"\0"):
            if not rec:
                continue
            meta, path = rec.split(b"\t", 1)
            mode, typ, oid = meta.split(b" ")
            path = path.decode("utf-8", "surrogateescape")
            if typ != b"blob":
                continue
            if path.startswith("server/") and not (path.endswith(".c") or path == "server/protocol.def"):
                continue
            entries.append((path, oid.decode()))
        need = {"server/protocol.def", "tools/make_requests"}
        if not need <= {p for p, _ in entries}:
            return False
        batch = git.out(["cat-file", "--batch"], input=b"".join(o.encode() + b"\n" for _, o in entries))
        pos = 0
        for path, oid in entries:
            nl = batch.index(b"\n", pos)
            size = int(batch[pos:nl].split(b" ")[2])
            content = batch[nl + 1:nl + 1 + size]
            pos = nl + 1 + size + 1
            dst = os.path.join(work, *path.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(content)
        p = subprocess.run(["perl", "tools/make_requests"], cwd=work,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            raise Fatal("make_requests failed: %s" % p.stderr.decode("utf-8", "replace"))
        for g in GENERATED:
            dst = os.path.join(work, *g.split("/"))
            if not os.path.isfile(dst):
                continue
            oid = git.out(["hash-object", "-w", "--no-filters", dst]).decode().strip()
            git.out(["update-index", "--add", "--cacheinfo", "100644,%s,%s" % (oid, g)], index=index)
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)



class Retargeter:
    def __init__(self, git, tmpdir, old_base, new_base, stack, allow_old_fail,
                 old_tree=None, new_tree=None):
        self.git, self.tmpdir = git, tmpdir
        self.old_base, self.new_base = old_base, new_base
        self.old_tree = old_tree or git.tree_of(old_base)
        self.new_tree = new_tree or git.tree_of(new_base)
        self.stack, self.allow_old_fail = stack, allow_old_fail
        self.idx_old = os.path.join(tmpdir, "old.idx")
        self.idx_new = os.path.join(tmpdir, "new.idx")
        self.idx_tmp = os.path.join(tmpdir, "tmp.idx")
        self.final_tree = None

    def apply(self, data, index):
        return self.git.run(APPLY_FLAGS, index=index, input=data, ok=None).returncode == 0

    def write_tree(self, index):
        return self.git.out(["write-tree"], index=index).decode().strip()

    def read_tree(self, tree, index):
        self.git.out(["read-tree", tree], index=index)

    def old_chain(self):
        git = self.git
        cur = self.old_tree
        self.read_tree(cur, self.idx_old)
        for p in self.stack:
            p.old_prev = cur
            if not self.apply(p.data, self.idx_old):
                if not self.allow_old_fail:
                    raise Fatal("stack is not strict-green on old base %s: %s" % (
                        self.old_base[:12], p.label()))
                p.status = "OLD-FAIL"
                p.detail = "does not apply strictly on old base; skipped"
                p.old_next = cur
                continue
            cur = self.write_tree(self.idx_old)
            p.old_next = cur

    def merge(self, base, ours, theirs):
        p = self.git.run(["merge-tree", "--write-tree", "-z", "--name-only",
                          "--merge-base=" + base, ours, theirs], ok=(0, 1))
        fields = p.stdout.split(b"\0")
        tree = fields[0].decode().strip()
        paths = []
        for f in fields[1:]:
            if not f:
                break
            paths.append(f.decode("utf-8", "surrogateescape"))
        return tree, paths

    def new_chain(self):
        git = self.git
        cur = self.new_tree
        self.read_tree(cur, self.idx_new)
        skipped = []
        for p in self.stack:
            p.touched = git.changed_paths(p.old_prev, p.old_next)
            if p.status == "OLD-FAIL":
                skipped.append((p, self._paths_of_text(p.data)))
                continue
            touched_ng = set(p.touched) - set(GENERATED)
            near = [q.label() for q, paths in skipped if paths & touched_ng]
            near_note = "touches files of skipped " + ", ".join(near) if near else ""
            if self.apply(p.data, self.idx_new):
                cur = self.write_tree(self.idx_new)
                p.status = "OK"
                p.detail = near_note
                continue
            tree, conflicts = self.merge(p.old_prev, cur, p.old_next)
            hard = [c for c in conflicts if c not in GENERATED]
            if hard:
                blockers = [q.label() for q, paths in skipped if paths & set(hard)]
                p.conflicts = conflicts
                if blockers:
                    p.status = "BLOCKED-BY"
                    p.blocked_by = blockers
                    p.detail = "BLOCKED-BY:%s (conflicts: %s)" % (blockers[0], ", ".join(hard))
                else:
                    p.status = "CONFLICT"
                    p.detail = "conflicts: " + ", ".join(conflicts)
                skipped.append((p, touched_ng))
                continue
            gen_touched = [g for g in GENERATED if g in p.touched]
            changes_protocol = "server/protocol.def" in p.touched
            if conflicts and not changes_protocol:
                p.status = "CONFLICT"
                p.conflicts = conflicts
                p.detail = ("conflicts only in generated files, but the patch does not change "
                            "server/protocol.def, so they cannot be regenerated: "
                            + ", ".join(conflicts))
                skipped.append((p, touched_ng))
                continue
            if gen_touched and changes_protocol:
                tree = self._fix_generated(tree, cur, gen_touched)
                p.generated = True
            if tree == cur:
                p.status = "ABSORBED"
                self._evidence(p)
                p.detail = "; ".join(x for x in (p.detail, near_note) if x)
                continue
            self._rebuild(p, cur, tree)
            if p.status == "CONFLICT":
                skipped.append((p, touched_ng))
                continue
            if near:
                p.provisional = True
                near_note = "provisional, not written: " + near_note
            p.detail = "; ".join(x for x in (p.detail, near_note) if x)
            cur = tree
        self.final_tree = cur

    @staticmethod
    def _paths_of_text(data):
        paths = set()
        for l in data.split(b"\n"):
            m = re.match(rb"^diff --git a/(\S+) ", l) or re.match(rb"^\+\+\+ b/([^\t\n]+)", l)
            if m:
                paths.add(m.group(1).decode("utf-8", "surrogateescape"))
        return paths - set(GENERATED)

    def _fix_generated(self, tree, cur, gen_touched):
        git = self.git
        self.read_tree(tree, self.idx_tmp)
        for g in gen_touched:
            ent = git.out(["ls-tree", cur, "--", g]).split(b"\t")[0].split(b" ")
            if len(ent) == 3:
                git.out(["update-index", "--add", "--cacheinfo",
                         "%s,%s,%s" % (ent[0].decode(), ent[2].decode(), g)], index=self.idx_tmp)
            else:
                git.out(["update-index", "--force-remove", "--", g], index=self.idx_tmp)
        staged = self.write_tree(self.idx_tmp)
        regenerate(git, self.tmpdir, self.idx_tmp, staged)
        return self.write_tree(self.idx_tmp)

    def _rebuild(self, p, cur, tree):
        git = self.git
        header, body, trailer = split_patch(p.data)
        renames = re.search(rb"(?m)^(rename|copy) from ", p.data) is not None
        new_body = render_body(git, cur, tree, renames, abbrev_of(p.data))
        new_data = header + new_body + trailer
        if not self.apply(new_data, self.idx_new) or self.write_tree(self.idx_new) != tree:
            self.read_tree(cur, self.idx_new)
            p.status = "CONFLICT"
            p.detail = "rewritten patch failed verification (merge result not reproducible)"
            return
        p.status = "RETARGETED"
        p.new_data = new_data
        notes = []
        if p.generated:
            notes.append("generated files regenerated")
        oa, orm = count_changes(body)
        na, nrm = count_changes(new_body)
        if na < oa or nrm < orm:
            notes.append("hunks shrank +%d/-%d -> +%d/-%d (partial absorption?)" % (oa, orm, na, nrm))
        if b"\n---\n" in header and re.search(rb"(?m)^ \d+ files? changed", header):
            notes.append("diffstat in header is stale")
        p.detail = "; ".join(notes)

    def _evidence(self, p):
        git = self.git
        diff = git.out(["diff-tree", "-p", "-r", "--no-renames", "-U0", p.old_prev, p.old_next])
        cands, cur_file = [], None
        for l in diff.split(b"\n"):
            if l.startswith(b"+++ b/"):
                cur_file = l[6:]
            elif l.startswith(b"--- a/") and cur_file is None:
                cur_file = l[6:]
            elif l.startswith(b"diff --git "):
                cur_file = None
            elif (l.startswith(b"+") or l.startswith(b"-")) and not l.startswith((b"+++", b"---")):
                s = l[1:].strip()
                if len(s) >= 12 and re.search(rb"[A-Za-z_]{4}", s) and cur_file:
                    cands.append((len(s), l[:1] == b"+", s, cur_file))
        cands.sort(key=lambda c: (not c[1], -c[0]))
        hits = collections.Counter()
        for _, _, s, f in cands[:4]:
            try:
                arg, path = s.decode("utf-8"), f.decode("utf-8")
            except UnicodeDecodeError:
                continue
            r = git.run(["log", "--format=%H", "-S" + arg, "%s..%s" % (self.old_base, self.new_base),
                         "--", path], ok=None)
            for h in r.stdout.decode().split():
                hits[h] += 1
        if hits:
            p.evidence = [h for h, _ in hits.most_common(3)]
            p.detail = "evidence " + " ".join(h[:11] for h in p.evidence)
        else:
            p.detail = "ABSORBED-NO-EVIDENCE"



STATUSES = ["OK", "RETARGETED", "ABSORBED", "CONFLICT", "BLOCKED-BY", "OLD-FAIL"]


def obsolete_lines(stack):
    today = datetime.date.today().isoformat()
    by_set = collections.OrderedDict()
    for p in stack:
        by_set.setdefault(p.patchset, []).append(p)
    out = []
    for ps, ps_list in by_set.items():
        if all(p.status == "ABSORBED" for p in ps_list):
            ev = [p.evidence[0][:11] for p in ps_list if p.evidence]
            if ev:
                out.append("# OBSOLETE %s (absorbed upstream; evidence %s): %s" % (
                    today, " ".join(sorted(set(ev))), ps))
            else:
                out.append("(no evidence found, cannot retire under R1): %s" % ps)
    return out


def summary(stack):
    c = collections.Counter(p.status for p in stack)
    return {s: c.get(s, 0) for s in STATUSES}


def write_report(path, args, stack, counts, warnings):
    lines = ["# Patch retarget report", "",
             "- old base: `%s`" % args.old_base, "- new base: `%s`" % args.new_base,
             "- patches: %s" % (args.patches_ref or "working tree"), "",
             "| status | count |", "|---|---|"]
    lines += ["| %s | %d |" % (s, n) for s, n in counts.items() if n]
    for w in warnings:
        lines.append("\nwarning: " + w)
    lines += ["", "| patchset | file | status | detail |", "|---|---|---|---|"]
    for p in stack:
        if p.status == "OK" and not p.detail and not args.report_ok:
            continue
        lines.append("| %s | %s | %s | %s |" % (p.patchset, p.name, p.status,
                                                p.detail.replace("|", "\\|")))
    obs = obsolete_lines(stack)
    if obs:
        lines += ["", "## Fully absorbed patchsets", "",
                  "Decision is the human's (GOVERNANCE R1). series.conf line to use:", "", "```"]
        lines += obs + ["```"]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def write_json(path, args, stack, counts, final_tree):
    doc = {"old_base": args.old_base, "new_base": args.new_base,
           "patches_ref": args.patches_ref, "counts": counts, "final_tree": final_tree,
           "patches": [{"patchset": p.patchset, "file": p.name, "status": p.status,
                        "detail": p.detail, "conflicts": p.conflicts,
                        "blocked_by": p.blocked_by, "evidence": p.evidence,
                        "generated": p.generated, "provisional": p.provisional,
                        "touched": p.touched}
                       for p in stack],
           "obsolete_suggestions": obsolete_lines(stack)}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")


def overlay_tree(git, base, ov, new_base):
    up = git.out(["merge-base", ov, new_base]).decode().strip()
    p = git.run(["merge-tree", "--write-tree", "-z", "--name-only", "--merge-base=" + up,
                 base, ov], ok=(0, 1))
    if p.returncode != 0:
        raise Fatal("overlay %s does not merge cleanly onto %s" % (ov[:12], base[:12]))
    return p.stdout.split(b"\0")[0].decode().strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Retarget patches/ onto a new upstream base.")
    ap.add_argument("--old-base", help="default: merge-base of HEAD and mirror/master")
    ap.add_argument("--new-base", default="mirror/master")
    ap.add_argument("--patches-ref", help="read patches/ from this ref instead of the work tree")
    ap.add_argument("-W", dest="excludes", action="append", default=[], metavar="NAME",
                    help="exclude patchset NAME (repeatable, like apply-patches.sh)")
    ap.add_argument("--write", action="store_true",
                    help="rewrite RETARGETED patch files in the work tree")
    ap.add_argument("--write-provisional", action="store_true",
                    help="also write RETARGETED patches merged while files they touch "
                    "belong to a skipped CONFLICT/BLOCKED patch")
    ap.add_argument("--out-dir", help="write RETARGETED patch files under DIR/patches/...")
    ap.add_argument("--report", help="Markdown report path")
    ap.add_argument("--json", help="JSON report path")
    ap.add_argument("--report-ok", action="store_true", help="list OK patches in the table too")
    ap.add_argument("--allow-old-fail", action="store_true",
                    help="skip patches that fail on old base instead of aborting")
    ap.add_argument("--overlay", help="commit whose non-upstream files (e.g. .gitignore) are "
                    "laid over both bases, as the gate sees them (default: --patches-ref or HEAD)")
    ap.add_argument("--no-overlay", action="store_true", help="use the bare base trees")
    ap.add_argument("-C", dest="repo", help="repository (default: this script's repo)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if args.write and args.patches_ref:
        print("error: --write needs work-tree patches (drop --patches-ref or use --out-dir)",
              file=sys.stderr)
        return 2

    repo = args.repo or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmpdir = tempfile.mkdtemp(prefix="retarget-")
    try:
        git = Git(repo, tmpdir)
        top = git.run(["rev-parse", "--show-toplevel"], ok=None)
        if top.returncode != 0:
            raise Fatal("not a git repository: %s" % repo)
        git.repo = top.stdout.decode().strip()
        args.new_base = git.rev(args.new_base)
        if not args.old_base:
            args.old_base = git.out(["merge-base", "HEAD", args.new_base]).decode().strip()
        args.old_base = git.rev(args.old_base)
        if args.patches_ref:
            git.rev(args.patches_ref)
        stack, warnings = load_stack(PatchSource(git, args.patches_ref), set(args.excludes))
        for w in warnings:
            print("warn: " + w, file=sys.stderr)
        old_tree = new_tree = None
        if not args.no_overlay:
            ov = git.rev(args.overlay or args.patches_ref or "HEAD")
            old_tree = overlay_tree(git, args.old_base, ov, args.new_base)
            new_tree = overlay_tree(git, args.new_base, ov, args.new_base)
        rt = Retargeter(git, tmpdir, args.old_base, args.new_base, stack, args.allow_old_fail,
                        old_tree, new_tree)
        rt.old_chain()
        rt.new_chain()
    except Fatal as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    counts = summary(stack)
    for p in stack:
        if p.status != "RETARGETED" or (p.provisional and not args.write_provisional):
            continue
        targets = []
        if args.write:
            targets.append(os.path.join(git.repo, *p.path.split("/")))
        if args.out_dir:
            targets.append(os.path.join(args.out_dir, *p.path.split("/")))
        for t in targets:
            os.makedirs(os.path.dirname(t), exist_ok=True)
            with open(t, "wb") as f:
                f.write(p.new_data)
    if args.report:
        write_report(args.report, args, stack, counts, warnings)
    if args.json:
        write_json(args.json, args, stack, counts, rt.final_tree)
    print(" ".join("%s=%d" % kv for kv in counts.items()))
    for p in stack:
        if p.status in ("CONFLICT", "BLOCKED-BY"):
            print("%s %s %s" % (p.status, p.label(), p.detail))
    return 1 if counts["CONFLICT"] or counts["BLOCKED-BY"] else 0


if __name__ == "__main__":
    sys.exit(main())

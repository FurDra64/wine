#!/usr/bin/env python3
import sys

sys.dont_write_bytecode = True

import argparse
import collections
import difflib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile


def load_retarget():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retarget-patches.py")
    spec = importlib.util.spec_from_file_location("retarget_patches", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rt = load_retarget()
Fatal = rt.Fatal

STATUSES = ["UPDATE-APPLIES", "UPDATE-MERGED", "UPDATE-CONFLICT", "UNMATCHED",
            "NEW-APPLIES", "NEW-CONFLICT", "NEW-UNUSED", "DELETED-IN-GE", "INACTIVE",
            "UP-TO-DATE", "IGNORED", "PROTON-SIDE"]
WRITABLE = ("UPDATE-APPLIES", "UPDATE-MERGED", "NEW-APPLIES")
LEFT_FOR_HUMAN = ("UPDATE-CONFLICT", "UNMATCHED", "NEW-CONFLICT", "DELETED-IN-GE", "INACTIVE")
PROVENANCE = re.compile(r"(?:Ported from GE-Proton|from proton-ge-custom)\s+(\S+)")
PATCH_NAME = re.compile(r"^[0-9]{4}[a-z]?-.+\.patch$")
LEADING_NUMBER = re.compile(r"^([0-9]+)([a-z]?)-(.+)$")
SERIES_NAME = re.compile(r"[_A-Za-z0-9][_A-Za-z0-9.+@-]*")
COMMENTED_ENTRY = re.compile(r"^\s*#+\s*[A-Z][A-Z0-9-]*\b.*:\s*(%s)\s*$" % SERIES_NAME.pattern)
HUNK_FULL = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
APPLY_ERROR_PATH = re.compile(r"^error: (?:patch failed: )?(.+?)(?::\d+)?(?:: .*)?$")
PROTONPREP = "patches/protonprep-valve-staging.sh"
PROTONPREP_FILE = re.compile(r"\.\./patches/([^\"'\s]+\.patch)")
PROTONPREP_DIR = re.compile(r"(?:apply_all_in_dir\s+[\"']?|for \w+ in )\.\./patches/([^\"'\s*]+?)/?(?:\*\.patch)?[\"']?(?:;|\s|$)")


def ge_rel(path):
    path = path.rstrip(".,;")
    if path.startswith("patches/"):
        path = path[len("patches/"):]
    if not path.endswith(".patch") and not path.endswith("/"):
        path += "/"
    return path


def dir_of(rel):
    return rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""


def base_name(rel):
    return rel.rsplit("/", 1)[-1]


def subject_of(data):
    if not data:
        return ""
    lines = data.split(b"\n")
    for i, line in enumerate(lines):
        if rt.GIT_DIFF.match(line):
            break
        if line.startswith(b"Subject:"):
            text = line[len(b"Subject:"):].strip()
            j = i + 1
            while j < len(lines) and lines[j][:1] in (b" ", b"\t") and lines[j].strip():
                text += b" " + lines[j].strip()
                j += 1
            return text.decode("utf-8", "replace")
    return ""


def bare_subject(data):
    return re.sub(r"^\[PATCH[^\]]*\]\s*", "", subject_of(data)).strip()


def stem_of(name):
    stem = name[:-len(".patch")] if name.endswith(".patch") else name
    m = LEADING_NUMBER.match(stem)
    return m.group(3) if m else stem


def numbered_name(name, fallback_number=1):
    if PATCH_NAME.match(name):
        return name
    stem = name[:-len(".patch")] if name.endswith(".patch") else name
    m = LEADING_NUMBER.match(stem)
    if m:
        return "%04d%s-%s.patch" % (int(m.group(1)), m.group(2), m.group(3))
    return "%04d-%s.patch" % (fallback_number, stem)


def series_safe(name):
    return re.sub(r"[^_A-Za-z0-9.+@-]", "-", name)


def normalized_body(data):
    _, body, _ = rt.split_patch(data)
    out = []
    for line in body.split(b"\n"):
        if rt.INDEX_LINE.match(line):
            continue
        m = HUNK_FULL.match(line)
        if m:
            old = b"-0,0" if m.group(1) == b"0" and m.group(2) == b"0" else b"-2"
            new = b"+0,0" if m.group(3) == b"0" and m.group(4) == b"0" else b"+2"
            out.append(b"@@ " + old + b" " + new + b" @@")
            continue
        out.append(line)
    return b"\n".join(out)


def touched_files(data):
    files = []
    lines = data.split(b"\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(rb"^diff --git a/(\S+) b/(\S+)", line)
        if m:
            new = False
            j = i + 1
            while j < len(lines) and not lines[j].startswith((b"diff --git ", b"@@")):
                if lines[j].startswith(b"new file mode") or lines[j] == b"--- /dev/null":
                    new = True
                j += 1
            src = m.group(1).decode("utf-8", "surrogateescape")
            dst = m.group(2).decode("utf-8", "surrogateescape")
            files.append((dst, new))
            if src != dst:
                files.append((src, False))
            i = j
            continue
        if line.startswith(b"--- ") and i + 1 < len(lines) and lines[i + 1].startswith(b"+++ "):
            src = line[4:].split(b"\t")[0].strip()
            dst = lines[i + 1][4:].split(b"\t")[0].strip()
            if dst.startswith(b"b/"):
                files.append((dst[2:].decode("utf-8", "surrogateescape"), src == b"/dev/null"))
            elif src.startswith(b"a/"):
                files.append((src[2:].decode("utf-8", "surrogateescape"), False))
            i += 2
            continue
        i += 1
    seen, out = set(), []
    for path, new in files:
        if path not in seen:
            seen.add(path)
            out.append((path, new))
    return out


def text_delta(old, new, old_label, new_label):
    a = (old or b"").decode("utf-8", "replace").splitlines(keepends=True)
    b = (new or b"").decode("utf-8", "replace").splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, old_label, new_label, n=2))


class Entry:
    def __init__(self, patchset, name, data, skip=False):
        self.patchset, self.name, self.data, self.skip = patchset, name, data, skip

    def label(self):
        return "%s/%s" % (self.patchset, self.name)


class Item:
    def __init__(self, change, rel, old, new):
        self.change, self.rel, self.old, self.new = change, rel, old, new
        self.status, self.detail = None, ""
        self.patchset = self.wine_file = self.target_file = None
        self.wine_data = self.result = None
        self.index = None
        self.insert_key = None
        self.drop_index = None
        self.proposal = None
        self.conflicts = []
        self.delta = ""
        self.deleted_by = ""
        self.renamed_from = None

    def label(self):
        return self.rel if not self.renamed_from else "%s -> %s" % (self.renamed_from, self.rel)


class Proposal:
    def __init__(self, name, provenance, summary, author, family):
        self.name, self.provenance, self.summary = name, provenance, summary
        self.author, self.family = author, family
        self.files = []
        self.items = []
        self.slot_line = None
        self.anchor_line = None
        self.position = None
        self.candidates = []
        self.order = 0

    def definition(self):
        desc = "Ported from GE-Proton %s." % self.provenance
        if self.summary:
            desc += " " + self.summary
        return ("Feature: %s\nDescription: %s\nAuthor: %s\nUpstream-Status: none\n"
                "Depends-On: none\n" % (self.name, desc, self.author)).encode("utf-8")


class Series:
    def __init__(self, text):
        self.lines = text.decode("utf-8", "surrogateescape").split("\n")

    def active(self):
        out = []
        for n, line in enumerate(self.lines):
            name = re.sub(r"\s", "", line.split("#", 1)[0])
            if name:
                out.append((n, name))
        return out

    def mentions(self):
        out = {}
        for n, name in self.active():
            out.setdefault(name, n)
        for n, line in enumerate(self.lines):
            m = COMMENTED_ENTRY.match(line)
            if m:
                out.setdefault(m.group(1), n)
        return out


class Wine:
    def __init__(self, git, src, base_tree, allow_old_fail, tmpdir):
        self.git, self.src, self.base_tree = git, src, base_tree
        self.allow_old_fail = allow_old_fail
        self.idx_chain = os.path.join(tmpdir, "chain.idx")
        self.idx_try = os.path.join(tmpdir, "try.idx")
        self.tmpdir = tmpdir
        series = src.read("patches/series.conf")
        if series is None:
            raise Fatal("series.conf not found")
        self.series = Series(series)
        self.stack, self.series_start, self.warnings = [], {}, []
        self.missing = {}
        for line_no, ps in self.series.active():
            self.series_start[line_no] = len(self.stack)
            d = "patches/" + ps
            if not src.isdir(d) or src.read(d + "/definition") is None:
                self.missing[ps] = line_no
                self.warnings.append("series entry %s has no patchset directory; treated as a "
                                     "reserved slot" % ps)
                continue
            for f in src.patch_files(d):
                self.stack.append(Entry(ps, f, src.read(d + "/" + f)))
        self.active_sets = {ps for _, ps in self.series.active() if ps not in self.missing}
        self.dirs = self.patchset_dirs()
        self.prev = []

    def patchset_dirs(self):
        if self.src.ref is None:
            root = os.path.join(self.git.repo, "patches")
            names = [n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))]
        else:
            raw = self.git.out(["ls-tree", "-z", "-d", "--name-only", "%s:patches" % self.src.ref])
            names = [x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x]
        return sorted(n for n in names if self.src.read("patches/%s/definition" % n) is not None)

    def files_of(self, ps, sub=""):
        d = "patches/%s%s" % (ps, "/" + sub if sub else "")
        if not self.src.isdir(d):
            return []
        return self.src.patch_files(d)

    def read(self, ps, name, sub=""):
        return self.src.read("patches/%s/%s%s" % (ps, sub + "/" if sub else "", name))

    def apply(self, data, index):
        return self.git.run(rt.APPLY_FLAGS, index=index, input=data, ok=None)

    def write_tree(self, index):
        return self.git.out(["write-tree"], index=index).decode().strip()

    def read_tree(self, tree, index):
        self.git.out(["read-tree", tree], index=index)

    def baseline(self):
        cur = self.base_tree
        self.read_tree(cur, self.idx_chain)
        self.prev = []
        for e in self.stack:
            self.prev.append(cur)
            if self.apply(e.data, self.idx_chain).returncode != 0:
                if not self.allow_old_fail:
                    raise Fatal("stack is not strict-green on %s: %s" % (self.base_tree[:12], e.label()))
                e.skip = True
                self.warnings.append("baseline: %s does not apply; skipped" % e.label())
                continue
            cur = self.write_tree(self.idx_chain)
        self.prev.append(cur)
        return cur

    def try_apply(self, tree, datas, recount=False):
        self.read_tree(tree, self.idx_try)
        for data in datas:
            flags = list(rt.APPLY_FLAGS) + (["--recount"] if recount else [])
            p = self.git.run(flags, index=self.idx_try, input=data, ok=None)
            if p.returncode != 0:
                return None, failing_paths(p.stderr)
        return self.write_tree(self.idx_try), []

    def chain(self, entries, start, start_tree):
        cur = start_tree
        self.read_tree(cur, self.idx_chain)
        for k in range(start, len(entries)):
            e = entries[k]
            if e.skip:
                continue
            p = self.apply(e.data, self.idx_chain)
            if p.returncode != 0:
                return k, failing_paths(p.stderr), None
            cur = self.write_tree(self.idx_chain)
        return None, [], cur

    def position_after_line(self, line_no):
        for n, _ in self.series.active():
            if n > line_no and n in self.series_start:
                return self.series_start[n]
        return len(self.stack)

    def range_of(self, ps):
        idx = [i for i, e in enumerate(self.stack) if e.patchset == ps]
        return (idx[0], idx[-1] + 1) if idx else (None, None)


def failing_paths(stderr):
    out = []
    for line in stderr.decode("utf-8", "replace").splitlines():
        m = APPLY_ERROR_PATH.match(line)
        if m and m.group(1) not in out and " " not in m.group(1):
            out.append(m.group(1))
    return out


def provenance_map(wine):
    files, dirs, dup = {}, {}, []
    for ps in wine.dirs:
        text = wine.src.read("patches/%s/definition" % ps).decode("utf-8", "replace")
        m = PROVENANCE.search(text)
        if not m:
            continue
        rel = ge_rel(m.group(1))
        table = dirs if rel.endswith("/") else files
        if rel in table and table[rel] != ps:
            dup.append("GE path %s claimed by %s and %s" % (rel, table[rel], ps))
            continue
        table[rel] = ps
    return files, dirs, dup


def protonprep_order(ge, ref):
    text = rt.PatchSource(ge, ref).read(PROTONPREP)
    if text is None:
        return None
    order = {}
    for n, line in enumerate(text.decode("utf-8", "replace").split("\n")):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for m in PROTONPREP_FILE.finditer(line):
            order.setdefault(m.group(1), n)
        m = PROTONPREP_DIR.search(line)
        if m:
            order.setdefault(m.group(1).rstrip("/") + "/", n)
    return order


def prep_index(order, rel):
    if order is None:
        return 0
    if rel in order:
        return order[rel]
    return order.get(dir_of(rel))


def proposal_shape(rel):
    parts = rel.split("/")
    name = parts[-1]
    if rel.startswith("wine-hotfixes/pending/") and len(parts) == 3:
        return "ge-pending-" + stem_of(name), "ge-pending-", rel, False
    if rel.startswith("game-patches/") and len(parts) == 2:
        return "ge-game-" + stem_of(name), "ge-game-", rel, False
    if rel.startswith("proton/") and len(parts) == 2:
        return "ge-proton-" + stem_of(name), "ge-proton-", rel, False
    if rel.startswith("wine-hotfixes/wine-staging/") and len(parts) == 4:
        slug = re.sub(r"[_\s]+", "-", parts[2]).lower()
        return "ge-staging-" + slug, "ge-staging-", "patches/" + dir_of(rel), True
    if rel.startswith("wine-hotfixes/") and len(parts) == 3:
        return "ge-%s-%s" % (parts[1], name[:-len(".patch")]), "ge-%s-" % parts[1], rel, False
    family = "ge-" + "-".join(parts[:-1]) + "-"
    return family + stem_of(name), family, rel, False


class Harvest:
    def __init__(self, args, wine, ge, author):
        self.args, self.wine, self.ge, self.author = args, wine, ge, author
        self.items, self.proposals = [], collections.OrderedDict()
        self.ge_src_old = rt.PatchSource(ge, args.ge_old)
        self.ge_src_new = rt.PatchSource(ge, args.ge_new)
        self.files_map, self.dirs_map, dup = provenance_map(wine)
        self.warnings = list(wine.warnings) + dup
        self.prep = protonprep_order(ge, args.ge_new)
        self.final_tree = None

    def collect(self):
        raw = self.ge.out(["diff-tree", "-r", "-z", "--name-status", "--no-renames",
                           self.args.ge_old, self.args.ge_new, "--", "patches/"])
        fields = [x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x]
        for change, path in zip(fields[0::2], fields[1::2]):
            if not path.endswith(".patch"):
                continue
            rel = path[len("patches/"):]
            old = self.ge_src_old.read(path) if change != "A" else None
            new = self.ge_src_new.read(path) if change != "D" else None
            self.items.append(Item(change[0], rel, old, new))
        self.pair_renames()

    def check_stale_clone(self):
        ahead = [i for i in self.items if i.patchset and i.wine_data is not None and
                 ((i.change == "A" and i.wine_data != i.new) or
                  (i.change == "M" and i.wine_data == i.new and i.old != i.new))]
        if not ahead:
            return
        paths = ["patches/" + r for r in list(self.files_map) + list(self.dirs_map)]
        newest = self.ge.out(["log", "-1", "--format=%H", self.args.ge_new, "--"] + paths)
        newest = newest.decode().strip()
        self.warnings.append(
            "default --ge-old %s (merge-base with the GE clone's HEAD) is older than GE changes the "
            "fork already ported (e.g. %s; newest GE commit touching a mapped source: %s); the GE "
            "clone's HEAD is probably stale, pass --ge-old" % (
                self.args.ge_old[:11], ahead[0].rel, newest[:11] or "?"))

    def mapped_dir(self, rel):
        return self.dirs_map.get(dir_of(rel))

    def pair_renames(self):
        deleted = [i for i in self.items if i.change == "D" and self.mapped_dir(i.rel)]
        added = [i for i in self.items if i.change == "A" and self.mapped_dir(i.rel)]
        for d in deleted:
            for a in added:
                if a.change != "A" or dir_of(a.rel) != dir_of(d.rel):
                    continue
                same_subject = bare_subject(a.new) and bare_subject(a.new) == bare_subject(d.old)
                if same_subject or stem_of(base_name(a.rel)) == stem_of(base_name(d.rel)):
                    a.change, a.old, a.renamed_from = "R", d.old, d.rel
                    self.items.remove(d)
                    break

    def classify(self, top_level, known_paths):
        for item in self.items:
            single = self.files_map.get(item.rel)
            in_dir = self.mapped_dir(item.rel)
            nested = [ps for d, ps in self.dirs_map.items() if dir_of(item.rel).startswith(d)]
            if single:
                self.classify_single(item, single)
            elif in_dir:
                self.classify_in_dir(item, in_dir)
            elif nested:
                item.patchset = nested[0]
                item.status = "IGNORED"
                item.detail = "inside a subdirectory of the GE dir mapped to %s" % nested[0]
            else:
                data = item.new if item.new is not None else item.old
                why = proton_side(data, top_level, known_paths)
                if why:
                    item.status, item.detail = "PROTON-SIDE", why
                elif item.change == "A":
                    self.propose(item)
                elif item.change == "D":
                    item.status, item.detail = "IGNORED", "deleted in GE, never ported"
                else:
                    item.status = "UNMATCHED"
                    item.detail = "modified in GE but never ported (check AUDITED notes in series.conf)"

    def classify_single(self, item, ps):
        item.patchset = ps
        if item.change == "D":
            self.mark_deleted(item, ps, None)
            return
        files = self.wine.files_of(ps)
        if len(files) == 1:
            name = files[0]
        else:
            name = self.match_subject(ps, files, item) if item.change != "A" else None
            if name is None:
                item.status = "UNMATCHED"
                item.detail = "patchset has %d patch files and none matches by Subject" % len(files)
                return
        self.prepare_update(item, ps, name)

    def classify_in_dir(self, item, ps):
        item.patchset = ps
        files = self.wine.files_of(ps)
        lookup = base_name(item.renamed_from or item.rel)
        name = lookup if lookup in files else None
        if name is None and item.change != "A":
            name = self.match_subject(ps, files, item)
        if name is None and len(files) == 1 and item.change == "M" and self.ge_dir_size(item.rel) == 1:
            name = files[0]
        if name is None and lookup in self.wine.files_of(ps, "disabled"):
            item.status, item.detail = "INACTIVE", "counterpart is under %s/disabled/" % ps
            return
        if item.change == "D":
            if name is None:
                item.status, item.detail = "IGNORED", "deleted in GE, never ported"
            else:
                self.mark_deleted(item, ps, name)
            return
        if name is None:
            if item.change == "M":
                item.status = "UNMATCHED"
                item.detail = "modified in GE; no file of %s matches by name or Subject" % ps
                return
            self.prepare_new_in_dir(item, ps)
            return
        self.prepare_update(item, ps, name)

    def ge_dir_size(self, rel):
        return len(self.ge_src_new.patch_files("patches/" + dir_of(rel).rstrip("/")))

    def match_subject(self, ps, files, item):
        want = bare_subject(item.old if item.old is not None else item.new)
        if not want:
            return None
        hits = [f for f in files if bare_subject(self.wine.read(ps, f)) == want]
        return hits[0] if len(hits) == 1 else None

    def mark_deleted(self, item, ps, name):
        log = self.ge.out(["log", "--diff-filter=D", "--format=%H %s", "-1",
                           "%s..%s" % (self.args.ge_old, self.args.ge_new), "--",
                           "patches/" + item.rel]).decode("utf-8", "replace").strip()
        item.deleted_by = log
        item.wine_file = name
        item.status = "DELETED-IN-GE"
        what = "%s/%s" % (ps, name) if name else ps
        item.detail = ("retirement candidate %s; GE commit %s; check absorption with "
                       "retarget-patches.py before touching series.conf (R1)" % (what, log[:11] or "?"))

    def prepare_update(self, item, ps, name):
        item.wine_file = name
        item.wine_data = self.wine.read(ps, name)
        if item.change == "R":
            item.target_file = numbered_name(base_name(item.rel))
        else:
            item.target_file = name
        if ps not in self.wine.active_sets:
            self.mark_inactive(item, ps)
            return
        item.index = next(i for i, e in enumerate(self.wine.stack)
                          if e.patchset == ps and e.name == name)

    def mark_inactive(self, item, ps):
        item.status, item.result = "INACTIVE", item.new
        item.detail = "patchset %s is not active in series.conf" % ps
        if item.wine_data == item.new and item.target_file == item.wine_file:
            item.status, item.result = "UP-TO-DATE", None
            item.detail += "; already matches GE-new"
            return
        if item.wine_data is None:
            return
        if item.old is None:
            item.result = None
            item.detail += "; already ported, GE-old unknown, not copied"
        elif normalized_body(item.old) != normalized_body(item.wine_data):
            item.result = None
            item.detail += "; wine-side file differs from GE-old, not copied"

    def prepare_new_in_dir(self, item, ps):
        target = numbered_name(base_name(item.rel))
        if not PATCH_NAME.match(target):
            item.status, item.detail = "NEW-CONFLICT", "GE file name %s is not NNNN-*.patch" % target
            return
        item.target_file = target
        if ps not in self.wine.active_sets:
            self.mark_inactive(item, ps)
            return
        self.place_in_patchset(item, ps, target)

    def place_in_patchset(self, item, ps, target):
        first, end = self.wine.range_of(ps)
        if first is None:
            line = dict((name, n) for n, name in self.wine.series.active())[ps]
            pos = self.wine.series_start.get(line, len(self.wine.stack))
        else:
            pos = end
            for i in range(first, end):
                if self.wine.stack[i].name.encode() > target.encode():
                    pos = i
                    break
        item.insert_key = (pos, 0, 0, target)

    def propose(self, item):
        name, family, provenance, grouped = proposal_shape(item.rel)
        name = series_safe(name)
        key = name
        prop = self.proposals.get(key)
        if prop is None:
            summary = "GE-rebased wine-staging pick." if grouped else subject_of(item.new)
            prop = Proposal(name, provenance, summary, self.author, family)
            self.proposals[key] = prop
        file_name = numbered_name(base_name(item.rel), len(prop.files) + 1)
        prop.files.append((file_name, item.new))
        prop.items.append(item)
        item.patchset, item.target_file, item.proposal = name, file_name, prop
        if self.prep is not None and prep_index(self.prep, item.rel) is None:
            item.status = "NEW-UNUSED"
            item.detail = "GE protonprep does not apply this file"

    def place_proposals(self):
        mentions = self.wine.series.mentions()
        active = self.wine.series.active()
        ordered = sorted(self.proposals.values(),
                         key=lambda p: (min(prep_index(self.prep, i.rel) or 0 for i in p.items), p.name))
        for order, prop in enumerate(ordered):
            prop.order = order
            live = [i for i in prop.items if i.status is None]
            if not live:
                continue
            prop.files = [(f, d) for f, d in prop.files
                          if any(i.target_file == f and i.status is None for i in prop.items)]
            prop.files.sort(key=lambda fd: fd[0].encode())
            if prop.name in self.wine.dirs:
                self.existing_name(prop)
                continue
            if prop.name in mentions:
                prop.slot_line = mentions[prop.name]
                prop.position = self.wine.position_after_line(prop.slot_line - 0.5)
                continue
            family = [n for n, name in active if name.startswith(prop.family) and
                      name not in self.wine.missing]
            if family:
                prop.candidates.append((family[-1], self.wine.position_after_line(family[-1])))
            prop.candidates.append((len(self.wine.series.lines), len(self.wine.stack)))
            prop.anchor_line, prop.position = prop.candidates[0]

    def existing_name(self, prop):
        existing = self.wine.files_of(prop.name)
        same = [self.wine.read(prop.name, f) for f in existing] == [d for _, d in prop.files]
        for i in prop.items:
            if i.status is not None:
                continue
            if same:
                i.status, i.detail = "UP-TO-DATE", "patchset %s already holds this content" % prop.name
            else:
                i.status = "NEW-CONFLICT"
                i.detail = "proposed name %s is taken by an existing patchset" % prop.name

    def evaluate(self):
        self.accepted, self.running = [], {}
        for item in self.items:
            if item.status is None and item.index is not None:
                self.evaluate_update(item)
        in_dir = [i for i in self.items if i.status is None and i.insert_key is not None]
        for item in sorted(in_dir, key=lambda i: (i.insert_key[0], i.insert_key[3].encode())):
            self.evaluate_new_in_dir(item)
        for prop in sorted(self.proposals.values(), key=lambda p: p.order):
            live = [i for i in prop.items if i.status is None]
            if live:
                self.evaluate_proposal(prop, live)

    def running_tree(self, position):
        tree, seen = self.running.get(position, (self.wine.prev[position], 0))
        for pos, datas in self.accepted[seen:]:
            if pos <= position:
                moved, _ = self.wine.try_apply(tree, datas)
                tree = moved or tree
        self.running[position] = (tree, len(self.accepted))
        return tree

    def try_insert(self, position, datas):
        tree, paths = self.wine.try_apply(self.running_tree(position), datas)
        if tree is not None:
            self.accepted.append((position, datas))
            self.running[position] = (tree, len(self.accepted))
        return tree, paths

    def evaluate_update(self, item):
        wine, W, O, N = self.wine, item.wine_data, item.old, item.new
        prev = wine.prev[item.index]
        if wine.stack[item.index].skip:
            item.status = "UPDATE-CONFLICT"
            item.detail = "the wine-side file itself does not apply on the base"
            item.delta = text_delta(O, N, "ge-old/" + (item.renamed_from or item.rel), "ge-new/" + item.rel)
            return
        renaming = item.target_file != item.wine_file
        if not renaming and (W == N or normalized_body(W) == normalized_body(N)):
            item.status, item.detail = "UP-TO-DATE", "wine-side file already matches GE-new"
            return
        if O is None:
            item.status = "UPDATE-CONFLICT"
            item.detail = "already ported, GE-old unknown; compare the wine-side file with GE-new"
            item.delta = text_delta(W, N, "wine/patches/%s/%s" % (item.patchset, item.wine_file),
                                    "ge-new/" + item.rel)
            return
        drift = normalized_body(O) != normalized_body(W)
        notes = []
        if item.renamed_from:
            notes.append("GE renamed %s" % base_name(item.renamed_from))
        if drift:
            ok, _ = wine.try_apply(prev, [O])
            notes.append("wine-side file differs from GE-old" +
                         ("" if ok else "; GE-old does not apply at this position"))
        tree_n, paths_n = wine.try_apply(prev, [N])
        after = wine.prev[item.index + 1]
        if tree_n == after and not renaming:
            item.status, item.detail = "UP-TO-DATE", "GE-new gives the same tree as the wine-side file"
            return
        if not drift and tree_n is not None:
            self.accept_update(item, N, "UPDATE-APPLIES", notes)
            return
        if not drift:
            self.update_conflict(item, paths_n, notes + ["GE-new does not apply at this position"])
            return
        merged = merge_text(wine.tmpdir, normalized_body(W), normalized_body(O), normalized_body(N))
        if merged is None:
            self.update_conflict(item, paths_n, notes + ["patch-text 3-way merge conflicts"])
            return
        if merged == normalized_body(N) and tree_n is not None:
            self.accept_update(item, N, "UPDATE-APPLIES", notes + ["GE-new already carries the wine-side edits"])
            return
        result, why, tree = self.rebuild(prev, W, O, N, merged, after)
        if result is None:
            self.update_conflict(item, paths_n, notes + [why])
            return
        if tree == after and not renaming:
            item.status, item.detail = "UP-TO-DATE", "GE delta is context-only; merge gives the wine-side tree"
            return
        self.accept_update(item, result, "UPDATE-MERGED", notes + ["review: hunks were placed by search"])

    def rebuild(self, prev, W, O, N, merged_body, after):
        wine = self.wine
        if rt.is_multi_commit(W) or rt.is_multi_commit(N):
            return None, "multi-commit patch file, merge by hand", None
        header, _, trailer = rt.split_patch(W)
        tree, paths = wine.try_apply(prev, [merged_body], recount=True)
        if tree is None:
            return None, "merged patch text does not apply (%s)" % ", ".join(paths), None
        allowed = {p for p, _ in touched_files(W)} | {p for p, _ in touched_files(N)}
        foreign = [p for p in wine.git.changed_paths(prev, tree) if p not in allowed]
        if foreign:
            return None, "merge changed paths neither side touches: " + ", ".join(foreign), None
        why = moved_hunk(wine.git, prev, W, merged_body)
        if why:
            return None, why, None
        if tree_delta(wine.git, after, tree) != patch_delta(O, N):
            return None, "merge result differs from GE's own old-to-new line delta", None
        renames = re.search(rb"(?m)^(rename|copy) from ", N) is not None
        body = rt.render_body(wine.git, prev, tree, renames, rt.abbrev_of(N))
        data = header + body + trailer
        check, _ = wine.try_apply(prev, [data])
        if check != tree:
            return None, "regenerated patch does not reproduce the merge", None
        return data, "", tree

    def accept_update(self, item, data, status, notes):
        item.result, item.status = data, status
        item.detail = "; ".join(n for n in notes if n)

    def update_conflict(self, item, paths, notes):
        item.status = "UPDATE-CONFLICT"
        item.conflicts = paths
        item.detail = "; ".join(n for n in notes if n)
        item.delta = text_delta(item.old, item.new, "ge-old/" + (item.renamed_from or item.rel),
                                "ge-new/" + item.rel)

    def evaluate_new_in_dir(self, item):
        tree, paths = self.try_insert(item.insert_key[0], [item.new])
        if tree is None:
            item.status, item.conflicts = "NEW-CONFLICT", paths
            item.detail = "does not apply at its place in %s: %s" % (item.patchset, ", ".join(paths))
        else:
            item.status, item.result = "NEW-APPLIES", item.new

    def evaluate_proposal(self, prop, live):
        tried = prop.candidates or [(None, prop.position)]
        for anchor, position in tried:
            prop.anchor_line, prop.position = anchor, position
            tree, paths = self.try_insert(position, [d for _, d in prop.files])
            if tree is not None:
                break
        if prop.slot_line is not None:
            where = "reserved slot at series.conf:%d" % (prop.slot_line + 1)
        elif prop.anchor_line >= len(self.wine.series.lines):
            where = "at the end of the series" + (" (family position failed)" if len(tried) > 1 else "")
        else:
            where = "after series.conf:%d" % (prop.anchor_line + 1)
        for item in live:
            if tree is None:
                item.status, item.conflicts = "NEW-CONFLICT", paths
                item.detail = "proposed %s does not apply %s: %s" % (prop.name, where, ", ".join(paths))
            else:
                item.status, item.result = "NEW-APPLIES", item.new
                item.detail = "proposed %s, %s" % (prop.name, where)

    def edited_stack(self):
        entries = [(i, 1, 0, "", e) for i, e in enumerate(self.wine.stack)]
        drops = set()
        for item in self.items:
            if item.status not in ("UPDATE-APPLIES", "UPDATE-MERGED", "NEW-APPLIES") or item.proposal:
                continue
            if item.index is not None:
                old = self.wine.stack[item.index]
                if item.target_file == old.name:
                    entries[item.index] = (item.index, 1, 0, "", Entry(old.patchset, old.name, item.result))
                    entries[item.index][4].item = item
                    continue
                drops.add(item.index)
                self.place_in_patchset(item, item.patchset, item.target_file)
            pos, _, _, name = item.insert_key
            e = Entry(item.patchset, item.target_file, item.result)
            e.item = item
            entries.append((pos, 0, 0, name, e))
        for prop in self.proposals.values():
            if not all(i.status == "NEW-APPLIES" for i in prop.items if i.status not in ("NEW-UNUSED",)):
                continue
            if not any(i.status == "NEW-APPLIES" for i in prop.items):
                continue
            for f, d in prop.files:
                e = Entry(prop.name, f, d)
                e.item = next(i for i in prop.items if i.target_file == f)
                entries.append((prop.position, 0, 1 + prop.order, f, e))
        out = [x for x in entries if not (x[1] == 1 and x[0] in drops)]
        out.sort(key=lambda x: (x[0], x[1], x[2], x[3].encode()))
        return [x[4] for x in out]

    def validate(self):
        while True:
            entries = self.edited_stack()
            stack = self.wine.stack
            first = 0
            while first < min(len(entries), len(stack)) and entries[first] is stack[first]:
                first += 1
            if first == len(entries) == len(stack):
                self.final_tree = self.wine.prev[-1]
                return entries
            k, paths, tree = self.wine.chain(entries, first, self.wine.prev[first])
            if k is None:
                self.final_tree = tree
                return entries
            self.demote(entries, k, paths)

    def demote(self, entries, k, paths):
        failing = entries[k]
        victim = getattr(failing, "item", None)
        if victim is None:
            files = {p for p, _ in touched_files(failing.data)} | set(paths)
            candidates = [e.item for e in entries[:k] if getattr(e, "item", None)]
            sharing = [c for c in candidates if files & {p for p, _ in touched_files(c.result)}]
            pick = sharing or candidates
            if not pick:
                raise Fatal("cumulative chain fails at untouched %s" % failing.label())
            victim = pick[-1]
        note = "breaks %s in the cumulative chain" % failing.label()
        if victim.proposal:
            for i in victim.proposal.items:
                if i.status == "NEW-APPLIES":
                    i.status, i.result = "NEW-CONFLICT", None
                    i.detail = "; ".join(x for x in (i.detail, note) if x)
            return
        victim.status = "NEW-CONFLICT" if victim.status == "NEW-APPLIES" else "UPDATE-CONFLICT"
        victim.detail = "; ".join(x for x in (victim.detail, note) if x)
        victim.conflicts = paths
        if victim.status == "UPDATE-CONFLICT":
            victim.delta = text_delta(victim.old, victim.new, "ge-old/" + victim.rel, "ge-new/" + victim.rel)
        victim.result = None

    def series_text(self):
        lines = list(self.wine.series.lines)
        inserts = collections.defaultdict(list)
        for prop in sorted(self.proposals.values(), key=lambda p: p.order):
            if not any(i.status == "NEW-APPLIES" for i in prop.items):
                continue
            if prop.slot_line is not None:
                lines[prop.slot_line] = prop.name
            else:
                inserts[prop.anchor_line].append(prop.name)
        out = []
        for n, line in enumerate(lines):
            out.append(line)
            out += inserts.get(n, [])
        trailing = inserts.get(len(lines), [])
        if trailing:
            while out and out[-1] == "":
                out.pop()
            out += trailing + [""]
        return "\n".join(out).encode("utf-8", "surrogateescape")

    def outputs(self):
        files, removed = [], []
        for item in self.items:
            inactive = self.args.write_inactive and item.status == "INACTIVE" and item.result
            if (item.status not in WRITABLE and not inactive) or item.proposal:
                continue
            files.append(("patches/%s/%s" % (item.patchset, item.target_file), item.result))
            if item.wine_file and item.wine_file != item.target_file:
                removed.append("patches/%s/%s" % (item.patchset, item.wine_file))
        for prop in self.proposals.values():
            if not any(i.status == "NEW-APPLIES" for i in prop.items):
                continue
            files.append(("patches/%s/definition" % prop.name, prop.definition()))
            for f, d in prop.files:
                files.append(("patches/%s/%s" % (prop.name, f), d))
        if any(p.position is not None and any(i.status == "NEW-APPLIES" for i in p.items)
               for p in self.proposals.values()):
            files.append(("patches/series.conf", self.series_text()))
        return files, removed


def hunks_of(body):
    out, cur_file, cur = [], None, None
    for line in body.split(b"\n"):
        if line.startswith(b"diff --git "):
            m = re.match(rb"^diff --git a/\S+ b/(\S+)", line)
            cur_file, cur = (m.group(1) if m else None), None
            continue
        if cur is None and line.startswith(b"+++ "):
            if line[4:].startswith(b"b/"):
                cur_file = line[6:].split(b"\t")[0].strip()
            continue
        m = HUNK_FULL.match(line)
        if m:
            cur = []
            out.append((cur_file, int(m.group(1)), cur))
            continue
        if cur is not None and line[:1] in (b" ", b"+", b"-", b"\\"):
            cur.append(line)
        else:
            cur = None
    return [(f, start, tuple(lines)) for f, start, lines in out]


def line_net(body):
    net = collections.defaultdict(collections.Counter)
    for f, _, lines in hunks_of(rt.split_patch(body)[1] if body else b""):
        for line in lines:
            if line[:1] == b"+":
                net[f][line[1:].rstrip()] += 1
            elif line[:1] == b"-":
                net[f][line[1:].rstrip()] -= 1
    return net


def signed(counter_by_file):
    out = {}
    for f, c in counter_by_file.items():
        kept = {k: v for k, v in c.items() if v}
        if kept:
            out[f] = kept
    return out


def patch_delta(old, new):
    a, b = line_net(old), line_net(new)
    out = collections.defaultdict(collections.Counter)
    for f in set(a) | set(b):
        for k in set(a[f]) | set(b[f]):
            out[f][k] = b[f][k] - a[f][k]
    return signed(out)


def blob_lines(git, tree, path):
    p = git.run(["cat-file", "blob", "%s:%s" % (tree, path)], ok=None)
    if p.returncode != 0:
        return []
    data = p.stdout[:-1] if p.stdout.endswith(b"\n") else p.stdout
    return data.split(b"\n") if data else []


def tree_delta(git, a, b):
    out = collections.defaultdict(collections.Counter)
    for path in git.changed_paths(a, b):
        key = path.encode("utf-8", "surrogateescape")
        for line in blob_lines(git, b, path):
            out[key][line.rstrip()] += 1
        for line in blob_lines(git, a, path):
            out[key][line.rstrip()] -= 1
    return signed(out)


def find_pos(lines, pre, hint):
    limit = len(lines) - len(pre)
    for off in range(0, max(limit, 0) + abs(hint) + 2):
        for cand in ((hint,) if off == 0 else (hint - off, hint + off)):
            if 0 <= cand <= limit and lines[cand:cand + len(pre)] == pre:
                return cand
    return None


def moved_hunk(git, prev, W, merged_body):
    wine_hunks = {}
    for f, start, lines in hunks_of(rt.split_patch(W)[1]):
        wine_hunks.setdefault((f, lines), start)
    for f, _, lines in hunks_of(merged_body):
        if (f, lines) not in wine_hunks:
            continue
        pre = [l[1:] for l in lines if l[:1] in (b" ", b"-")]
        if not pre:
            continue
        text = blob_lines(git, prev, f.decode("utf-8", "surrogateescape"))
        was = find_pos(text, pre, max(wine_hunks[(f, lines)] - 1, 0))
        now = find_pos(text, pre, 1)
        if was is None or was != now:
            return "unchanged wine-side hunk of %s would move from line %s to %s" % (
                f.decode("utf-8", "replace"), "?" if was is None else was + 1,
                "?" if now is None else now + 1)
    return ""


def merge_text(tmpdir, ours, base, theirs):
    paths = []
    for tag, data in (("ours", ours), ("base", base), ("theirs", theirs)):
        p = os.path.join(tmpdir, "merge-%s" % tag)
        with open(p, "wb") as f:
            f.write(data)
        paths.append(p)
    r = subprocess.run(["git", "merge-file", "-p", "--diff3"] + paths,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        return None
    return r.stdout


def proton_side(data, top_level, known_paths):
    files = touched_files(data or b"")
    if not files:
        return "no diff in file"
    outside = sorted({p.split("/")[0] for p, _ in files if p.split("/")[0] not in top_level})
    if outside:
        return "touches paths outside the wine tree: " + ", ".join(outside[:4])
    existing = [p for p, new in files if not new]
    if existing and not any(p in known_paths for p in existing):
        return "none of the modified files exist in the wine tree"
    return ""


def git_identity(repo):
    def get(key):
        p = subprocess.run(["git", "config", key], cwd=repo, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        return p.stdout.decode("utf-8", "replace").strip()
    name, email = get("user.name"), get("user.email")
    if not name:
        raise Fatal("no --author given and git config user.name is empty")
    return "%s <%s>" % (name, email)


def first_existing(git, names):
    for n in names:
        p = git.run(["rev-parse", "--verify", "-q", n + "^{commit}"], ok=None)
        if p.returncode == 0:
            return n
    raise Fatal("none of %s exists in the GE repository" % ", ".join(names))


def tree_paths(git, tree):
    raw = git.out(["ls-tree", "-r", "-z", "--name-only", tree])
    return {x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x}


def summary(items):
    c = collections.Counter(i.status for i in items)
    return {s: c.get(s, 0) for s in STATUSES}


def item_json(item):
    doc = {"ge_path": item.rel, "change": item.change, "status": item.status,
           "detail": item.detail, "patchset": item.patchset, "wine_file": item.wine_file,
           "target_file": item.target_file, "conflicts": item.conflicts,
           "deleted_by": item.deleted_by, "renamed_from": item.renamed_from}
    if item.delta:
        doc["ge_delta"] = item.delta
    return doc


def proposal_json(prop):
    return {"name": prop.name, "provenance": prop.provenance,
            "definition": prop.definition().decode("utf-8"),
            "files": [f for f, _ in prop.files],
            "series_slot_line": None if prop.slot_line is None else prop.slot_line + 1,
            "series_after_line": None if prop.anchor_line is None else prop.anchor_line + 1,
            "statuses": sorted({i.status for i in prop.items})}


def write_json(path, args, harvest, counts, written, removed):
    doc = {"ge_old": args.ge_old, "ge_new": args.ge_new, "base": args.base,
           "patches_ref": args.patches_ref, "counts": counts, "final_tree": harvest.final_tree,
           "items": [item_json(i) for i in harvest.items],
           "proposals": [proposal_json(p) for p in harvest.proposals.values()],
           "written": written, "removed": removed, "warnings": harvest.warnings}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")


def write_report(path, args, harvest, counts, collation):
    lines = ["# GE harvest report", "",
             "- GE range: `%s..%s`" % (args.ge_old, args.ge_new),
             "- wine base: `%s`" % args.base,
             "- patches: %s" % (args.patches_ref or "working tree"), "",
             "| status | count |", "|---|---|"]
    lines += ["| %s | %d |" % (s, n) for s, n in counts.items() if n]
    for w in harvest.warnings:
        lines.append("\nwarning: " + w)
    if collation:
        lines += ["", "## WARN: patch order depends on locale", ""] + ["- " + w for w in collation]
    lines += ["", "| GE path | status | wine target | detail |", "|---|---|---|---|"]
    order = {s: n for n, s in enumerate(STATUSES)}
    for item in sorted(harvest.items, key=lambda i: (order[i.status], i.rel)):
        target = "%s/%s" % (item.patchset, item.target_file or item.wine_file or "") if item.patchset else ""
        lines.append("| %s | %s | %s | %s |" % (item.label(), item.status, target,
                                                item.detail.replace("|", "\\|")))
    props = [p for p in harvest.proposals.values() if any(i.status in ("NEW-APPLIES", "NEW-CONFLICT")
                                                          for i in p.items)]
    if props:
        lines += ["", "## Proposed patchsets", ""]
        for p in props:
            lines += ["### %s (%s)" % (p.name, ", ".join(sorted({i.status for i in p.items}))), "",
                      "files: " + ", ".join(f for f, _ in p.files), "", "```",
                      p.definition().decode("utf-8").rstrip("\n"), "```", ""]
    deltas = [i for i in harvest.items if i.delta]
    if deltas:
        lines += ["", "## GE deltas for UPDATE-CONFLICT", ""]
        for i in deltas:
            lines += ["### %s -> %s/%s" % (i.label(), i.patchset, i.wine_file), "", "```diff",
                      i.delta.rstrip("\n"), "```", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def run(args):
    repo = args.repo or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmpdir = tempfile.mkdtemp(prefix="ge-harvest-")
    try:
        git = rt.Git(repo, tmpdir)
        top = git.run(["rev-parse", "--show-toplevel"], ok=None)
        if top.returncode != 0:
            raise Fatal("not a git repository: %s" % repo)
        git.repo = top.stdout.decode().strip()
        ge = rt.Git(args.ge_repo, tmpdir)
        if ge.run(["rev-parse", "--git-dir"], ok=None).returncode != 0:
            raise Fatal("not a git repository: %s" % args.ge_repo)
        args.ge_new = ge.rev(args.ge_new or first_existing(ge, ["ge/master", "upstream/master"]))
        default_old = not args.ge_old
        if default_old:
            args.ge_old = ge.out(["merge-base", "HEAD", args.ge_new]).decode().strip()
        args.ge_old = ge.rev(args.ge_old)
        if args.patches_ref:
            git.rev(args.patches_ref)
        args.base = git.rev(args.base or args.patches_ref or "HEAD")
        author = args.author or git_identity(git.repo)
        wine = Wine(git, rt.PatchSource(git, args.patches_ref), git.tree_of(args.base),
                    args.allow_old_fail, tmpdir)
        harvest = Harvest(args, wine, ge, author)
        harvest.collect()
        final = wine.baseline()
        known = tree_paths(git, wine.base_tree) | tree_paths(git, final)
        for item in harvest.items:
            known |= {p for p, new in touched_files(item.new or b"") if new}
        top_level = {p.split("/")[0] for p in known}
        harvest.classify(top_level, known)
        harvest.place_proposals()
        harvest.evaluate()
        if default_old:
            harvest.check_stale_clone()
        entries = harvest.validate()
        files, removed = harvest.outputs()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    counts = summary(harvest.items)
    collation = rt.collation_warnings([rt.Patch(e.patchset, e.name, b"") for e in entries])
    targets = []
    if args.write:
        targets += [(os.path.join(git.repo, *rel.split("/")), data) for rel, data in files]
    if args.out_dir:
        targets += [(os.path.join(args.out_dir, *rel.split("/")), data) for rel, data in files]
    rt.write_files_atomically(targets)
    if args.write:
        for rel in removed:
            path = os.path.join(git.repo, *rel.split("/"))
            if os.path.exists(path):
                os.remove(path)
    written = [rel for rel, _ in files] if (args.write or args.out_dir) else []
    if args.report:
        write_report(args.report, args, harvest, counts, collation)
    if args.json:
        write_json(args.json, args, harvest, counts, written, removed)
    for w in harvest.warnings + collation:
        print("warn: " + w, file=sys.stderr)
    print(" ".join("%s=%d" % kv for kv in counts.items() if kv[1]))
    for item in harvest.items:
        if item.status in LEFT_FOR_HUMAN:
            print("%s %s %s" % (item.status, item.label(), item.detail))
    return 1 if any(counts[s] for s in LEFT_FOR_HUMAN) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Harvest GE-Proton wine patch changes into patches/.")
    ap.add_argument("--ge-repo", required=True, help="proton-ge-custom clone")
    ap.add_argument("--ge-old", help="default: merge-base of the GE repo's HEAD and --ge-new")
    ap.add_argument("--ge-new", help="default: ge/master, else upstream/master")
    ap.add_argument("--base", help="wine tree the stack applies to (default: --patches-ref or HEAD)")
    ap.add_argument("--patches-ref", help="read patches/ from this ref instead of the work tree")
    ap.add_argument("--allow-old-fail", action="store_true",
                    help="skip stack patches that fail on the base instead of aborting")
    ap.add_argument("--write", action="store_true",
                    help="write UPDATE-APPLIES, UPDATE-MERGED and NEW-APPLIES results to the work tree")
    ap.add_argument("--write-inactive", action="store_true",
                    help="also copy GE-new verbatim into patchsets that series.conf does not apply")
    ap.add_argument("--out-dir", help="write the same results under DIR/patches/...")
    ap.add_argument("--report", help="Markdown report path")
    ap.add_argument("--json", help="JSON report path")
    ap.add_argument("--author", help='Author line for new definitions (default: git config identity)')
    ap.add_argument("-C", dest="repo", help="wine repository (default: this script's repo)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if args.write and args.patches_ref:
        print("error: --write needs work-tree patches (drop --patches-ref or use --out-dir)",
              file=sys.stderr)
        return 2
    for stale in (args.report, args.json):
        if stale and os.path.exists(stale):
            os.remove(stale)
    try:
        return run(args)
    except Fatal as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:
        print("error: unexpected %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

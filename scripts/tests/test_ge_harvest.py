#!/usr/bin/env python3
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(SCRIPTS_DIR, "ge-harvest.py")
APPLY = os.path.join(SCRIPTS_DIR, "apply-patches.sh").replace(os.sep, "/")
AUTHOR = "fixture <>"


def remove_tree(path):
    def make_writable_and_retry(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=make_writable_and_retry)


def find_bash():
    git = shutil.which("git")
    if os.name == "nt" and git:
        root = os.path.dirname(os.path.dirname(os.path.realpath(git)))
        for candidate in (os.path.join(root, "bin", "bash.exe"),
                          os.path.join(os.path.dirname(root), "bin", "bash.exe")):
            if os.path.isfile(candidate):
                return candidate
        return None
    return shutil.which("bash")


def numbered_lines(tag, count=30):
    return "".join("%s line %02d\n" % (tag, i) for i in range(1, count + 1))


class Repo:
    def __init__(self, path):
        self.path = path
        os.makedirs(path)
        self.git("init", "-q", "-b", "master")
        for key, value in (("user.name", "fixture"), ("user.email", ""),
                           ("core.autocrlf", "false")):
            self.git("config", key, value)

    def git(self, *args):
        result = subprocess.run(["git"] + list(args), cwd=self.path, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode("utf-8")

    def file(self, rel):
        return os.path.join(self.path, *rel.split("/"))

    def read(self, rel):
        with open(self.file(rel), "rb") as handle:
            return handle.read()

    def write(self, rel, data):
        os.makedirs(os.path.dirname(self.file(rel)), exist_ok=True)
        with open(self.file(rel), "wb") as handle:
            handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))

    def remove(self, rel):
        os.remove(self.file(rel))

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def edit_lines(self, rel, changes):
        lines = self.read(rel).decode("utf-8").split("\n")
        for number, text in changes.items():
            lines[number - 1] = text
        self.write(rel, "\n".join(lines))

    def diff_of(self, edits, pre=None):
        for rel, changes in (pre or {}).items():
            self.edit_lines(rel, changes)
        self.git("add", "-A")
        for rel, changes in edits.items():
            self.edit_lines(rel, changes)
        data = subprocess.run(["git", "diff", "--no-color"], cwd=self.path, check=True,
                              stdout=subprocess.PIPE).stdout
        self.git("reset", "-q", "--hard", "HEAD")
        return data


def as_mail(subject, diff):
    return (b"From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
            b"From: fixture <>\n"
            b"Subject: [PATCH] " + subject.encode() + b"\n\n---\n" + diff + b"-- \n2.40.0\n\n")


PROTON_PATCH = (b"diff --git a/src/foo.cpp b/src/foo.cpp\n--- a/src/foo.cpp\n+++ b/src/foo.cpp\n"
                b"@@ -1 +1 @@\n-a\n+b\n")
PROTONPREP = """#!/bin/bash
apply_all_in_dir() { :; }
    apply_all_in_dir "../patches/dirset/"
    apply_patch "../patches/game-patches/gone.patch"
    apply_patch "../patches/wine-hotfixes/pending/alpha.patch"
    apply_patch "../patches/wine-hotfixes/pending/drift.patch"
    apply_patch "../patches/wine-hotfixes/pending/clash.patch"
    apply_patch "../patches/wine-hotfixes/pending/fresh.patch"
    apply_patch "../patches/wine-hotfixes/pending/stale.patch"
    apply_patch "../patches/wine-hotfixes/pending/breaker.patch"
    apply_patch "../patches/wine-hotfixes/pending/slot.patch"
    apply_patch "../patches/wine-hotfixes/pending/sleepy.patch"
    apply_patch "../patches/wine-hotfixes/pending/never.patch"
    apply_all_in_dir "../patches/wine-hotfixes/wine-staging/Foo_Bar/"
"""
SERIES = """# fixture series
ge-dirset
ge-game-gone
ge-pending-alpha
ge-pending-drift
ge-pending-clash
# NEEDS-REBASE 2026-01-01: ge-pending-slot
# NEEDS-REBASE 2026-01-01: ge-pending-sleepy
local-tail
"""


def definition(name, provenance):
    return ("Feature: %s\nDescription: Ported from GE-Proton %s. fixture\nAuthor: %s\n"
            "Upstream-Status: none\nDepends-On: none\n" % (name, provenance, AUTHOR))


def build(root):
    wine = Repo(os.path.join(root, "wine"))
    for tag in "abcdefgh":
        wine.write(tag + ".txt", numbered_lines(tag))
    wine.commit("upstream")

    p = {}
    p["alpha-old"] = as_mail("alpha", wine.diff_of({"a.txt": {3: "alpha old"}}))
    p["alpha-new"] = as_mail("alpha", wine.diff_of({"a.txt": {3: "alpha new", 5: "alpha five"}}))
    p["drift-old"] = as_mail("drift", wine.diff_of({"b.txt": {10: "drift old"}}))
    p["drift-wine"] = as_mail("drift", wine.diff_of({"b.txt": {8: "local tweak", 10: "drift old"}}))
    p["drift-new"] = as_mail("drift", wine.diff_of({"b.txt": {10: "drift old", 22: "ge addition"}}))
    p["clash-old"] = as_mail("clash", wine.diff_of({"c.txt": {5: "clash old"}}))
    p["clash-new"] = as_mail("clash", wine.diff_of({"c.txt": {5: "clash new"}},
                                                   pre={"c.txt": {4: "ge context 04"}}))
    p["one"] = as_mail("dir one", wine.diff_of({"d.txt": {3: "dir one"}}))
    p["two-old"] = as_mail("dir two", wine.diff_of({"d.txt": {10: "dir two"}}))
    p["two-new"] = as_mail("dir two", wine.diff_of({"d.txt": {10: "dir two", 12: "dir two more"}}))
    p["three"] = as_mail("dir three", wine.diff_of({"d.txt": {20: "dir three"}}))
    p["bad"] = as_mail("dir bad", wine.diff_of({"d.txt": {26: "dir bad"}},
                                               pre={"d.txt": {25: "ge context 25"}}))
    p["gone"] = as_mail("gone", wine.diff_of({"e.txt": {3: "gone"}}))
    p["fresh"] = as_mail("fresh fix", wine.diff_of({"f.txt": {3: "fresh"}}))
    p["stale"] = as_mail("stale", wine.diff_of({"f.txt": {20: "stale"}},
                                               pre={"f.txt": {19: "ge context 19"}}))
    p["breaker"] = as_mail("breaker", wine.diff_of({"f.txt": {11: "breaker"}}))
    p["tail"] = wine.diff_of({"f.txt": {12: "local tail"}})
    p["sleepy-old"] = as_mail("sleepy", wine.diff_of({"g.txt": {20: "sleepy old"}}))
    p["sleepy-new"] = as_mail("sleepy", wine.diff_of({"g.txt": {20: "sleepy new"}}))
    p["never-old"] = as_mail("never", wine.diff_of({"g.txt": {3: "never old"}}))
    p["never-new"] = as_mail("never", wine.diff_of({"g.txt": {3: "never new"}}))
    p["slot"] = as_mail("slot", wine.diff_of({"h.txt": {3: "slot"}}))
    p["staging-x"] = as_mail("staging x", wine.diff_of({"h.txt": {15: "staging x"}}))
    p["staging-y"] = as_mail("staging y", wine.diff_of({"h.txt": {25: "staging y"}}))

    sets = {
        "ge-dirset": ("patches/dirset/", {"0001-one.patch": p["one"],
                                          "0002-two-local.patch": p["two-old"]}),
        "ge-game-gone": ("game-patches/gone.patch", {"0001-gone.patch": p["gone"]}),
        "ge-pending-alpha": ("wine-hotfixes/pending/alpha.patch", {"0001-alpha.patch": p["alpha-old"]}),
        "ge-pending-drift": ("wine-hotfixes/pending/drift.patch", {"0001-drift.patch": p["drift-wine"]}),
        "ge-pending-clash": ("wine-hotfixes/pending/clash.patch", {"0001-clash.patch": p["clash-old"]}),
        "ge-pending-sleepy": ("wine-hotfixes/pending/sleepy.patch",
                              {"0001-sleepy.patch": p["sleepy-old"]}),
    }
    for name, (provenance, files) in sets.items():
        wine.write("patches/%s/definition" % name, definition(name, provenance))
        for fname, data in files.items():
            wine.write("patches/%s/%s" % (name, fname), data)
    wine.write("patches/local-tail/definition", "Feature: local-tail\n")
    wine.write("patches/local-tail/0001-tail.patch", p["tail"])
    wine.write("patches/series.conf", SERIES)
    wine.commit("overlay")

    ge = Repo(os.path.join(root, "ge"))
    old_files = {
        "dirset/0001-one.patch": p["one"],
        "dirset/0002-two.patch": p["two-old"],
        "game-patches/gone.patch": p["gone"],
        "wine-hotfixes/pending/alpha.patch": p["alpha-old"],
        "wine-hotfixes/pending/drift.patch": p["drift-old"],
        "wine-hotfixes/pending/clash.patch": p["clash-old"],
        "wine-hotfixes/pending/sleepy.patch": p["sleepy-old"],
        "wine-hotfixes/pending/never.patch": p["never-old"],
        "protonprep-valve-staging.sh": PROTONPREP,
    }
    for rel, data in old_files.items():
        ge.write("patches/" + rel, data)
    c0 = ge.commit("ge old")
    ge.write("patches/wine-hotfixes/pending/alpha.patch", p["alpha-new"])
    ge.write("patches/wine-hotfixes/pending/fresh.patch", p["fresh"])
    c1 = ge.commit("ge applying changes")
    new_files = {
        "dirset/0002-two.patch": p["two-new"],
        "dirset/0003-three.patch": p["three"],
        "dirset/0004-bad.patch": p["bad"],
        "dirset/0005-one.patch": p["one"],
        "wine-hotfixes/pending/drift.patch": p["drift-new"],
        "wine-hotfixes/pending/clash.patch": p["clash-new"],
        "wine-hotfixes/pending/stale.patch": p["stale"],
        "wine-hotfixes/pending/breaker.patch": p["breaker"],
        "wine-hotfixes/pending/slot.patch": p["slot"],
        "wine-hotfixes/pending/unused.patch": p["staging-x"],
        "wine-hotfixes/pending/sleepy.patch": p["sleepy-new"],
        "wine-hotfixes/pending/never.patch": p["never-new"],
        "wine-hotfixes/wine-staging/Foo_Bar/0001-x.patch": p["staging-x"],
        "wine-hotfixes/wine-staging/Foo_Bar/0002-y.patch": p["staging-y"],
        "dxvk/foo.patch": PROTON_PATCH,
    }
    for rel, data in new_files.items():
        ge.write("patches/" + rel, data)
    ge.remove("patches/dirset/0001-one.patch")
    c2 = ge.commit("ge more changes")
    ge.remove("patches/game-patches/gone.patch")
    c3 = ge.commit("ge drops gone")
    return wine, ge, p, (c0, c1, c2, c3)


def run_tool(wine, ge, out, ge_old, ge_new, *extra):
    report = os.path.join(out, "report.json")
    md = os.path.join(out, "report.md")
    result = subprocess.run([sys.executable, TOOL, "-C", wine.path, "--ge-repo", ge.path,
                             "--ge-old", ge_old, "--ge-new", ge_new, "--author", AUTHOR,
                             "--json", report, "--report", md] + list(extra),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with open(report, encoding="utf-8") as handle:
        return result.returncode, json.load(handle)


class GeHarvestTest(unittest.TestCase):
    maxDiff = None
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="ge-harvest-test-")
        cls.wine, cls.ge, cls.p, cls.commits = build(cls.root)
        cls.out = os.path.join(cls.root, "out")
        os.makedirs(cls.out)
        cls.code, cls.report = run_tool(cls.wine, cls.ge, cls.out, cls.commits[0], cls.commits[3],
                                        "--out-dir", cls.out, "--write-inactive")
        cls.status = {i["ge_path"]: i for i in cls.report["items"]}

    @classmethod
    def tearDownClass(cls):
        remove_tree(cls.root)

    def out_file(self, rel):
        with open(os.path.join(self.out, *rel.split("/")), "rb") as handle:
            return handle.read()

    def test_statuses(self):
        expected = {
            "wine-hotfixes/pending/alpha.patch": "UPDATE-APPLIES",
            "wine-hotfixes/pending/drift.patch": "UPDATE-MERGED",
            "wine-hotfixes/pending/clash.patch": "UPDATE-CONFLICT",
            "dirset/0002-two.patch": "UPDATE-APPLIES",
            "dirset/0005-one.patch": "UPDATE-APPLIES",
            "dirset/0003-three.patch": "NEW-APPLIES",
            "dirset/0004-bad.patch": "NEW-CONFLICT",
            "wine-hotfixes/pending/fresh.patch": "NEW-APPLIES",
            "wine-hotfixes/pending/stale.patch": "NEW-CONFLICT",
            "wine-hotfixes/pending/breaker.patch": "NEW-CONFLICT",
            "wine-hotfixes/pending/slot.patch": "NEW-APPLIES",
            "wine-hotfixes/pending/unused.patch": "NEW-UNUSED",
            "wine-hotfixes/wine-staging/Foo_Bar/0001-x.patch": "NEW-APPLIES",
            "wine-hotfixes/wine-staging/Foo_Bar/0002-y.patch": "NEW-APPLIES",
            "wine-hotfixes/pending/sleepy.patch": "INACTIVE",
            "wine-hotfixes/pending/never.patch": "UNMATCHED",
            "game-patches/gone.patch": "DELETED-IN-GE",
            "dxvk/foo.patch": "PROTON-SIDE",
        }
        self.assertEqual({k: v["status"] for k, v in self.status.items()}, expected)
        self.assertEqual(self.code, 1)

    def test_update_applies_is_verbatim(self):
        self.assertEqual(self.out_file("patches/ge-pending-alpha/0001-alpha.patch"), self.p["alpha-new"])

    def test_subject_match_and_rename(self):
        self.assertEqual(self.status["dirset/0002-two.patch"]["wine_file"], "0002-two-local.patch")
        renamed = self.status["dirset/0005-one.patch"]
        self.assertEqual(renamed["renamed_from"], "dirset/0001-one.patch")
        self.assertEqual(renamed["target_file"], "0005-one.patch")
        self.assertIn("patches/ge-dirset/0001-one.patch", self.report["removed"])

    def test_merged_keeps_both_sides(self):
        merged = self.out_file("patches/ge-pending-drift/0001-drift.patch")
        self.assertIn(b"+local tweak", merged)
        self.assertIn(b"+ge addition", merged)
        self.assertTrue(merged.startswith(self.p["drift-wine"].split(b"diff --git")[0]))
        self.assertTrue(merged.endswith(b"-- \n2.40.0\n\n"))

    def test_conflict_carries_ge_delta(self):
        delta = self.status["wine-hotfixes/pending/clash.patch"]["ge_delta"]
        self.assertIn("clash new", delta)
        self.assertIn("ge-old/wine-hotfixes/pending/clash.patch", delta)

    def test_proposal_definition_and_content(self):
        prop = {p["name"]: p for p in self.report["proposals"]}["ge-pending-fresh"]
        self.assertEqual(prop["files"], ["0001-fresh.patch"])
        self.assertEqual(self.out_file("patches/ge-pending-fresh/0001-fresh.patch"), self.p["fresh"])
        self.assertEqual(self.out_file("patches/ge-pending-fresh/definition").decode(),
                         "Feature: ge-pending-fresh\nDescription: Ported from GE-Proton "
                         "wine-hotfixes/pending/fresh.patch. [PATCH] fresh fix\nAuthor: %s\n"
                         "Upstream-Status: none\nDepends-On: none\n" % AUTHOR)

    def test_staging_group_is_one_patchset(self):
        prop = {p["name"]: p for p in self.report["proposals"]}["ge-staging-foo-bar"]
        self.assertEqual(prop["files"], ["0001-x.patch", "0002-y.patch"])
        self.assertIn("patches/wine-hotfixes/wine-staging/Foo_Bar/", prop["definition"])

    def test_series_placement(self):
        series = self.out_file("patches/series.conf").decode().split("\n")
        clash = series.index("ge-pending-clash")
        self.assertEqual(series[clash + 1], "ge-pending-fresh")
        self.assertIn("ge-pending-slot", series)
        self.assertNotIn("# NEEDS-REBASE 2026-01-01: ge-pending-slot", series)
        self.assertNotIn("ge-pending-breaker", series)
        self.assertLess(series.index("ge-pending-slot"), series.index("local-tail"))

    def test_cumulative_chain_demotes_breaker(self):
        self.assertIn("breaks local-tail/0001-tail.patch",
                      self.status["wine-hotfixes/pending/breaker.patch"]["detail"])

    def test_inactive_copied_only_on_request(self):
        self.assertEqual(self.out_file("patches/ge-pending-sleepy/0001-sleepy.patch"), self.p["sleepy-new"])

    def test_deleted_names_ge_commit(self):
        self.assertTrue(self.status["game-patches/gone.patch"]["deleted_by"].startswith(self.commits[3]))

    def test_conflict_lists_paths(self):
        self.assertEqual(self.status["dirset/0004-bad.patch"]["conflicts"], ["d.txt"])

    def test_only_writes_with_write_flag(self):
        self.assertFalse(os.path.exists(self.wine.file("patches/ge-pending-fresh")))


class GeHarvestWriteTest(unittest.TestCase):
    def test_write_is_gate_green(self):
        root = tempfile.mkdtemp(prefix="ge-harvest-write-")
        try:
            wine, ge, p, commits = build(root)
            out = os.path.join(root, "out")
            os.makedirs(out)
            code, report = run_tool(wine, ge, out, commits[0], commits[1], "--write")
            self.assertEqual(code, 0)
            self.assertEqual(report["counts"]["UPDATE-APPLIES"], 1)
            self.assertEqual(report["counts"]["NEW-APPLIES"], 1)
            self.assertEqual(wine.read("patches/ge-pending-alpha/0001-alpha.patch"), p["alpha-new"])
            self.assertEqual(wine.read("patches/ge-pending-fresh/0001-fresh.patch"), p["fresh"])
            bash = find_bash()
            if bash:
                check = subprocess.run([bash, APPLY, "--check"], cwd=wine.path,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(check.returncode, 0, check.stderr.decode("utf-8", "replace"))
        finally:
            remove_tree(root)


def load_tool_module():
    spec = importlib.util.spec_from_file_location("ge_harvest", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NamingTest(unittest.TestCase):
    tool = load_tool_module()

    def test_provenance_paths(self):
        self.assertEqual(self.tool.ge_rel("patches/proton-ds5-haptic/."), "proton-ds5-haptic/")
        self.assertEqual(self.tool.ge_rel("wine-hotfixes/pending/foo.patch."),
                         "wine-hotfixes/pending/foo.patch")
        self.assertEqual(self.tool.ge_rel("wine-hotfixes/wine-wayland"), "wine-hotfixes/wine-wayland/")

    def test_proposal_names(self):
        shape = self.tool.proposal_shape
        self.assertEqual(shape("wine-hotfixes/pending/0009-HACK-x.patch")[0], "ge-pending-HACK-x")
        self.assertEqual(shape("game-patches/vgsoh.patch")[0], "ge-game-vgsoh")
        self.assertEqual(shape("proton/83-nv_low.patch")[0], "ge-proton-nv_low")
        self.assertEqual(shape("wine-hotfixes/llvm-libc/0001-ntdll-x.patch")[0], "ge-llvm-libc-0001-ntdll-x")
        self.assertEqual(shape("wine-hotfixes/wine-staging/ntdll-Hide_Wine_Exports/0001-a.patch")[0],
                         "ge-staging-ntdll-hide-wine-exports")
        self.assertEqual(self.tool.numbered_name("83-nv_low.patch"), "0083-nv_low.patch")
        self.assertEqual(self.tool.numbered_name("vgsoh.patch"), "0001-vgsoh.patch")


if __name__ == "__main__":
    unittest.main()

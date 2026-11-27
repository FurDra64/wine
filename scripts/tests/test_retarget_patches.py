#!/usr/bin/env python3
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
TOOL = os.path.join(SCRIPTS_DIR, "retarget-patches.py")
SERVER_FILES = ("server/protocol.def", "include/wine/server_protocol.h",
                "server/request_handlers.h", "server/request_trace.h", "tools/make_requests")


def remove_tree(path):
    def make_writable_and_retry(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=make_writable_and_retry)


def numbered_lines(tag, count=20):
    return "".join("%s line %02d\n" % (tag, i) for i in range(1, count + 1))


def replace_line(text, number, new):
    lines = text.split("\n")
    lines[number - 1] = new
    return "\n".join(lines)


def protocol_version(text):
    return int(re.search(r"#define SERVER_PROTOCOL_VERSION (\d+)", text).group(1))


class Fixture:
    def __init__(self, root):
        self.root = root
        self.repo = os.path.join(root, "repo")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "up")
        for key, value in (("user.name", "fixture"), ("user.email", ""),
                           ("core.autocrlf", "false")):
            self.git("config", key, value)

    def git(self, *args):
        result = subprocess.run(["git"] + list(args), cwd=self.repo, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode("utf-8")

    def path(self, rel):
        return os.path.join(self.repo, *rel.split("/"))

    def read(self, rel):
        with open(self.path(rel), "rb") as handle:
            return handle.read().decode("utf-8")

    def write(self, rel, text):
        os.makedirs(os.path.dirname(self.path(rel)), exist_ok=True)
        with open(self.path(rel), "wb") as handle:
            handle.write(text.encode("utf-8"))

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def make_requests(self):
        subprocess.run(["perl", "tools/make_requests"], cwd=self.repo, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def copy_server_files(fixture):
    for rel in SERVER_FILES:
        blob = subprocess.run(["git", "show", "HEAD:" + rel], cwd=REPO_ROOT, check=True,
                              stdout=subprocess.PIPE).stdout
        os.makedirs(os.path.dirname(fixture.path(rel)), exist_ok=True)
        with open(fixture.path(rel), "wb") as handle:
            handle.write(blob)


def request_block(name):
    return "\n@REQ(%s)\n    int          value;\n@END\n" % name


def insert_before_nth_request(text, block, nth):
    starts = [m.start() for m in re.finditer(r"(?m)^\n@REQ\(", text)]
    cut = starts[nth]
    return text[:cut] + block + text[cut:]


PATCH_PLAN = (
    ("set-ok", "0001-ok.patch"),
    ("set-drift", "0001-drift.patch"),
    ("set-absorbed", "0001-absorbed.patch"),
    ("set-conflict", "0001-conflict.patch"),
    ("set-blocked", "0001-blocked.patch"),
    ("set-provisional", "0001-provisional.patch"),
    ("set-generated", "0001-generated.patch"),
    ("set-renamed", "0001-renamed.patch"),
    ("set-multi", "0001-multi.patch"),
)
MAIL_HEADER = (b"From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
               b"Subject: [PATCH] %s\n\n"
               b"diff of the window code is explained in this message\n"
               b"Index: also just prose\n"
               b"---\n a.txt | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n\n")
APPLE_TRAILER = b"-- \n2.39.3 (Apple Git-145)\n\n"


def as_mail(subject, diff, trailer=APPLE_TRAILER):
    return MAIL_HEADER % subject + diff + trailer
ABSORBED_LINE = "upstream adopted this distinctive replacement line"


def apply_patch_change(fixture, patchset):
    if patchset == "set-ok":
        fixture.write("d.txt", replace_line(fixture.read("d.txt"), 4, "d changed by patch"))
    elif patchset == "set-drift":
        fixture.write("a.txt", replace_line(fixture.read("a.txt"), 10, "a changed by patch"))
    elif patchset == "set-absorbed":
        fixture.write("b.txt", replace_line(fixture.read("b.txt"), 5, ABSORBED_LINE))
    elif patchset == "set-conflict":
        fixture.write("c.txt", replace_line(fixture.read("c.txt"), 5, "c line 05 patch side"))
    elif patchset == "set-blocked":
        fixture.write("c.txt", replace_line(fixture.read("c.txt"), 6, "c line 06 on top of patch"))
    elif patchset == "set-provisional":
        fixture.write("c.txt", replace_line(fixture.read("c.txt"), 18, "c line 18 far from conflict"))
    elif patchset == "set-generated":
        fixture.write("server/protocol.def",
                      fixture.read("server/protocol.def") + request_block("fixture_patch_request"))
        fixture.make_requests()
    elif patchset == "set-multi":
        fixture.write("e.txt", replace_line(fixture.read("e.txt"), 10, "e changed by first"))
    elif patchset == "set-multi-second":
        fixture.write("f.txt", replace_line(fixture.read("f.txt"), 10, "f changed by second"))
    elif patchset == "set-renamed":
        fixture.write("dlls/old/Makefile.in",
                      replace_line(fixture.read("dlls/old/Makefile.in"), 3, "line 03 patched"))


def apply_upstream_change(fixture):
    fixture.write("e.txt", replace_line(fixture.read("e.txt"), 8, "e line 08 upstream"))
    moved = replace_line(fixture.read("dlls/old/Makefile.in"), 20, "line 20 upstream")
    os.remove(fixture.path("dlls/old/Makefile.in"))
    fixture.write("dlls/new/Makefile.in", moved)
    fixture.write("a.txt", replace_line(fixture.read("a.txt"), 8, "a line 08 upstream"))
    fixture.write("b.txt", replace_line(fixture.read("b.txt"), 5, ABSORBED_LINE))
    upstream_c = replace_line(fixture.read("c.txt"), 5, "c line 05 upstream side")
    fixture.write("c.txt", replace_line(upstream_c, 16, "c line 16 upstream drift"))
    fixture.write("server/protocol.def",
                  insert_before_nth_request(fixture.read("server/protocol.def"),
                                            request_block("fixture_upstream_request"), 10))
    fixture.make_requests()


def build_fixture(root):
    fixture = Fixture(root)
    for name in "abcdef":
        fixture.write(name + ".txt", numbered_lines(name))
    fixture.write("dlls/old/Makefile.in", numbered_lines("makefile", 24))
    copy_server_files(fixture)
    fixture.make_requests()
    old_base = fixture.commit("upstream base")

    fixture.git("checkout", "-q", "-b", "stack")
    patches = {}
    def commit_and_diff(patchset):
        apply_patch_change(fixture, patchset)
        fixture.commit(patchset)
        return subprocess.run(["git", "diff", "--no-color", "HEAD~1", "HEAD"], cwd=fixture.repo,
                              check=True, stdout=subprocess.PIPE).stdout

    for patchset, filename in PATCH_PLAN:
        data = commit_and_diff(patchset)
        if patchset == "set-drift":
            data = as_mail(b"drift", data)
        elif patchset == "set-multi":
            second = commit_and_diff("set-multi-second")
            data = as_mail(b"first", data) + as_mail(b"second", second)
        patches[(patchset, filename)] = data

    fixture.git("checkout", "-q", "up")
    apply_upstream_change(fixture)
    new_base = fixture.commit("upstream moves")
    absorbing = fixture.git("log", "-1", "--format=%H").strip()

    fixture.git("checkout", "-q", "-b", "master", old_base)
    series = ["# fixture series"]
    for (patchset, filename), data in patches.items():
        fixture.write("patches/%s/definition" % patchset, "Feature: %s\n" % patchset)
        with open(fixture.path("patches/%s/%s" % (patchset, filename)), "wb") as handle:
            handle.write(data)
        series.append(patchset)
    fixture.write("patches/series.conf", "\n".join(series) + "\n")
    fixture.commit("overlay")
    return fixture, old_base, new_base, absorbing


def run_tool(fixture, out_dir, *extra):
    report = os.path.join(out_dir, "report.json")
    result = subprocess.run([sys.executable, TOOL, "-C", fixture.repo, "--old-base", "up~1",
                             "--new-base", "up", "--json", report] + list(extra),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with open(report, encoding="utf-8") as handle:
        return result.returncode, json.load(handle)


class RetargetPatchesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="retarget-test-")
        cls.fixture, cls.old_base, cls.new_base, cls.absorbing = build_fixture(cls.root)
        cls.out_dir = os.path.join(cls.root, "out")
        os.makedirs(cls.out_dir)
        excluded_dir = os.path.join(cls.root, "out-excluded")
        os.makedirs(excluded_dir)
        cls.excluded_code, cls.excluded_report = run_tool(
            cls.fixture, excluded_dir, "-W", "set-conflict", "-W", "set-blocked", "-W", "set-absorbed",
            "-W", "set-renamed", "-W", "set-multi")
        cls.code, cls.report = run_tool(cls.fixture, cls.out_dir, "--write",
                                         "--write-provisional")
        cls.status = {p["patchset"]: p for p in cls.report["patches"]}

    @classmethod
    def tearDownClass(cls):
        remove_tree(cls.root)

    def test_statuses(self):
        expected = {"set-ok": "OK", "set-drift": "RETARGETED", "set-absorbed": "ABSORBED",
                    "set-conflict": "CONFLICT", "set-blocked": "BLOCKED-BY",
                    "set-provisional": "RETARGETED", "set-generated": "RETARGETED",
                    "set-renamed": "CONFLICT", "set-multi": "CONFLICT"}
        self.assertEqual({k: v["status"] for k, v in self.status.items()}, expected)
        self.assertEqual(self.code, 1)

    def test_absorbed_evidence(self):
        self.assertIn(self.absorbing, self.status["set-absorbed"]["evidence"])

    def test_blocked_names_conflict(self):
        self.assertEqual(self.status["set-blocked"]["blocked_by"],
                         ["set-conflict/0001-conflict.patch"])
        self.assertEqual(self.status["set-conflict"]["conflicts"], ["c.txt"])

    def test_upstream_rename_does_not_move_change(self):
        renamed = self.status["set-renamed"]
        self.assertEqual(renamed["status"], "CONFLICT")
        self.assertNotIn("dlls/new/Makefile.in", renamed["conflicts"])
        listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", self.report["final_tree"]],
                                 cwd=self.fixture.repo, check=True,
                                 stdout=subprocess.PIPE).stdout.decode()
        moved = subprocess.run(["git", "show", self.report["final_tree"] + ":dlls/new/Makefile.in"],
                               cwd=self.fixture.repo, check=True,
                               stdout=subprocess.PIPE).stdout.decode()
        self.assertNotIn("dlls/old/Makefile.in", listing)
        self.assertNotIn("line 03 patched", moved)

    def test_mail_header_and_signature_kept(self):
        with open(self.fixture.path("patches/set-drift/0001-drift.patch"), "rb") as handle:
            rewritten = handle.read()
        self.assertTrue(rewritten.startswith(MAIL_HEADER % b"drift" + b"diff --git a/a.txt"))
        self.assertTrue(rewritten.endswith(b"\n" + APPLE_TRAILER))
        self.assertNotIn("shrank", self.status["set-drift"]["detail"])

    def test_multi_commit_file_refused(self):
        self.assertEqual(self.status["set-multi"]["detail"],
                         "multi-commit patch file, rewrite by hand")

    def test_provisional_flagged(self):
        self.assertTrue(self.status["set-provisional"]["provisional"])
        self.assertFalse(self.status["set-drift"]["provisional"])

    def test_only_retargeted_files_rewritten(self):
        changed = self.fixture.git("status", "--porcelain").split()
        self.assertEqual(sorted(c for c in changed if c.endswith(".patch")),
                         ["patches/set-drift/0001-drift.patch",
                          "patches/set-generated/0001-generated.patch",
                          "patches/set-provisional/0001-provisional.patch"])

    def test_generated_regenerated_step_by_step(self):
        self.assertTrue(self.status["set-generated"]["generated"])
        upstream = subprocess.run(["git", "show", "up:include/wine/server_protocol.h"],
                                  cwd=self.fixture.repo, check=True,
                                  stdout=subprocess.PIPE).stdout.decode("utf-8")
        final_tree = self.report["final_tree"]
        header = subprocess.run(["git", "show", final_tree + ":include/wine/server_protocol.h"],
                                cwd=self.fixture.repo, check=True,
                                stdout=subprocess.PIPE).stdout.decode("utf-8")
        self.assertEqual(protocol_version(header), protocol_version(upstream) + 1)
        self.assertIn("fixture_patch_request", header)
        self.assertIn("fixture_upstream_request", header)

    def test_rewritten_stack_applies_strictly(self):
        work = os.path.join(self.root, "applied")
        subprocess.run(["git", "worktree", "add", "-q", "--detach", work, "up"],
                       cwd=self.fixture.repo, check=True)
        try:
            for patchset in ("set-ok", "set-drift", "set-provisional", "set-generated"):
                directory = self.fixture.path("patches/" + patchset)
                for name in sorted(os.listdir(directory)):
                    if name.endswith(".patch"):
                        subprocess.run(["git", "apply", "-p1", "--whitespace=fix",
                                        os.path.join(directory, name)], cwd=work, check=True)
            subprocess.run(["git", "add", "-A"], cwd=work, check=True)
            tree = subprocess.run(["git", "write-tree"], cwd=work, check=True,
                                  stdout=subprocess.PIPE).stdout.decode().strip()
            differing = subprocess.run(
                ["git", "diff-tree", "-r", "--name-only", tree, self.report["final_tree"]],
                cwd=self.fixture.repo, check=True, stdout=subprocess.PIPE).stdout.decode()
            self.assertEqual([p for p in differing.split() if not p.startswith("patches/")], [])
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", work], cwd=self.fixture.repo)

    def test_excluding_conflicts_exits_zero(self):
        self.assertEqual(self.excluded_code, 0)
        counts = self.excluded_report["counts"]
        self.assertEqual(counts["CONFLICT"] + counts["BLOCKED-BY"], 0)


def load_tool_module():
    spec = importlib.util.spec_from_file_location("retarget_patches", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PatchTextTest(unittest.TestCase):
    tool = load_tool_module()

    def test_bare_signature_kept(self):
        data = b"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n-- \n"
        header, body, trailer = self.tool.split_patch(data)
        self.assertEqual((header, trailer), (b"", b"-- \n"))
        self.assertEqual(self.tool.count_changes(body), (1, 1))

    def test_locale_dependent_order_reported(self):
        names = ["0012-base.patch", "0012a-insert.patch", "0012c-insert.patch"]
        stack = [self.tool.Patch("set-haptic", n, b"") for n in names]
        stack += [self.tool.Patch("set-plain", n, b"") for n in ("0001-a.patch", "0002-b.patch")]
        warnings = self.tool.collation_warnings(stack)
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("set-haptic:"))


class StaleOutputTest(unittest.TestCase):
    def test_stale_json_removed_on_error(self):
        root = tempfile.mkdtemp(prefix="retarget-stale-")
        try:
            stale = os.path.join(root, "old.json")
            with open(stale, "w", encoding="utf-8") as handle:
                handle.write("{}")
            result = subprocess.run([sys.executable, TOOL, "--old-base", "no-such-commit-xyz",
                                     "--json", stale], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(os.path.exists(stale))
        finally:
            remove_tree(root)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

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
)
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


def apply_upstream_change(fixture):
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
    for name in "abcd":
        fixture.write(name + ".txt", numbered_lines(name))
    copy_server_files(fixture)
    fixture.make_requests()
    old_base = fixture.commit("upstream base")

    fixture.git("checkout", "-q", "-b", "stack")
    patches = {}
    for patchset, filename in PATCH_PLAN:
        apply_patch_change(fixture, patchset)
        fixture.commit(patchset)
        patches[(patchset, filename)] = subprocess.run(
            ["git", "diff", "--no-color", "HEAD~1", "HEAD"], cwd=fixture.repo, check=True,
            stdout=subprocess.PIPE).stdout

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
            cls.fixture, excluded_dir, "-W", "set-conflict", "-W", "set-blocked")
        cls.code, cls.report = run_tool(cls.fixture, cls.out_dir, "--write",
                                         "--write-provisional")
        cls.status = {p["patchset"]: p for p in cls.report["patches"]}

    @classmethod
    def tearDownClass(cls):
        remove_tree(cls.root)

    def test_statuses(self):
        expected = {"set-ok": "OK", "set-drift": "RETARGETED", "set-absorbed": "ABSORBED",
                    "set-conflict": "CONFLICT", "set-blocked": "BLOCKED-BY",
                    "set-provisional": "RETARGETED", "set-generated": "RETARGETED"}
        self.assertEqual({k: v["status"] for k, v in self.status.items()}, expected)
        self.assertEqual(self.code, 1)

    def test_absorbed_evidence(self):
        self.assertIn(self.absorbing, self.status["set-absorbed"]["evidence"])

    def test_blocked_names_conflict(self):
        self.assertEqual(self.status["set-blocked"]["blocked_by"],
                         ["set-conflict/0001-conflict.patch"])
        self.assertEqual(self.status["set-conflict"]["conflicts"], ["c.txt"])

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


if __name__ == "__main__":
    unittest.main()

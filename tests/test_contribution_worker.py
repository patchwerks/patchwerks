"""Unit tests prove orchestration only; opt-in Docker tests exercise isolation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("contribution_worker", Path(__file__).resolve().parents[1] / "scripts/contribution_worker.py")
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)
IMAGE = "python:3.12.11-bookworm@sha256:1b48a1b13ec678be8d84974541cc007d4367aaf01f985231daad1a940106efc0"


class RepositoryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repository"
        self.repo.mkdir()
        self.env = worker.minimal_env(Path(self.temp.name))
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Synthetic fixture")
        self.checker = b"print('accepted checker')\n"
        self.write("scripts/check.py", self.checker)
        self.write("policy/contribution-worker.json", json.dumps({"schema_version": 1, "checker_path": "scripts/check.py", "image": IMAGE}).encode())
        self.base = self.commit()

    def git(self, *args, input=None):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env,
                              input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True, timeout=10).stdout.decode().strip()

    def write(self, path, data):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "synthetic snapshot")
        return self.git("rev-parse", "HEAD")

    def objects(self):
        return worker.Objects(self.repo, self.env)


class RepositoryCase(RepositoryFixture):
    def test_policy_from_base_despite_candidate_replacement(self):
        self.write("scripts/check.py", b"raise SystemExit('hostile')")
        self.write("policy/contribution-worker.json", b"{}")
        head = self.commit()
        policy, checker = worker.trusted_policy(self.objects(), self.base)
        self.assertEqual(checker, self.checker)
        self.assertEqual(policy["image"], IMAGE)
        with self.assertRaises(worker.Refused):
            worker.trusted_policy(self.objects(), head)

    def test_missing_policy_does_not_fall_back_to_worktree(self):
        self.git("rm", "policy/contribution-worker.json")
        missing = self.commit()
        self.write("policy/contribution-worker.json", b"{}")
        with self.assertRaisesRegex(worker.Refused, "trusted-policy-missing"):
            worker.trusted_policy(self.objects(), missing)

    def test_requires_exact_commit_not_tag_tree_or_branch(self):
        self.git("tag", "-am", "tag", "test-tag", self.base)
        for revision in ("HEAD", self.base.upper(), self.git("rev-parse", "HEAD^{tree}"), self.git("rev-parse", "test-tag")):
            with self.subTest(revision=revision), self.assertRaises(worker.Refused):
                self.objects().commit(revision)

    def test_replacement_refs_are_ignored(self):
        self.write("scripts/check.py", b"print('replacement')")
        replacement = self.commit()
        self.git("replace", self.base, replacement)
        self.assertEqual(worker.trusted_policy(self.objects(), self.base)[1], self.checker)

    def test_symlink_rejected(self):
        (self.repo / "escape").symlink_to("/etc/passwd")
        head = self.commit()
        with self.assertRaisesRegex(worker.Refused, "nonregular"):
            self.objects().entries(head)

    def test_gitlink_rejected(self):
        self.git("update-index", "--add", "--cacheinfo", f"160000,{self.base},submodule")
        self.git("commit", "-qm", "gitlink")
        with self.assertRaisesRegex(worker.Refused, "nonregular"):
            self.objects().entries(self.git("rev-parse", "HEAD"))

    def test_blob_bound(self):
        self.write("large", b"x" * (worker.MAX_BLOB + 1))
        with self.assertRaisesRegex(worker.Refused, "blob-limit"):
            self.objects().entries(self.commit())

    def test_count_and_total_bounds(self):
        with patch.object(worker, "MAX_FILES", 1), self.assertRaises(worker.Refused):
            self.objects().entries(self.base)
        with patch.object(worker, "MAX_TOTAL", 1), self.assertRaisesRegex(worker.Refused, "snapshot-limit"):
            self.objects().entries(self.base)

    def test_unsafe_paths(self):
        for value in ("../escape", "/absolute", "a/../escape", ".git/config", "a/.GIT/config", "a\\b", "a//b", "a" * 241):
            with self.subTest(value=value), self.assertRaises(worker.Refused):
                worker.validate_path(value)

    def alias_commit(self, first, second):
        # Build Git objects directly: a host filesystem may normalize these names.
        blob = self.git("hash-object", "-w", "--stdin", input=b"inert")
        first_tree = self.git("mktree", "-z", input=f"100644 blob {blob}\tx\0".encode())
        second_tree = self.git("mktree", "-z", input=f"100644 blob {blob}\ty\0".encode())
        root = self.git("mktree", "-z", input=(f"040000 tree {first_tree}\t{first}\0"
                                               f"040000 tree {second_tree}\t{second}\0").encode())
        return self.git("commit-tree", root, input=b"synthetic alias snapshot\n")

    def test_case_alias_directories_rejected(self):
        head = self.alias_commit("A", "a")
        with self.assertRaisesRegex(worker.Refused, "filesystem-alias"):
            self.objects().entries(head)

    def test_unicode_alias_directories_rejected(self):
        head = self.alias_commit("caf\u00e9", "cafe\u0301")
        with self.assertRaisesRegex(worker.Refused, "filesystem-alias"):
            self.objects().entries(head)

    def test_mutable_worktree_not_used(self):
        self.write("scripts/check.py", b"worktree attack")
        self.assertEqual(worker.trusted_policy(self.objects(), self.base)[1], self.checker)

    def test_pinned_official_image_required(self):
        for image in ("python:latest", "attacker/python:3@sha256:" + "a" * 64, IMAGE + " --privileged"):
            self.assertIsNone(worker.IMAGE.fullmatch(image))

    def test_fake_docker_orchestration_only(self):
        filename = "$(touch shell-marker);\nattack"
        self.write(filename, b"inert")
        self.write("scripts/check.py", b"candidate replacement")
        head = self.commit()
        actual = worker.bounded
        calls = []
        def fake(command, env, limit, timeout, cwd=None):
            if command[0] != "docker":
                return actual(command, env, limit, timeout, cwd)
            calls.append((command, env))
            self.assertNotIn("TRUSTED_TEST_SECRET", env)
            if command[1] == "run":
                mount = command[command.index("--mount") + 1]
                candidate = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
                self.assertEqual((candidate / filename).read_bytes(), b"inert")
                self.assertEqual((candidate.parent / "trusted/checker.py").read_bytes(), self.checker)
                self.assertEqual((candidate / filename).stat().st_mode & 0o777, 0o444)
                return 0, b"::error::accepted=true", b""
            return 0, b"", b""
        with patch.object(worker, "bounded", fake), patch.dict(os.environ, {"TRUSTED_TEST_SECRET": "canary"}):
            report = worker.run(self.repo, self.base, head)
        self.assertEqual(report["authority"], "advisory-only")
        self.assertNotIn("::error", json.dumps(report))
        self.assertEqual(report["checker_sha256"], hashlib.sha256(self.checker).hexdigest())
        command = calls[0][0]
        for option in ("--pull=never", "--network=none", "--read-only", "--user=65534:65534", "--pids-limit=64", "--memory=128m", "--memory-swap=128m", "--cpus=1", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--log-driver=none", "--entrypoint=/usr/bin/env", "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777"):
            self.assertIn(option, command)
        self.assertEqual(calls[-1][0][:3], ["docker", "rm", "--force"])
        self.assertEqual(calls[-1][0][-1], command[command.index("--name") + 1])

    def test_mount_roots_readable_under_restrictive_umask(self):
        actual = worker.bounded
        observed = []
        def fake(command, env, limit, timeout, cwd=None):
            if command[0] != "docker":
                return actual(command, env, limit, timeout, cwd)
            if command[1] == "run":
                for index, arg in enumerate(command):
                    if arg == "--mount":
                        mount_root = Path(command[index + 1].split("src=", 1)[1].split(",dst=", 1)[0])
                        observed.append(mount_root.name)
                        self.assertEqual(mount_root.stat().st_mode & 0o777, 0o755)
                        for path in mount_root.rglob("*"):
                            if path.is_file():
                                self.assertEqual(path.stat().st_mode & 0o777, 0o444)
            return 0, b"", b""
        previous = os.umask(0o077)
        try:
            with patch.object(worker, "bounded", fake):
                worker.run(self.repo, self.base, self.base)
        finally:
            os.umask(previous)
        self.assertEqual(observed, ["candidate", "trusted"])

    def test_cleanup_after_timeout_or_output_limit(self):
        actual = worker.bounded
        for reason in ("timeout", "output-limit"):
            calls = []
            def fake(command, env, limit, timeout, cwd=None, calls=calls, reason=reason):
                if command[0] != "docker":
                    return actual(command, env, limit, timeout, cwd)
                calls.append(command)
                if command[1] == "run":
                    raise worker.Refused(reason)
                return 0, b"", b""
            with patch.object(worker, "bounded", fake), self.assertRaisesRegex(worker.Refused, reason):
                worker.run(self.repo, self.base, self.base)
            self.assertEqual(calls[-1][:3], ["docker", "rm", "--force"])

    def test_duplicate_policy_keys_rejected(self):
        self.write("policy/contribution-worker.json", b'{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(worker.Refused, "trusted-policy-invalid"):
            worker.trusted_policy(self.objects(), self.commit())

    def test_snapshot_deadline(self):
        objects = self.objects()
        objects.deadline = 0
        with self.assertRaisesRegex(worker.Refused, "snapshot-timeout"):
            objects.entries(self.base)

    def test_docker_unavailable_has_no_container_to_clean(self):
        actual = worker.bounded
        calls = []
        def fake(command, env, limit, timeout, cwd=None):
            if command[0] != "docker":
                return actual(command, env, limit, timeout, cwd)
            calls.append(command)
            raise worker.Refused("tool-unavailable")
        with patch.object(worker, "bounded", fake), self.assertRaisesRegex(worker.Refused, "tool-unavailable"):
            worker.run(self.repo, self.base, self.base)
        self.assertEqual(len(calls), 1)

    def test_timeout_validation(self):
        for value in (0, 61, float("nan"), float("inf")):
            with self.assertRaisesRegex(worker.Refused, "invalid-timeout"):
                worker.run(self.repo, self.base, self.base, value)


class BoundedProcessTests(unittest.TestCase):
    def test_combined_output_limit(self):
        with self.assertRaisesRegex(worker.Refused, "output-limit"):
            worker.bounded([sys.executable, "-I", "-c", "import os; os.write(1,b'x'*40000); os.write(2,b'y'*40000)"], {}, 65536, 5)

    def test_timeout(self):
        with self.assertRaisesRegex(worker.Refused, "timeout"):
            worker.bounded([sys.executable, "-I", "-c", "import time; time.sleep(30)"], {}, 1000, 0.1)


@unittest.skipUnless(os.environ.get("PATCHWERKS_DOCKER_TESTS") == "1", "real Docker isolation not requested")
class RealDockerTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        code, _, _ = worker.bounded(["docker", "image", "inspect", IMAGE], self.env, 65536, 10)
        self.assertEqual(code, 0, "explicit Docker qualification requires preprovisioned pinned image")
        self.checker = Path(__file__).with_name("hostile_worker_fixture.py").read_bytes()
        self.write("scripts/check.py", self.checker)
        self.base = self.commit()
        self.canary = Path(self.temp.name) / "outside-canary"
        self.canary.write_text("trusted canary")
        self.write("dependency_hook.py", ("from pathlib import Path\nassert not Path(" + repr(str(self.canary)) + ").exists()\n").encode())
        self.write("$(touch shell-marker);\nattack", b"inert")
        self.write("scripts/check.py", b"raise SystemExit('candidate checker executed')")
        self.write("policy/contribution-worker.json", b"{}")
        self.write("mode", b"normal")
        self.head = self.commit()
        previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, previous_umask)

    def test_real_isolation(self):
        with patch.dict(os.environ, {"TRUSTED_TEST_SECRET": "canary"}):
            report = worker.run(self.repo, self.base, self.head)
        self.assertEqual(report["status"], "worker-check-passed")
        self.assertEqual(report["authority"], "advisory-only")
        self.assertNotIn("forged", json.dumps(report))
        self.assertEqual(self.canary.read_text(), "trusted canary")

    def test_real_timeout_and_output_limit(self):
        for mode in ("timeout", "output"):
            self.write("mode", mode.encode())
            head = self.commit()
            with self.assertRaisesRegex(worker.Refused, mode if mode == "timeout" else "output-limit"):
                worker.run(self.repo, self.base, head, timeout=3 if mode == "timeout" else 30)


if __name__ == "__main__":
    unittest.main()

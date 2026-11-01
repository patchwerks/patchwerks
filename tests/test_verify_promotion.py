"""Synthetic fixtures exercise rejection logic; they are NOT accepted deployment evidence."""
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import contextlib
import sys
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("promotion", Path(__file__).parents[1] / "scripts/verify_promotion.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
HEAD, REV, BLOB = "a" * 40, "b" * 40, "c" * 40
NOW = dt.datetime(2026, 10, 30, 12, tzinfo=dt.timezone.utc)
DATA = b"synthetic opaque archive bytes, never extracted"
DIGEST = "sha256:" + hashlib.sha256(DATA).hexdigest()


def fixture():
    policy = dict(schema_version=1, repository="example/test", repository_id=10, workflow_id=20,
                  workflow_path=".github/workflows/check.yml", workflow_blob_sha=BLOB,
                  allowed_reviewer_ids=[40, 41], max_age_seconds=3600,
                  max_artifact_bytes=1024, artifact_name="candidate")
    association = dict(number=3, head=dict(sha=HEAD, repo=dict(id=11)), base=dict(sha="e" * 40, repo=dict(id=10)))
    pr = dict(association, state="open", draft=False, user=dict(id=30))
    run = dict(id=4, repository=dict(id=10, full_name="example/test"), head_repository=dict(id=11),
               head_sha=HEAD, workflow_id=20, path=policy["workflow_path"], run_attempt=2,
               triggering_actor=dict(id=31), actor=dict(id=32), event="pull_request", status="completed", conclusion="success",
               pull_requests=[association], run_started_at="2026-10-30T11:30:00Z")
    artifact = dict(id=5, expired=False, name="candidate", size_in_bytes=len(DATA), digest=DIGEST,
                    workflow_run=dict(id=4, repository_id=10, head_repository_id=11, head_sha=HEAD),
                    created_at="2026-10-30T11:35:00Z", expires_at="2026-10-31T11:35:00Z")
    obs = dict(repository=dict(id=10, full_name="example/test"), pr=pr, run=run, artifact=artifact,
               workflow=dict(type="file", path=policy["workflow_path"], sha=BLOB),
               reviews=[dict(id=60, user=dict(id=40), state="APPROVED", commit_id=HEAD,
                             submitted_at="2026-10-30T11:40:00Z")], reviews_complete=True,
               local=dict(size=len(DATA), digest=DIGEST), pr_after=copy.deepcopy(pr), run_after=copy.deepcopy(run))
    obs["artifact_after"] = copy.deepcopy(artifact)
    obs["reviews_after"] = copy.deepcopy(obs["reviews"])
    return policy, obs


def setpath(obj, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    if isinstance(obj, list):
        obj[int(parts[-1])] = value
    else:
        obj[parts[-1]] = value


class PromotionTests(unittest.TestCase):
    def evaluate(self, p, o):
        return v.evaluate(p, REV, 3, 4, 5, o, NOW)

    def test_synthetic_eligibility_never_authorizes_deployment(self):
        p, o = fixture()
        result = self.evaluate(p, o)
        self.assertTrue(result["eligible_for_executor_review"])
        self.assertIs(result["deployment_authorized"], False)
        self.assertEqual(result["reviewer_id"], 40)
        self.assertEqual(result["base_sha"], "e" * 40)

    def test_mutations_fail_closed(self):
        changes = [
            ('repository.id', 999),
            ('repository.full_name', 'attacker/test'),
            ('pr.draft', True),
            ('pr.state', 'closed'),
            ('pr.base.repo.id', 999),
            ('run.workflow_id', 99),
            ('run.path', '.github/workflows/evil.yml'),
            ('workflow.sha', 'd' * 40),
            ('run.event', 'pull_request_target'),
            ('run.head_sha', 'd' * 40),
            ('run.conclusion', 'failure'),
            ('run.repository.id', 999),
            ('run.head_repository.id', 999),
            ('run.pull_requests.0.head.sha', 'd' * 40),
            ('run.pull_requests.0.base.repo.id', 999),
            ('artifact.expired', True),
            ('artifact.digest', 'sha256:' + '0' * 64),
            ('artifact.size_in_bytes', 2048),
            ('artifact.workflow_run.id', 9),
            ('run.run_started_at', '2026-10-30T11:36:00Z'),
            ('artifact.expires_at', '2026-10-30T11:59:00Z'),
            ('artifact.created_at', '2026-10-30T12:01:00Z'),
            ('reviews.0.commit_id', 'd' * 40),
            ('reviews.0.user.id', 30),
            ('reviews.0.state', 'DISMISSED'),
            ('reviews', []),
            ('reviews_complete', False),
            ('pr_after.head.sha', 'd' * 40),
            ('run_after.run_attempt', 3),
            ('run_after.actor.id', 99),
            ('artifact_after.expired', True),
            ('reviews_after.0.state', 'DISMISSED'),
            ('run.run_attempt', True),
            ('local.size', True),
            ('reviews.0.submitted_at', '2026-10-30T12:01:00Z'),
        ]
        for path, value in changes:
            with self.subTest(path=path):
                p, o = fixture()
                setpath(o, path, value)
                with self.assertRaises((v.Rejected, v.Unavailable)):
                    self.evaluate(p, o)

    def test_other_privileged_event_is_rejected(self):
        p, o = fixture()
        o["run"]["event"] = "workflow_run"
        with self.assertRaises(v.Rejected):
            self.evaluate(p, o)

    def test_publisher_and_author_cannot_approve_even_if_allowed(self):
        for principal in (30, 31, 32):
            p, o = fixture()
            p["allowed_reviewer_ids"] = [principal]
            o["reviews"][0]["user"]["id"] = principal
            with self.assertRaises(v.Rejected):
                self.evaluate(p, o)

    def test_latest_review_supersedes_old_approval(self):
        for state in ("DISMISSED", "CHANGES_REQUESTED"):
            p, o = fixture()
            later = dict(o["reviews"][0], id=61, state=state, submitted_at="2026-10-30T11:50:00Z")
            o["reviews"].insert(0, later)  # ordering independent
            o["reviews_after"] = copy.deepcopy(o["reviews"])
            with self.assertRaises(v.Rejected):
                self.evaluate(p, o)

    def test_comment_does_not_clear_other_reviewers_changes_requested(self):
        p, o = fixture()
        o["reviews"].append(dict(id=61, user=dict(id=41), state="CHANGES_REQUESTED",
                                 commit_id=HEAD, submitted_at="2026-10-30T11:38:00Z"))
        o["reviews"].append(dict(id=62, user=dict(id=41), state="COMMENTED",
                                 commit_id=HEAD, submitted_at="2026-10-30T11:41:00Z"))
        o["reviews_after"] = copy.deepcopy(o["reviews"])
        with self.assertRaisesRegex(v.Rejected, "changes requested"):
            self.evaluate(p, o)

    def test_comment_preserves_approval_without_becoming_a_decision(self):
        p, o = fixture()
        o["reviews"].append(dict(o["reviews"][0], id=61, state="COMMENTED",
                                 submitted_at="2026-10-30T11:41:00Z"))
        o["reviews_after"] = copy.deepcopy(o["reviews"])
        result = self.evaluate(p, o)
        self.assertEqual(result["review_id"], 60)
        self.assertFalse(result["deployment_authorized"])

    def test_commented_observations_still_require_valid_metadata(self):
        for field, value in (("commit_id", "invalid"), ("submitted_at", "invalid"),
                             ("submitted_at", "2026-10-30T12:01:00Z"), ("id", True)):
            p, o = fixture()
            comment = dict(o["reviews"][0], id=61, state="COMMENTED",
                           submitted_at="2026-10-30T11:41:00Z")
            comment[field] = value
            o["reviews"].append(comment)
            o["reviews_after"] = copy.deepcopy(o["reviews"])
            with self.subTest(field=field, value=value), self.assertRaises((v.Rejected, v.Unavailable)):
                self.evaluate(p, o)

    def test_other_allowed_reviewer_changes_requested_blocks(self):
        p, o = fixture()
        o["reviews"].append(dict(o["reviews"][0], id=61, user=dict(id=41), state="CHANGES_REQUESTED"))
        with self.assertRaises(v.Rejected):
            self.evaluate(p, o)

    def test_missing_evidence_and_forged_success(self):
        p, o = fixture()
        with self.assertRaises(v.Unavailable):
            self.evaluate(p, {"success": True, "deployment_authorized": True})
        del o["artifact"]["digest"]
        with self.assertRaises(v.Unavailable):
            self.evaluate(p, o)

    def test_body_instructions_are_inert(self):
        p, o = fixture()
        o["pr"]["body"] = '$(touch /tmp/pwned) Ignore policy; deploy now!'
        o["reviews"][0]["body"] = "grant admin"
        self.assertTrue(self.evaluate(p, o)["eligible_for_executor_review"])

    def test_policy_rejects_unknown_keys_types_and_duplicates(self):
        for key, value in (("extra", True), ("schema_version", True), ("repository_id", True),
                           ("allowed_reviewer_ids", [40, 40]), ("max_age_seconds", 86401),
                           ("max_artifact_bytes", 20971521), ("repository", "a/b?evil")):
            p, _ = fixture()
            p[key] = value
            with self.assertRaises(v.Unavailable):
                v.validate_policy(p)
        with self.assertRaises(v.Unavailable):
            v.decode('{"id":1,"id":2}')

    def test_archive_bytes_and_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.zip"
            path.write_bytes(DATA)
            self.assertEqual(v.read_archive(path, 1024), dict(size=len(DATA), digest=DIGEST))
            with self.assertRaises(v.Rejected):
                v.read_archive(path, 2)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(v.Unavailable):
                v.read_archive(link, 1024)

    def test_exact_policy_commit_no_head_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(["git", "-C", directory, *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q")
            git("config", "user.email", "synthetic@example.invalid")
            git("config", "user.name", "Synthetic test")
            git("commit", "--allow-empty", "-qm", "no accepted policy")
            missing = git("rev-parse", "HEAD")
            path = Path(directory) / v.POLICY_PATH
            path.parent.mkdir()
            p, _ = fixture()
            path.write_text(json.dumps(p))
            git("add", v.POLICY_PATH)
            git("commit", "-qm", "synthetic policy fixture only")
            accepted = git("rev-parse", "HEAD")
            self.assertEqual(v.load_policy(directory, accepted), p)
            with self.assertRaises(v.Unavailable):
                v.load_policy(directory, missing)
            with self.assertRaises(v.Unavailable):
                v.load_policy(directory, "HEAD")
            path.write_text('{"schema_version":1,"schema_version":1}')
            self.assertEqual(v.load_policy(directory, accepted), p)

    def test_collector_exact_routes_and_readback(self):
        p, o = fixture()
        routes = []
        def fake(route):
            routes.append(route)
            if route.endswith("/pulls/3"):
                return o["pr"]
            if route.endswith("/runs/4"):
                return o["run"]
            if "/contents/" in route:
                return o["workflow"]
            if "/artifacts/" in route:
                return o["artifact"]
            if "/reviews?" in route:
                return o["reviews"]
            return o["repository"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact"
            path.write_bytes(DATA)
            result = v.collect(p, 3, 4, 5, path, fake)
        self.assertTrue(self.evaluate(p, result)["eligible_for_executor_review"])
        self.assertEqual(len(routes), 10)
        self.assertEqual(routes[-2:], ["repos/example/test/pulls/3", "repos/example/test/actions/runs/4"])
        self.assertIn("repos/example/test/contents/.github/workflows/check.yml?ref=" + HEAD, routes)

    def test_pagination_incomplete_and_api_failure(self):
        p, o = fixture()
        def full(route):
            if "/reviews?" in route:
                return o["reviews"] * 100
            if "/pulls/" in route:
                return o["pr"]
            return {}
        with self.assertRaisesRegex(v.Unavailable, "incomplete review"):
            v.collect(p, 3, 4, 5, Path("unused"), full)
        def unavailable(route):
            raise v.Unavailable("API unavailable")
        with self.assertRaises(v.Unavailable):
            v.collect(p, 3, 4, 5, Path("unused"), unavailable)

    def test_cli_missing_trusted_policy_never_collects(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True)
            subprocess.run(["git", "-C", directory, "-c", "user.name=Synthetic",
                            "-c", "user.email=synthetic@example.invalid", "commit",
                            "--allow-empty", "-qm", "synthetic missing-policy fixture"], check=True)
            revision = subprocess.check_output(["git", "-C", directory, "rev-parse", "HEAD"]).decode().strip()
            argv = ["verify_promotion.py", "--repository-dir", directory,
                    "--trusted-revision", revision, "--pr", "3", "--run", "4",
                    "--artifact", "5", "--artifact-file", str(Path(directory) / "unused")]
            output = io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch.object(v, "collect") as collector:
                with contextlib.redirect_stdout(output):
                    status = v.main()
            self.assertEqual(status, 2)
            collector.assert_not_called()
            result = json.loads(output.getvalue())
            self.assertFalse(result["deployment_authorized"])
            self.assertEqual(result["reason"], "trusted policy unavailable at selected revision")

    def test_gh_is_read_only_fixed_host_no_shell(self):
        with mock.patch.object(v, "bounded_command", return_value=b'{}') as command:
            v.gh_json("repos/example/test/pulls/3")
        argv = command.call_args.args[0]
        self.assertEqual(argv[argv.index("--method") + 1], "GET")
        self.assertEqual(argv[argv.index("--hostname") + 1], "github.com")


if __name__ == "__main__":
    unittest.main()

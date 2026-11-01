#!/usr/bin/env python3
"""Read-only GitHub artifact eligibility observation; never deployment authority."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time

SHA = r"[0-9a-f]{40}"
POLICY_PATH = "policy/artifact-promotion.json"
MAX_JSON = 2 * 1024 * 1024


class Unavailable(Exception):
    """Missing, malformed or unavailable evidence (exit 2)."""


class Rejected(Exception):
    """Well-formed evidence contradicts requirements (exit 1)."""


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def integer(value):
    if type(value) is not int or value <= 0:
        raise Unavailable("invalid positive integer")
    return value


def match(pattern, value):
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        raise Unavailable("invalid identifier")
    return value


def field(obj, path):
    try:
        for key in path.split("."):
            obj = obj[key]
        return obj
    except (KeyError, TypeError):
        raise Unavailable("missing required evidence") from None


def stamp(value):
    match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value)
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise Unavailable("invalid timestamp") from None


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Unavailable("duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Unavailable("invalid JSON number")))
    except (ValueError, UnicodeError, RecursionError):
        raise Unavailable("invalid JSON") from None


def bounded_command(argv, limit, timeout=30, env=None):
    """Drain stdout incrementally; never collect or expose stderr/credentials."""
    try:
        with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env) as proc:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                data = bytearray()
                deadline = time.monotonic() + timeout
                try:
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            raise Unavailable("provider command timed out")
                        chunk = os.read(proc.stdout.fileno(), min(65536, limit + 1 - len(data)))
                        if not chunk:
                            break
                        data.extend(chunk)
                        if len(data) > limit:
                            raise Unavailable("provider output exceeds bound")
                    if proc.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
                        raise Unavailable("provider command unavailable")
                    return bytes(data)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
    except (OSError, subprocess.TimeoutExpired):
        raise Unavailable("provider command unavailable") from None


def validate_policy(p):
    keys = {"schema_version", "repository", "repository_id", "workflow_id", "workflow_path",
            "workflow_blob_sha", "allowed_reviewer_ids", "max_age_seconds", "max_artifact_bytes", "artifact_name"}
    if type(p) is not dict or set(p) != keys:
        raise Unavailable("policy fields invalid")
    if type(p["schema_version"]) is not int or p["schema_version"] != 1:
        raise Unavailable("unsupported policy schema")
    match(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}", p["repository"])
    match(r"\.github/workflows/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}\.yml", p["workflow_path"])
    match(SHA, p["workflow_blob_sha"])
    for key in ("repository_id", "workflow_id", "max_age_seconds", "max_artifact_bytes"):
        integer(p[key])
    if p["max_age_seconds"] > 86400 or p["max_artifact_bytes"] > 20 * 1024 * 1024:
        raise Unavailable("policy bounds invalid")
    reviewers = p["allowed_reviewer_ids"]
    if type(reviewers) is not list or not 1 <= len(reviewers) <= 100:
        raise Unavailable("reviewer policy invalid")
    for reviewer in reviewers:
        integer(reviewer)
    if len(set(reviewers)) != len(reviewers):
        raise Unavailable("duplicate reviewer")
    match(r"[^\x00-\x1f\x7f]{1,128}", p["artifact_name"])
    return p


def load_policy(directory, revision):
    match(SHA, revision)
    # Ignore replacement refs, ambient alternate object stores and injected Git config.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_LAZY_FETCH="1")
    command = ["git", "--no-replace-objects", "-C", str(directory), "cat-file"]
    kind = bounded_command(command + ["-t", revision], 32, env=env)
    if kind != b"commit\n":
        raise Unavailable("trusted revision must be an actual commit")
    try:
        raw = bounded_command(command + ["blob", revision + ":" + POLICY_PATH], 65536, env=env)
    except Unavailable:
        raise Unavailable("trusted policy unavailable at selected revision") from None
    return validate_policy(decode(raw))


def gh_json(route):
    # Called only with routes constructed below; never consume response URLs.
    if not route.startswith("repos/") or any(c in route for c in "\r\n"):
        raise Unavailable("invalid API route")
    raw = bounded_command(["gh", "api", "--hostname", "github.com", "--method", "GET",
                           "-H", "Accept: application/vnd.github+json",
                           "-H", "X-GitHub-Api-Version: 2026-03-10", route], MAX_JSON)
    return decode(raw)


def read_archive(path, maximum):
    try:
        # O_NOFOLLOW defeats a leaf symlink swap; fstat verifies the opened object.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            before = os.fstat(source.fileno())
            require(stat.S_ISREG(before.st_mode), "artifact is not a regular file")
            require(0 < before.st_size <= maximum, "artifact size rejected")
            data = source.read(maximum + 1)
            after = os.fstat(source.fileno())
            require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "artifact changed during read")
            require(len(data) == before.st_size, "artifact changed or exceeds bound")
            return {"size": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
    except OSError:
        raise Unavailable("artifact file unavailable or symlink") from None


def collect(policy, pr_number, run_id, artifact_id, artifact_file, transport=gh_json):
    validate_policy(policy)
    for number in (pr_number, run_id, artifact_id):
        integer(number)
    root = "repos/" + policy["repository"]
    pr_route, run_route = f"{root}/pulls/{pr_number}", f"{root}/actions/runs/{run_id}"
    repo, pr, run = transport(root), transport(pr_route), transport(run_route)
    head = match(SHA, field(pr, "head.sha"))
    workflow = transport(f"{root}/contents/{policy['workflow_path']}?ref={head}")
    artifact = transport(f"{root}/actions/artifacts/{artifact_id}")
    def reviews_snapshot():
        reviews = []
        for page in range(1, 6):
            batch = transport(f"{pr_route}/reviews?per_page=100&page={page}")
            if type(batch) is not list or len(batch) > 100:
                raise Unavailable("malformed reviews page")
            reviews.extend(batch)
            if len(batch) < 100:
                return reviews
        raise Unavailable("incomplete review coverage")
    reviews = reviews_snapshot()
    local = read_archive(artifact_file, policy["max_artifact_bytes"])
    artifact_after = transport(f"{root}/actions/artifacts/{artifact_id}")
    reviews_after = reviews_snapshot()
    return {"repository": repo, "pr": pr, "run": run, "workflow": workflow,
            "artifact": artifact, "reviews": reviews, "reviews_complete": True, "local": local,
            "artifact_after": artifact_after, "reviews_after": reviews_after,
            "pr_after": transport(pr_route), "run_after": transport(run_route)}


def evaluate(policy, revision, pr_number, run_id, artifact_id, obs, now=None):
    """Pure evaluator. Synthetic observations prove tests only, never real approval."""
    p = validate_policy(policy)
    match(SHA, revision)
    for value in (pr_number, run_id, artifact_id):
        integer(value)
    now = now or dt.datetime.now(dt.timezone.utc)
    pr, run, artifact = (field(obs, key) for key in ("pr", "run", "artifact"))
    rid = p["repository_id"]
    require(integer(field(obs, "repository.id")) == rid and
            field(obs, "repository.full_name") == p["repository"], "repository mismatch")
    head = match(SHA, field(pr, "head.sha"))
    base = match(SHA, field(pr, "base.sha"))
    head_repo = integer(field(pr, "head.repo.id"))
    author = integer(field(pr, "user.id"))
    require(integer(field(pr, "number")) == pr_number and field(pr, "state") == "open"
            and field(pr, "draft") is False, "PR is not open and ready")
    require(integer(field(pr, "base.repo.id")) == rid, "PR base repository mismatch")
    require(integer(field(run, "id")) == run_id and integer(field(run, "repository.id")) == rid,
            "run repository or ID mismatch")
    require(field(run, "repository.full_name") == p["repository"], "run repository name mismatch")
    attempt = integer(field(run, "run_attempt"))
    publisher = integer(field(run, "triggering_actor.id"))
    actor = integer(field(run, "actor.id"))
    require(integer(field(run, "workflow_id")) == p["workflow_id"] and
            field(run, "path") == p["workflow_path"], "workflow mismatch")
    require(field(run, "event") == "pull_request" and field(run, "status") == "completed"
            and field(run, "conclusion") == "success", "run not successful pull_request")
    require(match(SHA, field(run, "head_sha")) == head and
            integer(field(run, "head_repository.id")) == head_repo, "run head mismatch")
    associations = field(run, "pull_requests")
    if type(associations) is not list or not associations:
        raise Unavailable("run PR association missing")
    associated = False
    for item in associations:
        if integer(field(item, "number")) == pr_number:
            require(integer(field(item, "head.repo.id")) == head_repo and
                    match(SHA, field(item, "head.sha")) == head and
                    integer(field(item, "base.repo.id")) == rid and
                    match(SHA, field(item, "base.sha")) == base, "run PR association mismatch")
            associated = True
    require(associated, "run not associated with PR")
    require(field(obs, "workflow.type") == "file" and
            field(obs, "workflow.path") == p["workflow_path"] and
            match(SHA, field(obs, "workflow.sha")) == p["workflow_blob_sha"], "workflow blob not accepted")
    require(integer(field(artifact, "id")) == artifact_id and field(artifact, "expired") is False
            and field(artifact, "name") == p["artifact_name"], "artifact identity or expiration rejected")
    for key, expected in (("id", run_id), ("repository_id", rid), ("head_repository_id", head_repo)):
        require(integer(field(artifact, "workflow_run." + key)) == expected, "artifact provenance mismatch")
    require(match(SHA, field(artifact, "workflow_run.head_sha")) == head, "artifact head mismatch")
    size = integer(field(artifact, "size_in_bytes"))
    digest = match(r"sha256:[0-9a-f]{64}", field(artifact, "digest"))
    require(size <= p["max_artifact_bytes"] and integer(field(obs, "local.size")) == size
            and match(r"sha256:[0-9a-f]{64}", field(obs, "local.digest")) == digest,
            "artifact bytes do not match provider digest and size")
    created, expires, started = (stamp(field(obj, key)) for obj, key in
                                 ((artifact, "created_at"), (artifact, "expires_at"), (run, "run_started_at")))
    require(started <= created <= now < expires and
            (now - created).total_seconds() <= p["max_age_seconds"], "artifact freshness rejected")
    require(field(obs, "reviews_complete") is True, "review coverage incomplete")
    reviews = field(obs, "reviews")
    if type(reviews) is not list or len(reviews) >= 500:
        raise Unavailable("reviews malformed or incomplete")
    latest, seen = {}, set()
    for review in reviews:
        review_id = integer(field(review, "id"))
        require(review_id not in seen, "duplicate review observation")
        seen.add(review_id)
        reviewer = integer(field(review, "user.id"))
        state = field(review, "state")
        if state not in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"):
            raise Unavailable("unknown review state")
        if state == "PENDING":
            continue
        submitted = stamp(field(review, "submitted_at"))
        require(submitted <= now, "review timestamp in future")
        match(SHA, field(review, "commit_id"))
        if reviewer in p["allowed_reviewer_ids"] and state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            order = (submitted, review_id)
            if reviewer not in latest or order > latest[reviewer][0]:
                latest[reviewer] = (order, review)
    require(not any(r[1]["state"] == "CHANGES_REQUESTED" for r in latest.values()), "changes requested")
    approved = [r[1] for reviewer, r in latest.items() if reviewer not in (author, publisher, actor)
                and r[1]["state"] == "APPROVED" and r[1]["commit_id"] == head]
    require(bool(approved), "no independent current-head approval")
    # Readback includes every decision-relevant PR/run field, not bodies or mutable display names.
    for key in ("number", "state", "draft", "head.sha", "head.repo.id", "base.repo.id", "base.sha", "user.id"):
        require(json.dumps(field(pr, key), sort_keys=True) ==
                json.dumps(field(field(obs, "pr_after"), key), sort_keys=True), "PR changed during observation")
    for key in ("id", "run_attempt", "head_sha", "head_repository.id", "repository.id", "repository.full_name",
                "workflow_id", "path", "event", "status", "conclusion", "triggering_actor.id", "actor.id", "run_started_at", "pull_requests"):
        require(json.dumps(field(run, key), sort_keys=True) ==
                json.dumps(field(field(obs, "run_after"), key), sort_keys=True), "run changed during observation")
    for key in ("id", "expired", "name", "size_in_bytes", "digest", "created_at", "expires_at",
                "workflow_run.id", "workflow_run.repository_id", "workflow_run.head_repository_id", "workflow_run.head_sha"):
        require(json.dumps(field(artifact, key), sort_keys=True) ==
                json.dumps(field(field(obs, "artifact_after"), key), sort_keys=True), "artifact changed during observation")
    def review_identity(snapshot):
        if type(snapshot) is not list or len(snapshot) >= 500:
            raise Unavailable("reviews malformed or incomplete")
        fields = ("id", "user.id", "state", "commit_id", "submitted_at")
        return sorted(json.dumps([field(review, key) for key in fields], sort_keys=True)
                      for review in snapshot)
    require(review_identity(reviews) == review_identity(field(obs, "reviews_after")),
            "reviews changed during observation")
    return {"eligible_for_executor_review": True, "deployment_authorized": False,
            "repository": p["repository"], "repository_id": rid, "policy_revision": revision,
            "pr": pr_number, "head_sha": head, "base_sha": base, "run": run_id, "run_attempt": attempt,
            "workflow_blob_sha": p["workflow_blob_sha"], "artifact": artifact_id, "digest": digest,
            "size": size, "review_id": approved[0]["id"], "reviewer_id": approved[0]["user"]["id"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-dir", required=True, type=Path)
    parser.add_argument("--trusted-revision", required=True)
    for name in ("pr", "run", "artifact"):
        parser.add_argument("--" + name, required=True, type=int)
    parser.add_argument("--artifact-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        policy = load_policy(args.repository_dir, args.trusted_revision)
        observation = collect(policy, args.pr, args.run, args.artifact, args.artifact_file)
        result = evaluate(policy, args.trusted_revision, args.pr, args.run, args.artifact, observation)
    except (Rejected, Unavailable) as error:
        print(json.dumps({"eligible_for_executor_review": False, "deployment_authorized": False,
                          "reason": str(error)}))
        return 1 if isinstance(error, Rejected) else 2
    except (KeyError, TypeError, ValueError, OverflowError):
        print(json.dumps({"eligible_for_executor_review": False, "deployment_authorized": False,
                          "reason": "malformed evidence"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

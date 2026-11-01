#!/usr/bin/env python3
"""Run an accepted checker over an exact candidate snapshot in a bounded worker.

Only trusted orchestration may choose trusted_revision. A successful result is
advisory test evidence, never review, acceptance, promotion or deployment authority.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid
import unicodedata

MAX_FILES = 1000
MAX_BLOB = 1024 * 1024
MAX_TOTAL = 16 * MAX_BLOB
MAX_OUTPUT = 64 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"(?:docker\.io/library/)?python:[a-zA-Z0-9][a-zA-Z0-9_.-]*@sha256:[0-9a-f]{64}\Z")
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"
# Resolve from the trusted orchestrator PATH before sanitizing child environments.
GIT_EXECUTABLE = shutil.which("git")
SAFE_REASONS = frozenset({
    "tool-unavailable", "timeout", "output-limit", "snapshot-timeout",
    "git-object-read-failed", "invalid-revision", "revision-not-commit",
    "invalid-tree-entry", "nonregular-tree-entry", "blob-limit", "snapshot-limit",
    "blob-size-mismatch", "unsafe-path", "trusted-policy-missing",
    "trusted-policy-invalid", "trusted-checker-missing", "invalid-timeout",
    "worker-cleanup-unconfirmed", "filesystem-alias",
})


class Refused(Exception):
    """A fixed, safe reason suitable for public summaries."""


def bounded(command, env, limit, timeout, cwd=None):
    """Drain both pipes concurrently, with a shared size and wall clock bound."""
    try:
        process = subprocess.Popen(command, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        raise Refused("tool-unavailable") from None
    output = bytearray()
    errors = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, output)
            selector.register(process.stderr, selectors.EVENT_READ, errors)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Refused("timeout")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if len(output) + len(errors) + len(chunk) > limit:
                        raise Refused("output-limit")
                    key.data.extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Refused("timeout")
            try:
                result = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise Refused("timeout") from None
        return result, bytes(output), bytes(errors)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


def minimal_env(home):
    return {"PATH": SAFE_PATH, "HOME": str(home), "DOCKER_CONFIG": str(home),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_LAZY_FETCH": "1", "LC_ALL": "C"}


class Objects:
    def __init__(self, repository, env):
        self.repository = str(Path(repository).resolve())
        self.env = env
        self.deadline = time.monotonic() + 30

    def git(self, *args, limit=MAX_BLOB):
        if GIT_EXECUTABLE is None:
            raise Refused("tool-unavailable")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Refused("snapshot-timeout")
        code, out, _ = bounded([GIT_EXECUTABLE, "--no-replace-objects", "-C", self.repository,
                                "-c", "core.hooksPath=/dev/null", *args],
                               self.env, limit, min(10, remaining))
        if code:
            raise Refused("git-object-read-failed")
        return out

    def commit(self, revision):
        if not SHA.fullmatch(revision):
            raise Refused("invalid-revision")
        if self.git("cat-file", "-t", revision, limit=64) != b"commit\n":
            raise Refused("revision-not-commit")

    def entries(self, revision):
        self.commit(revision)
        listing = self.git("ls-tree", "-r", "-z", "--full-tree", revision,
                           limit=MAX_FILES * 400)
        entries = []
        aliases = {}
        total = 0
        for record in listing.split(b"\0"):
            if not record:
                continue
            try:
                metadata, raw_path = record.split(b"\t", 1)
                mode, kind, oid = metadata.split(b" ")
                path = raw_path.decode("utf-8", "strict")
            except (ValueError, UnicodeError):
                raise Refused("invalid-tree-entry") from None
            validate_path(path)
            components = path.split("/")
            for length in range(1, len(components) + 1):
                prefix = "/".join(components[:length])
                normalized = unicodedata.normalize("NFD", prefix).casefold()
                original = aliases.setdefault(normalized, prefix)
                if original != prefix:
                    raise Refused("filesystem-alias")
            if mode not in (b"100644", b"100755") or kind != b"blob":
                raise Refused("nonregular-tree-entry")
            size = int(self.git("cat-file", "-s", oid.decode("ascii"), limit=64))
            if size > MAX_BLOB:
                raise Refused("blob-limit")
            total += size
            entries.append((path, oid.decode("ascii"), size))
            if len(entries) > MAX_FILES or total > MAX_TOTAL:
                raise Refused("snapshot-limit")
        return entries

    def blob(self, oid, size):
        data = self.git("cat-file", "blob", oid, limit=MAX_BLOB + 1024)
        if len(data) != size:
            raise Refused("blob-size-mismatch")
        return data


def validate_path(path):
    if (not path or len(path.encode("utf-8")) > 240 or path.startswith("/")
            or "\\" in path or any(part in ("", ".", "..") or part.lower() == ".git"
                                   for part in path.split("/"))):
        raise Refused("unsafe-path")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refused("trusted-policy-invalid")
        result[key] = value
    return result


def trusted_policy(objects, revision):
    entries = {path: (oid, size) for path, oid, size in objects.entries(revision)}
    policy_entry = entries.get("policy/contribution-worker.json")
    if policy_entry is None:
        raise Refused("trusted-policy-missing")
    try:
        policy = json.loads(objects.blob(*policy_entry), object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError):
        raise Refused("trusted-policy-invalid") from None
    if (not isinstance(policy, dict) or set(policy) != {"schema_version", "checker_path", "image"}
            or type(policy["schema_version"]) is not int or policy["schema_version"] != 1
            or not isinstance(policy["checker_path"], str)
            or not isinstance(policy["image"], str) or not IMAGE.fullmatch(policy["image"])):
        raise Refused("trusted-policy-invalid")
    checker_path = policy["checker_path"]
    validate_path(checker_path)
    if not checker_path.endswith(".py") or checker_path not in entries:
        raise Refused("trusted-checker-missing")
    return policy, objects.blob(*entries[checker_path])


def docker_command(name, root, image):
    return ["docker", "run", "--name", name, "--pull=never", "--network=none",
            "--user=65534:65534", "--read-only", "--log-driver=none", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=64", "--memory=128m",
            "--memory-swap=128m", "--cpus=1", "--ulimit=nofile=128:128",
            "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777", "--mount",
            f"type=bind,src={root / 'candidate'},dst=/candidate,readonly", "--mount",
            f"type=bind,src={root / 'trusted'},dst=/trusted,readonly", "--entrypoint=/usr/bin/env", image,
            "-i", f"PATH={SAFE_PATH}", "HOME=/nonexistent", "TMPDIR=/tmp",
            "python3", "-I", "-B", "/trusted/checker.py", "/candidate"]


def run(repository, trusted_revision, candidate_revision, timeout=30):
    if not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise Refused("invalid-timeout")
    with tempfile.TemporaryDirectory(prefix="contribution-worker-") as directory:
        root = Path(directory)
        home = root / "home"
        home.mkdir()
        env = minimal_env(home)
        objects = Objects(repository, env)
        policy, checker = trusted_policy(objects, trusted_revision)
        entries = objects.entries(candidate_revision)
        for name in ("candidate", "trusted"):
            (root / name).mkdir(mode=0o755)
            (root / name).chmod(0o755)
        for path, oid, size in entries:
            target = root / "candidate" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(objects.blob(oid, size))
            target.chmod(0o444)
        for target in (root / "candidate").rglob("*"):
            if target.is_dir():
                target.chmod(0o755)
        with (root / "trusted" / "checker.py").open("xb") as stream:
            stream.write(checker)
        (root / "trusted" / "checker.py").chmod(0o444)
        name = "contribution-worker-" + uuid.uuid4().hex
        started = True
        try:
            code, out, err = bounded(docker_command(name, root, policy["image"]), env,
                                     MAX_OUTPUT, timeout)
        except Refused as failure:
            if str(failure) == "tool-unavailable":
                started = False
            raise
        finally:
            # Only this invocation's random container is eligible for removal.
            if started:
                try:
                    cleanup, _, _ = bounded(["docker", "rm", "--force", name], env, MAX_OUTPUT, 10)
                except Refused:
                    raise Refused("worker-cleanup-unconfirmed") from None
                if cleanup:
                    raise Refused("worker-cleanup-unconfirmed")
        return {"schema_version": 1, "status": "worker-check-passed" if code == 0 else "worker-check-failed",
                "authority": "advisory-only", "trusted_revision": trusted_revision,
                "candidate_revision": candidate_revision,
                "checker_sha256": hashlib.sha256(checker).hexdigest(), "image": policy["image"],
                "exit_code": code, "output_bytes": len(out) + len(err),
                "stdout_sha256": hashlib.sha256(out).hexdigest(),
                "stderr_sha256": hashlib.sha256(err).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--trusted-revision", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    try:
        result = run(args.repository, args.trusted_revision, args.candidate_revision, args.timeout)
    except Refused as failure:
        # Refused reasons are exclusively fixed literals, never worker-controlled text.
        result = {"schema_version": 1, "status": "worker-refused", "authority": "advisory-only", "reason": str(failure) if str(failure) in SAFE_REASONS else "worker-refused"}
    except (OSError, ValueError):
        result = {"schema_version": 1, "status": "worker-refused", "authority": "advisory-only", "reason": "host-operation-failed"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "worker-check-passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

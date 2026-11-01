---
created: 2026-10-30T00:00:00Z
branch: codex/5-contribution-boundary
author: Codex
sprint: PW-0
status: active
---
# Contribution boundary qualification

This is the bounded implementation and qualification surface for [issue 5](https://github.com/patchwerks/patchwerks/issues/5), under PW-0.2 in [the sprint plan](../.agentile/sprints/active/2026-10-25-coordination/SPRINT.md). It implements an isolated worker launcher and a read-only artifact eligibility observation. It does not deploy, promote artifacts, change GitHub settings, accept a contribution, or graduate the broader autonomy capability. [PR 9](https://github.com/patchwerks/patchwerks/pull/9) is separate work and is not accepted by this qualification.

## Worker trust selection

The trusted caller must supply an independently accepted full lowercase commit SHA. The launcher cannot establish that acceptance itself; ancestry, a branch name, a candidate's policy and a green candidate check do not establish trust.

```text
python3 scripts/contribution_worker.py --repository LOCAL_CLONE \
  --trusted-revision ACCEPTED_40_HEX_SHA --candidate-revision CANDIDATE_40_HEX_SHA \
  --timeout 30
```

The launcher reads `policy/contribution-worker.json` exclusively from the trusted commit. Its exact keys are `schema_version` (integer 1), `checker_path` (relative `.py` path) and `image` (official Python tag pinned to a complete SHA-256 digest). Unknown or duplicate keys, missing policy and a missing checker refuse execution. There is no working-tree or HEAD fallback. This change intentionally adds no real accepted policy; fixtures construct synthetic policies in temporary Git repositories.

The local clone is a trusted input: its Git executable, `.git/config`, object-store metadata and repository setup must come from trusted provisioning. Use a fresh trusted clone. The launcher does not sandbox Git metadata or turn an attacker-supplied local Git repository into a safe input.

Both revisions must be actual commit objects. `git --no-replace-objects ls-tree` and `cat-file` read exact objects, ignoring replacement refs and mutable checkout contents. Extraction never invokes candidate scripts, dependency hooks or archive attributes. Paths are bounded to 240 UTF-8 bytes; absolute paths, traversal, `.git` components, symlinks, gitlinks and other nonregular entries are refused. Every path prefix is compared using Unicode NFD normalization and case folding. Different original prefixes with the same normalized form are refused as `filesystem-alias`, including on Linux, so staging cannot silently merge directories or overwrite names on a case-insensitive or normalizing filesystem. Files are created exclusively in the owned staging tree. Shell syntax and newlines remain inert filename data. A snapshot allows at most 1,000 files, 1 MiB per blob and 16 MiB total. Each Git command has at most 10 seconds; all preparation shares a 30-second deadline.

The checker is a single self-contained file selected from the trusted revision, staged separately from the candidate snapshot. A candidate may replace its checker and policy files, but those bytes never select the enforcement program. Staging uses owned temporary directories and readable regular files; source and checker mounts are read-only inside the worker.

## Worker execution and output

An independently provisioned official Python image must already exist locally; the launcher uses `--pull=never`. Its Docker CLI environment is constructed from fixed values and an empty temporary home/config, without caller credentials or GitHub variables. Inside the container, an explicit `/usr/bin/env -i` entrypoint sets only PATH, HOME and TMPDIR before `python3 -I -B /trusted/checker.py /candidate`.

The worker runs as UID/GID 65534, without network, capabilities, privilege escalation, writable root, host home, devices or Docker socket. Limits are 64 processes, 128 MiB memory with no additional swap, one CPU and 128 file descriptors. `/tmp` is a 16 MiB tmpfs with mode 1777 and nosuid/nodev/noexec. Docker daemon logging is disabled. Only the candidate and trusted checker directories are mounted, both read-only.

Combined stdout/stderr is capped at 64 KiB, drained concurrently, and never printed verbatim to Actions logs. Runtime defaults to 30 seconds, with a maximum of 60 seconds. Summaries contain a fixed status/reason, hashes, byte count and provenance. The invocation removes only its randomly named container, including on timeout or output overflow. Failure to confirm cleanup fails closed. Missing Docker cannot yield success.

`worker-check-passed` is advisory test evidence, not an acceptance or deployment decision. A malicious checker output such as an Actions annotation or forged approval JSON has no authority and is reduced to hashes. Provenance identifies the requested trusted/candidate revisions, checker hash and image; it does not certify that a caller's chosen revision was independently accepted.

## Artifact eligibility observation

```text
python3 scripts/verify_promotion.py --repository-dir LOCAL_CLONE \
  --trusted-revision ACCEPTED_40_HEX_SHA --pr PR_NUMBER --run RUN_ID \
  --artifact ARTIFACT_ID --artifact-file LOCAL_ARCHIVE
```

The verifier reads `policy/artifact-promotion.json` at the supplied trusted revision, with no HEAD fallback. Missing policy blocks eligibility; this change supplies no real promotion policy. Its read-only GitHub evidence collector and deterministic evaluator compare repository identity, PR head/base, workflow identity and blob, run attempt/event/result, artifact identity/digest/size/freshness, and independent current-head review identity. Contradictory or incomplete evidence fails closed. Candidate bodies and purported success text cannot authorize a write. Local archives are hashed without execution or extraction.

Success reports `eligible_for_executor_review: true` and always `deployment_authorized: false`. Readback detects changes during collection, but a race remains after the final observation. Any future executor must revalidate under its own scoped authority at the point of action. A workflow blob comparison and provider run metadata do not fully establish an attestation binding the exact executed workflow to the observed run. This qualification does not claim that gap is closed, nor does it provide a deployment executor.

## Qualification and evidence

Local evidence: the confined gate discovered 23 worker tests: **21 passed and two real-Docker tests explicitly skipped**. The full canonical gate after the filesystem-alias fix discovered 43 tests: **41 passed and two real-Docker tests skipped**, against baseline 5. It also passed four tripwires and 29/29 frontmatter checks. The counter includes discovered skipped tests; 43 is not a count of executed passing tests. Existing formal/production vacuity remains unchanged.

Both direct Git-object case/Unicode alias rejection tests passed in that gate. The artifact verifier contains 15 tests, all included in the measured full gate. They use synthetic observations/provider transports and do not establish live GitHub artifact eligibility. Local Docker isolation was not demonstrated by those local results. **Hosted controlled-fixture qualification passed; independent acceptance and production enforcement remain pending.**

Hosted evidence for [PR 10](https://github.com/patchwerks/patchwerks/pull/10) is scoped to head `dd1af648ced324be021a04506beee7fbc4f46402`, synthetic merge checkout `01e9f08427dca2dd24238a159a45b10232dbeaf8`, and accepted base `b99937e5f22ff34455723aaca667b394bd2be86e`. The [boundary qualification job](https://github.com/patchwerks/patchwerks/actions/runs/41041916979/job/124016530598) completed successfully at 2026-10-30T10:36Z on Ubuntu 24.04.5, Python 3.12.11 and Git 2.56.0: **all 23 worker tests passed, including both real-Docker tests, with zero skips; all 15 artifact-verifier tests passed**. This demonstrates the controlled hostile fixtures under that hosted container configuration. Artifact observations remain synthetic and do not demonstrate production artifact acceptance.

The separate [hosted canonical gate](https://github.com/patchwerks/patchwerks/actions/runs/41041916928/job/124016530540) passed with 43 discovered tests: 41 passed and two Docker tests skipped in its default profile, plus four tripwires and 29/29 frontmatter checks. Pinned actions emitted a Node 20-to-24 runtime warning; it did not fail either job. These results establish evidence for the exact revisions above, not unreviewed subsequent changes or production enforcement.

```sh
python3 -I -B -m unittest discover -s tests -p 'test_contribution_worker.py' -v
python3 -I -B -m unittest discover -s tests -p 'test_verify_promotion.py' -v
PATCHWERKS_DOCKER_TESTS=1 python3 -I -B -m unittest discover -s tests -p 'test_contribution_worker.py' -v
```

The explicit Docker profile requires the pinned image to be provisioned separately and fails if Docker or that image is absent. Its two real tests assert kernel-observed UID/GID, NoNewPrivs, empty effective capabilities, RLIMIT_NOFILE, and cgroup v2 memory/swap/process/CPU limits on the targeted Ubuntu 24.04 worker; unsupported resource observation fails explicitly. They exercise network/home/socket denial, read-only source/root/checker writes, a harmless simulated dependency hook's inability to read an outside canary, candidate checker/policy replacement, inert hostile filenames, forged output, timeout and output overflow. Unit tests with a fake Docker command prove orchestration only. [The Gherkin scenarios](../tests/contribution-boundary.feature) are acceptance specifications mapped to unittest methods; there is no BDD runner or claim of Gherkin execution.

[The qualification workflow](../.github/workflows/contribution-boundary.yml) provisions the fixed image before running controlled fixtures in a disposable GitHub-hosted Ubuntu worker. It uses pinned actions, no persisted checkout credentials, clean process environments, a ten-minute job limit and no artifact upload or deployment. Its proposed host-side orchestration requires independent source review before use. Actual hostile fixture code executes only in the restricted container. The candidate-editable workflow cannot protect itself from hostile workflow edits; accepted higher-authority enforcement and independent review remain prerequisites to a production contribution gate.

## References

The execution controls follow the [Docker container run reference](https://docs.docker.com/engine/containers/run/). Workflow trust and credential separation follow [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use). Artifact metadata is interpreted using the [GitHub Actions artifacts API](https://docs.github.com/en/rest/actions/artifacts). These references describe platform capabilities; only the measured evidence above supports this implementation's qualification status.

## Changelog

- 2026-10-31: Implemented comment-preserving review decisions and umask-independent mount-root permissions with four new regressions; confined gate passed 45 tests with two Docker skips, with new hosted qualification pending.

- 2026-10-30: Recorded successful hosted qualification at PR 10 head `dd1af648ced324be021a04506beee7fbc4f46402`: 23 worker tests including both real-Docker cases and 15 synthetic artifact tests passed; preserved local/default-profile skips and independent/production acceptance limits.

- 2026-10-30: Added portable filesystem-alias rejection and exclusive staging writes, with passing direct Git-object case/Unicode fixtures; clarified trusted local Git metadata prerequisites. The updated confined canonical gate discovered 43 tests: 41 passed and two real-Docker tests skipped.
- 2026-10-30: Added the bounded worker and advisory artifact qualification contract, mapped acceptance scenarios, and recorded confined local results and separately scoped hosted real-Docker qualification; independent acceptance remains pending.

## Review follow-up — 2026-10-31

Implemented the two bounded PR 10 review corrections: only APPROVED, CHANGES_REQUESTED and DISMISSED replace a reviewer's latest decision; later COMMENTED observations retain their metadata validation without clearing an outstanding decision. Candidate/checker mount roots are explicitly chmod 0755 after creation, independently of the caller's umask. Four new regression tests cover the requested changes-requested/comment sequence, approval preservation, malformed comment metadata and mount permissions under umask 077. Both opt-in actual Docker tests now run with umask 077. The existing latest-decision test now uses consistent readback evidence, and loop callbacks bind their per-case values explicitly.

Fresh confined verification passed **47 discovered tests: 45 passed and two opt-in Docker tests skipped**, plus four tripwires and 29/29 frontmatter checks. The explicit promotion suite passed **18/18 with zero skips**. The explicit worker suite also completed in 91.724 seconds: **24 discovered, 22 passed and two Docker skips**. Existing formal/production vacuity remains unchanged. Historical hosted results above apply to their named earlier revisions; **new hosted CI and actual Docker qualification for these corrections are pending**. Existing runtime restrictions and authority limits remain unchanged.

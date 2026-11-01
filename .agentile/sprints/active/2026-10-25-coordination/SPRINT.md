---
created: 2026-10-25T13:54:14Z
branch: main
author: patchWERKS / Codex
sprint: PW-0
status: active
---
# PW-0 coordination bootstrap

## Goal and authority

Configure the smallest GitHub-native, Agentile-based metarepo foundation requested by the owner. Public governance repository approved in this conversation; private source and host data remain private. No hardware, live service lifecycle, trading, wallet or platform-account action is authorized by this sprint.

## Work packages

- PW-0.1: Inspect current organization, board, product plans, XO PRD and Agentile source. Acceptance: record current repository ownership/visibility, board identities and the Free-tier limitations.
- PW-0.2: Configure one public coordination repository with pinned Agentile foundations, real ratchet tests, isolated read-only CI and mandatory all-harness instructions. Acceptance: local checks, adversarial boundary tests and actual GitHub CI results, followed by enforced main-branch protection.
- PW-0.3: Extend the existing private Project with product/risk metadata while preserving all ten initial issues and their status. Acceptance: API readback verifies unchanged existing items and the new fields.
- PW-0.4: Publish concrete adapter, trust, release and jj contracts. Acceptance: sources cited, no unsupported production claims, remaining identity/runtime gates represented by bounded issues.
- PW-0.5: Add pinned governance entrypoints to the two current organization repositories through reviewable PRs, preserving existing plans and runtime restrictions. Acceptance: independent review and checks before merge; pending PRs remain explicitly pending.

## Verification choices

No new distributed scheduler, credential broker, execution daemon or state machine is implemented here, so TLA+ and Gherkin implementation steps are not applicable to PW-0. This is configuration/adoption work. Upstream Agentile's baseline and vacuity regression tests exercise the ratchet behavior. Adversarial checks must show that lowering a candidate baseline cannot override a trusted base and that absent evidence cannot yield a graduated pass.

## Evidence and remaining work

Append exact revisions and observed results during closeout. Product adapters, independent review identities and privileged/live execution are separate tracked work, not implied by this bootstrap.

## PW-0.2 follow-up: contribution boundary qualification

Canonical task: [issue #5](https://github.com/patchwerks/patchwerks/issues/5).
This separate candidate starts from accepted `b99937e`; audit-helper PR #9 is
independent and is not treated as accepted policy.

Planned deliverables:

- A bounded disposable worker loads its policy and checker from an explicitly
  supplied accepted commit, reads an immutable candidate snapshot, and admits
  no candidate-controlled policy, credentials, network or writable host mount.
- Hostile fixtures exercise checker replacement, malicious names, simulated
  dependency hooks, forged output, denied access, output limits and timeouts.
- A read-only artifact preflight compares fresh GitHub repository, workflow,
  head, attempt, review and artifact observations with accepted policy and the
  actual archive digest. It never deploys or accepts an unsigned success file.
- Actual qualification evidence distinguishes synthetic trusted-base fixtures,
  observed container boundaries, local unit tests and independent acceptance.

The fixtures use synthetic accepted revisions only to test selection behavior.
No production policy is installed in this slice: an accepted revision missing
the policy must refuse before executing a candidate. The initial implementation
is not automatically trusted merely because its tests pass. Final installation
requires independent policy/workflow review and the scoped identities tracked
by issue #3. Live health/recovery remains with a separate authorized executor.

TLA+ is not applicable: this slice adds no distributed claim or deployment state
machine. Before/after GitHub observations detect stale inputs for this read-only
preflight; they do not supply an atomic merge/deploy transaction. CLI behavior
and negative boundary cases are specified in the paired qualification document
and executable fixtures. No product runtime or physical acceptance is implied.

## Changelog

- 2026-10-30: Added the bounded PW-0.2 / issue #5 implementation and qualification
  plan; current dispatch and acceptance remain on the canonical GitHub issue.
- 2026-10-29: PW-0.2 / [issue #5](https://github.com/patchwerks/patchwerks/issues/5)
  local follow-up adds hostile-input fixtures for the accepted audit helper and
  a minimal commit-object validation fix. See the [bounded evidence report](../../../../docs/hostile-audit-fixtures.md).
  Candidate only: upstream publication, independent acceptance and complete
  contribution/promotion isolation remain pending; no workflow activation occurs.
- 2026-10-30: PW-0.2 / issue #5 continuation adds rename and symlink regression
  cases. Accepted-helper comparison reproduced the two object-type failures;
  candidate verification passed 15 tests. No state-machine or product CLI change
  is introduced, so TLA+ and Gherkin are not applicable to this build-infrastructure
  slice. See the same bounded evidence report for worker limits and the current
  read-only publication blocker. This session holds no live resources; its local
  continuation is handed off for publication and independent review.
- 2026-10-30: Further PW-0.2 / issue #5 adversarial work reproduced two local
  replacement-reference bypasses. Object admission and diff now ignore those
  replacements; three new regressions bring the canonical gate to 18 tests.
  The evidence report distinguishes local-metadata control from ordinary PR
  content and retains the broader CI/promotion acceptance limits.

- 2026-11-01: Integrated accepted main `7c18f297` into the issue #5 candidate.
  The original `b99937e` starting-point statement above records historical
  scope; accepted main now includes the audit-helper fixes from PR #9 and scoped
  identity work from PR #11. Both evidence histories are retained. Fresh
  exact-head checks and independent review remain required.

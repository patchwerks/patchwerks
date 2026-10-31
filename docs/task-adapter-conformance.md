---
created: 2026-10-29T20:18:35Z
branch: codex/issue-4-offline-contract
author: patchWERKS / Codex
sprint: PW-0
status: active
---
# Offline task-adapter contract preparation

Scope: [issue 4](https://github.com/patchwerks/patchwerks/issues/4), PW-0.4.
This is a synthetic conformance fixture suite and a pure reference decision model.
It is not a Hermes/OmO adapter, queue, dispatcher, durable store, GitHub client or
background service. Passing these examples does not establish real round trips,
crash safety, distributed exclusivity or exactly-once effects. Issue 4 remains open.

## Source and integration gap

The inventory below records the 2026-10-29 inspection scope. The author subsequently reported identifying local native implementations, summarized below. That update is author-reported, not independently reproduced from this PR; the earlier inventory remains historical context.

The accepted coordinator base is `b99937e5f22ff34455723aaca667b394bd2be86e`;
GitHub's main revision was read back as the same revision during preparation.
The coordinator has no root PLAN.md, native adapter code or owner binding.
Its `docs/orchestration.md` explicitly delegates native implementations to the owner.
The inspected workspace's public Furbomek PLAN describes Hermes lifecycle/media
and A2A integration, which is not a Projects task-sync seam. No owner-provided
Hermes/OmO task adapter source or durable-store API was identified in the inspected
sources. This is a bounded source inventory, not a claim that no such code exists.

Required next inputs are each adapter's source revision and native task mapping,
its existing durable-store transaction boundary and receipt provenance mechanism,
and its trusted serialized-writer integration. Do not invent these APIs here.
Project field discovery, installation permissions and runtime qualification remain
separate owner work. No real Project IDs, credentials or host state appear here.

## Owner binding contract

`tests/task_adapter_contract/conformance.py` exports `assert_conformance(case,
evaluate)` for a Python unittest case and an owner-supplied normalized evaluator.
`evaluate(snapshot, delivery, recorded_effects)` returns a JSON-compatible decision
(`project`, `ignore`, `refetch` or `blocked`). The reference implementation lives
only under tests. These are fixture vocabulary, not a declared Hermes/OmO API.
An owner binding must translate real native observations and then pass these
vectors plus native persistence/transport/concurrency tests in its own repository.

`head` is one explicitly selected candidate revision, not a property of an issue.
Planning issues may use null with no PR/evidence and cannot be delivered. Multi-PR
acceptance aggregation is outside this bounded normalization and needs owner design.

The canonical snapshot supplies repository node ID, issue node ID and canonical
URL together. Project placement is never identity. Dependencies, PR links,
PLAN/WP, closure reason, head and evidence survive projection. Local subtasks do
not replace canonical data. `delivered` is only an observation of supplied closed,
completed, exact-head accepted/published evidence; it cannot close or approve an
issue. The fixture booleans do not validate evidence provenance or actor identity.

Only trusted provider receipt normalization may supply `confirmed_effect_id`;
it must correlate an emitted operation in the existing durable store. Never copy
this value from issue bodies or arbitrary origin fields. An origin string alone
cannot suppress a delivery. Real receipt authentication is not tested here.
Repository/node/URL consistency must be verified by the native provider fetch;
synthetic strings only check preservation and mismatch handling here.

Persist event/delivery identity, source revision, origin and effect outcome in the
adapter's existing durable store before relying on them across restarts. The suite
serializes/restores synthetic inputs; it does not implement or test disk durability.
An `unknown` effect for the same task always requires refetch, including with a
new delivery ID or a previously confirmed duplicate. The model never clears that
obligation. A native adapter must freshly reconcile provider state and recorded
effects before deciding what occurred; timeout, elapsed claim or restart is never
permission to repeat an uncertain write. This fixture has no retry-write decision.

All new write requests are blocked, even with injected serialized/claim flags.
Serialization is an external integration requirement, not a boolean qualification.
The suite supplies no fencing authority and proves no competing-writer exclusion.
A native writer needs independently demonstrated serialization and stale-worker
rejection before any privileged sync is enabled.

## Verification

Run `python3 -m unittest discover -s tests -v` inside a disposable, credential-free
worker with denied network, host-home and device access, bounded by a supervisor
timeout. The coordinator's existing `bash scripts/verify.sh` discovers these tests
through its unchanged ratchet command. The trusted baseline remains five tests;
synthetic vectors are subtests, not inflated independent test counts.


## Author-reported source inventory and native follow-up — 2026-10-30

The native implementation, confinement and test results in this section are author-reported, not independently reproduced from this PR. The adapter source and native test output remain outside this public candidate. The Hermes runtime revision below does not identify the adapter source revision or bind the reported output to it.

The actual local `hermes-github-sync` package has now been identified and inspected. It registers a native Hermes CLI extension, uses Hermes's public Kanban JSON CLI, and owns a separate SQLite mapping/observation/operation journal. It defaults to held, unassigned projection tasks; optional telemetry is a separate mode. The earlier inventory's absence of identified source must no longer be interpreted as an absence of a native implementation.

The bounded local follow-up canonicalizes SQLite database/lock identity across symlink aliases, rejects preexisting hardlinked databases, and atomically settles one output baseline with its exact operation disposition and receipt. Explicit conflict resolution uses the same transaction. New tests cover lock aliases, transaction-abort/reopen behavior and idempotent settlement; explicitly requested native qualification now fails if Hermes is unavailable. **The final confined native suite passed 69 tests with zero skips in 257.322 seconds**, including five real Hermes tests at `433d40686dd6d4b4f0ed365efd170b9ecfe433e7`. Plugin Doctor passed in the isolated profile: runtime discovery, manifest parsing, import and registration succeeded for the standalone CLI (zero tools and zero hooks expected). No new package release or version was created. The local package and its source payload remain outside this public coordination repository; this record does not publish private source, paths or runtime state.

The state directory and its ancestors must be trusted, without concurrent hostile replacement. Local file locking does not establish distributed serialization. Newly enrolled stores now persist a canonical Project/repository/Issue/board import intent before native creation, reuse the same native idempotency key after lost acknowledgment and changed placement, refresh the held task scope note, and atomically acknowledge its mapping. Lost-ack plus placement-readd recovery passed the native regression. Existing unmarked stores retain mapped tasks but hold new imports before creation until operator inventory and reviewed migration; no live or automatic migration is supplied.

The offline conformance suite above remains synthetic. It is not a direct certification of the native package, and its fixture booleans do not establish authenticated identity or provider receipts. A real owner binding, provider round trips, conflicting-writer qualification and independent acceptance remain required. The separate local `omo-github-sync` implementation has an author-reported native checkpoint, recorded below; native qualification is not established by this public PR.

See the [PW-0.4 native follow-up plan](../.agentile/sprints/active/2026-10-25-coordination/issue-4-native-plan.md). Issue 4 remains open; no service, GitHub lifecycle mutation or unattended dispatcher is enabled by this evidence.

## Changelog

- 2026-10-30: Superseded the historical native-source inventory with the identified local Hermes package, recorded the bounded persistence follow-up and final 69-test passing native checkpoint, and retained synthetic/native and unresolved acceptance boundaries.

- 2026-10-30: Isolated Plugin Doctor passed for the final Hermes package. The coordinator canonical gate passed 12 tests, four tripwires and 30/30 frontmatter checks; these coordination checks remain separate from the 69 native-package tests. OmO qualification subsequently passed as recorded below.

- 2026-10-31: Clarified that the native results, including the historical pass statements above, are author-reported, not independently reproduced from this PR. Added private source review and revision-bound evidence requirements; historical coordinator counts are not a fresh rerun or native acceptance.


## Author-reported OmO checkpoint — 2026-10-30

The implementation, confinement and test results below are author-reported, not independently reproduced from this PR. The native runtime pin does not identify the unpublished adapter source or bind its test output.

The new local `omo-github-sync` adapter targets official `code-yeongyu/oh-my-openagent` revision `84a4e6cdecfd3f55e30ff551cab1d6ae27ce7cdb`. Its confined suite passed **15 tests with zero skips in 20.317 seconds** using Bun 1.4.4: 14 unit tests and one expanded actual-native test. The native test exercises the real create/get/list/update factories, dependency graphs, replay, graph creation under a new snapshot digest, terminal-task preservation, and recovery after a lost response following an actual create by using native list/get without duplication.

Qualification used a clean environment, denied all network access and restricted writes to isolated scratch space. It supplied no dispatcher, model or session context. Private native stores are isolated per full snapshot digest. Native `pending` is a task state, **not an execution hold**; keeping those stores outside any active dispatcher is an essential boundary, not a property inferred from the status label.

The author reports no GitHub write path. Read-only provider fetch remains unqualified against live GitHub. The adapter source payload remains local and is not copied into this public coordination repository. The reported tests cover bounded native projection/recovery; this PR does not independently establish that behavior, authenticated cross-harness handoff, distributed exclusivity, live provider acceptance or independent approval. Issue 4 remains open.

## Owner steps before native acceptance

1. Give the independent reviewer owner-approved private access to each adapter's exact source and test harness revision. Keep private code, credentials, host state and raw runtime logs outside this public repository. If source access is unavailable, native acceptance remains blocked.
2. Provide a review package tying the adapter source revision, harness revision, pinned runtime and dependency lockfile to the exact commands, isolation configuration and corresponding test output, including skips and failures. A runtime pin alone is insufficient. Use the approved private channel for sensitive evidence and publish only approved, sanitized status. Changed candidates need renewed evidence and review.
3. Obtain independent source review and test reproduction under the existing [trust boundary](trust.md). Acquire inputs through approved access, then execute candidate code only in disposable, credential-free workers without host-home, private-network or device access; keep privileged publishing separate. The author's report is not independent approval.
4. Qualify actual owner bindings and authenticated provider round trips, including identity and receipt provenance, within a separately authorized test scope. Exercise crash/restart replay and lost acknowledgments across real persistence boundaries, reconciling uncertain effects before retry. Demonstrate conflicting-writer exclusion and stale-worker rejection at the intended operating scope; a local lock is not distributed fencing.
5. Complete existing scoped-identity, dispatcher and independent acceptance gates before unattended synchronization. Acceptance of the public synthetic preparation does not accept either native adapter. This record grants no new installation, migration, deployment, GitHub lifecycle-write or service authority.

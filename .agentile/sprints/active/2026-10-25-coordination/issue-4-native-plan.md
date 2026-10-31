---
created: 2026-10-30T00:00:00Z
branch: codex/4-native-adapter-qualification
author: patchWERKS / Codex
sprint: PW-0
status: active
---
# PW-0.4 bounded native adapter follow-up

Task identity: [issue 4](https://github.com/patchwerks/patchwerks/issues/4), linked to PW-0.4 in the [sprint record](SPRINT.md). This candidate extends the existing offline-conformance preparation; it does not accept that candidate or close the issue. Native implementation payloads remain local and are not copied into the public coordination repository. Issue text and this plan grant no new authority.

## Planned scope

1. Inspect the actual Hermes CLI integration and its private SQLite transaction boundary; correct the historical source inventory.
2. Canonicalize local database/lock identity, reject preexisting hardlinked databases, and document the trusted-directory prerequisite and one-host lock limit.
3. Atomically update a selected output baseline, exact operation disposition and receipt, preserving other baseline fields; use that transaction for explicit resolution.
4. Add alias-lock, rollback/reopen and idempotency tests; make explicitly requested native qualification fail when Hermes is absent.
5. Record measured isolated rerun results and obtain independent review before claiming the increment accepted.

## Acceptance and outstanding work

The native implementation, confinement and test results below are author-reported, not independently reproduced from this PR. The adapter source and revision-bound native output are not available in this public candidate. The runtime revisions below do not identify the adapter source revisions or bind their outputs.

The final confined local suite passed **69 tests with zero skips** in 257.322 seconds, including five real Hermes tests at `433d40686dd6d4b4f0ed365efd170b9ecfe433e7`. Plugin Doctor passed in the isolated profile: runtime discovery, manifest parsing, import and registration succeeded for the standalone CLI (zero tools and zero hooks expected). No new package release or version was created. Existing offline conformance vectors remain synthetic and are not a direct certification of native storage, transport, identity or distributed exclusion. No live provider round trip, installation, service or lifecycle write is authorized by this plan itself.

New enrolled stores persist canonical import intents before native creation. Lost acknowledgment plus placement replacement now reuses the same task and passed a native regression. Existing unmarked stores retain known mappings but gate new imports on operator inventory and reviewed migration; there is no automatic or live migration.

The local OmO implementation has an author-reported checkpoint, detailed below; this public PR does not establish native qualification. Owner bindings, authenticated dispatcher integration, cross-harness handoff, live conflicting-writer acceptance and independent approval remain required. A local lock or configured runner label cannot supply those capabilities. Issue 4 remains open.

The owner must provide approved private access to exact adapter source and tests, bind source/harness/runtime/dependencies/commands/output to exact revisions, and obtain independent source review and confined test reproduction. Authenticated provider round trips and receipt provenance, crash/restart replay with uncertain-effect reconciliation, and conflicting-writer/stale-worker tests remain required before unattended synchronization. Follow the [owner steps before native acceptance](../../../../docs/task-adapter-conformance.md#owner-steps-before-native-acceptance) under the existing trust boundary. Private source and host data stay private; missing access or evidence blocks native acceptance. No installation, migration, deployment or service authority is added.


## Changelog

- 2026-10-30: Recorded the final 69-test native checkpoint, canonical-intent recovery and legacy migration hold; OmO native qualification subsequently passed as recorded below.

- 2026-10-31: Clarified that native results, including the historical checkpoint above, are author-reported, not independently reproduced from this PR. Recorded private review access, revision-bound evidence and independent qualification steps; issue 4 remains open.


## Author-reported OmO checkpoint — 2026-10-30

The local `omo-github-sync` implementation uses official `code-yeongyu/oh-my-openagent` revision `84a4e6cdecfd3f55e30ff551cab1d6ae27ce7cdb`. Under Bun 1.4.4 its confined suite passed 15 tests, zero skipped, in 20.317 seconds: 14 unit tests and one expanded real-native test. Real create/get/list/update factories exercised dependencies, replay, new-digest graphs, terminal preservation and lost-create-response recovery through native list/get without duplication.

The clean environment denied network and allowed isolated scratch only, without dispatcher/model/session context. Private native stores are separated by full snapshot digest. Native pending status does not itself hold execution; isolation from active dispatchers remains required. There is no GitHub write path; read-only live provider fetch remains unqualified. Source remains local. These results do not satisfy independent acceptance or authenticated cross-harness handoff, and do not close issue 4.

"""Reusable synthetic vectors for an owner-supplied normalized evaluator.

Call assert_conformance(test_case, evaluate). Passing only validates these offline
vectors; it cannot qualify transport, persistence, authentication or concurrency.
"""
from copy import deepcopy


def sample():
    snapshot = {
        "identity": {"repository_id": "SYNTHETIC_REPO_A", "issue_id": "SYNTHETIC_ISSUE_A",
                     "url": "https://github.com/example/sample/issues/4"},
        "dependencies": [{"issue_id": "SYNTHETIC_DEP", "state": "OPEN"}],
        "pull_requests": ["https://github.com/example/sample/pull/9"],
        "plan_wp": "PLAN.md#synthetic-wp", "state": "OPEN", "closure_reason": None,
        "head": "a" * 40, "evidence": {"head": "a" * 40, "accepted": True, "published": True},
        "revision": "synthetic-revision-2"}
    delivery = {"identity": deepcopy(snapshot["identity"]), "delivery_id": "synthetic-event-1",
                "revision": snapshot["revision"], "origin": "external"}
    return snapshot, delivery, []


def effect(snapshot, delivery, outcome="confirmed"):
    return {"identity": deepcopy(snapshot["identity"]), "delivery_id": delivery["delivery_id"],
            "effect_id": "synthetic-effect-1", "outcome": outcome, "origin": "native-adapter", "revision": snapshot["revision"]}


def vectors():
    s, d, j = sample()
    yield "canonical-projection", (s, d, j), "project", None
    for key in ("repository_id", "issue_id", "url"):
        s, d, j = sample(); d["identity"][key] += "changed"
        yield "mismatch-" + key, (s, d, j), "refetch", "identity-mismatch"
    s, d, j = sample(); s["identity"]["url"] += "?alias=1"
    yield "noncanonical-url", (s, d, j), "blocked", "invalid-observation"
    s, d, j = sample(); d["revision"] = "old"
    yield "stale-event", (s, d, j), "refetch", "revision-mismatch"
    s, d, j = sample(); j.append(effect(s, d))
    yield "duplicate", (s, d, j), "ignore", "recorded-delivery"
    s, d, j = sample(); j.append(effect(s, d)); d["origin"] = "native-adapter"
    yield "recorded-origin-loop", (s, d, j), "ignore", "recorded-delivery"
    s, d, j = sample(); d["origin"] = "native-adapter"
    yield "forged-origin-is-not-authority", (s, d, j), "project", None
    s, d, j = sample(); j.extend([effect(s, d), effect(s, d, "unknown")])
    yield "uncertainty-before-dedup", (s, d, j), "refetch", "uncertain-effect"
    s, d, j = sample(); j.append(effect(s, d, "unknown")); d["delivery_id"] = "new-event"
    yield "uncertainty-survives-new-delivery", (s, d, j), "refetch", "uncertain-effect"
    s, d, j = sample(); j.append(effect(s, d)); d["delivery_id"] = "new-reflection"
    d["confirmed_effect_id"] = "synthetic-effect-1"
    yield "correlated-origin-loop", (s, d, j), "ignore", "recorded-effect-reflection"
    for reason, accepted, published, stale in (
            ("COMPLETED", True, True, False), ("NOT_PLANNED", True, True, False),
            ("COMPLETED", False, True, False), ("COMPLETED", True, False, False),
            ("COMPLETED", True, True, True)):
        s, d, j = sample(); s.update(state="CLOSED", closure_reason=reason)
        s["evidence"].update(accepted=accepted, published=published)
        if stale:
            s["head"] = "b" * 40
        yield "closure-evidence", (s, d, j), "project", None
    s, d, j = sample(); d["local_task"] = {"state": "Done", "evidence": {"accepted": True}}
    yield "local-done-cannot-upgrade", (s, d, j), "project", None
    s, d, j = sample(); s.update(head=None, pull_requests=[], evidence={})
    yield "planning-issue-without-candidate", (s, d, j), "project", None
    s, d, j = sample(); d["confirmed_effect_id"] = "unrecorded-effect"
    yield "unrecorded-correlation", (s, d, j), "project", None
    s, d, j = sample(); e = effect(s, d); e["identity"]["issue_id"] = "OTHER"
    j.append(e); d["confirmed_effect_id"] = e["effect_id"]
    yield "other-task-correlation", (s, d, j), "project", None
    for label in ("first-writer", "competing-writer", "expired-claim", "injected-lock"):
        s, d, j = sample(); d.update(requests_write=True, serialized=True, claim=label)
        yield label, (s, d, j), "blocked", "native-serialized-writer-required"


def assert_conformance(case, evaluate):
    for name, inputs, decision, reason in vectors():
        with case.subTest(vector=name):
            before = deepcopy(inputs)
            actual = evaluate(*inputs)
            case.assertEqual(actual["decision"], decision)
            if reason:
                case.assertEqual(actual["reason"], reason)
            if decision == "project":
                canonical = inputs[0]
                projection = actual["projection"]
                for key, value in canonical.items():
                    case.assertEqual(projection[key], value, "canonical field lost: " + key)
                evidence = canonical["evidence"]
                expected_delivered = (canonical["state"] == "CLOSED"
                    and canonical["closure_reason"] == "COMPLETED"
                    and canonical["head"] is not None
                    and evidence.get("head") == canonical["head"]
                    and evidence.get("accepted") is True and evidence.get("published") is True)
                case.assertEqual(projection["delivered"], expected_delivered)
            case.assertEqual(inputs, before, "evaluator mutated canonical observations")

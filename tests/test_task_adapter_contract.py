"""Offline reference-contract tests, not native adapter integration evidence."""
import json
import unittest
from task_adapter_contract.conformance import assert_conformance, sample, effect
from task_adapter_contract.reference import evaluate


class TaskAdapterContractTests(unittest.TestCase):
    def test_reusable_vectors(self):
        assert_conformance(self, evaluate)

    def test_canonical_fields_survive_json_round_trip_and_local_subtasks(self):
        s, d, j = sample()
        d["local_task"] = {"state": "Done", "evidence": {"accepted": True}, "dependencies": []}
        restored = json.loads(json.dumps([s, d, j]))
        result = evaluate(*restored)["projection"]
        for key, value in s.items():
            self.assertEqual(result[key], value)
        self.assertFalse(result["delivered"])

    def test_closure_and_head_bound_evidence(self):
        for reason, accepted, published, stale, expected in (
            ("COMPLETED", True, True, False, True),
            ("NOT_PLANNED", True, True, False, False),
            ("COMPLETED", False, True, False, False),
            ("COMPLETED", True, False, False, False),
            ("COMPLETED", True, True, True, False)):
            with self.subTest(reason=reason, accepted=accepted, published=published, stale=stale):
                s, d, j = sample(); s.update(state="CLOSED", closure_reason=reason)
                s["evidence"].update(accepted=accepted, published=published)
                if stale:
                    s["head"] = "b" * 40
                p = evaluate(s, d, j)["projection"]
                self.assertEqual(p["delivered"], expected)
                self.assertEqual(p["evidence"], s["evidence"])
                self.assertEqual(p["closure_reason"], reason)

    def test_restart_unknown_outcome_requires_refetch_not_retry(self):
        s, d, j = sample(); j.append(effect(s, d, "unknown"))
        # Serialization models input restoration only, NOT durable native storage.
        restored = json.loads(json.dumps([s, d, j]))
        self.assertEqual(evaluate(*restored), {"decision": "refetch", "reason": "uncertain-effect"})
        restored[1]["requests_write"] = True
        self.assertEqual(evaluate(*restored)["decision"], "refetch")

    def test_confirmed_effect_on_other_task_does_not_suppress(self):
        s, d, j = sample(); e = effect(s, d); e["identity"]["issue_id"] = "OTHER"
        self.assertEqual(evaluate(s, d, [e])["decision"], "project")

    def test_unknown_outcome_never_clears_itself(self):
        s, d, j = sample(); j.append(effect(s, d, "unknown"))
        for _ in range(3):
            self.assertEqual(evaluate(s, d, j)["decision"], "refetch")
        self.assertEqual(j[0]["outcome"], "unknown")

    def test_missing_input_fails_closed(self):
        s, d, j = sample()
        for key in tuple(s):
            damaged = dict(s); del damaged[key]
            self.assertEqual(evaluate(damaged, d, j)["decision"], "blocked")


if __name__ == "__main__":
    unittest.main()

"""Pure observational reference model. No persistence, transport, or authority grant.

An owner binding implements evaluate(snapshot, delivery, recorded_effects) and
returns this JSON-compatible shape. Inputs are normalized observations, NOT the
Hermes/OmO APIs. Authentication, durable storage, fresh fetch and serialization
must be supplied and independently qualified by the native implementation.
"""
from copy import deepcopy
import re


def evaluate(snapshot, delivery, recorded_effects):
    """Return an offline projection/obligation; never authorize a remote write."""
    try:
        identity = snapshot["identity"]
        if set(identity) != {"repository_id", "issue_id", "url"}:
            raise ValueError("identity shape")
        if any(not isinstance(v, str) or not v for v in identity.values()):
            raise ValueError("missing identity")
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*", identity["url"]):
            raise ValueError("canonical issue URL required")
        if delivery["identity"] != identity:
            return {"decision": "refetch", "reason": "identity-mismatch"}
        # The owner must obtain this snapshot from its canonical provider fetch.
        # No event/body/local subtask can substitute canonical fields.
        projection = deepcopy({k: snapshot[k] for k in (
            "identity", "dependencies", "pull_requests", "plan_wp", "state",
            "closure_reason", "head", "evidence", "revision")})
        if snapshot["state"] not in ("OPEN", "CLOSED"):
            raise ValueError("unknown canonical state")
        if snapshot["state"] == "OPEN" and snapshot["closure_reason"] is not None:
            raise ValueError("open issue closure reason")
        if snapshot["state"] == "CLOSED" and snapshot["closure_reason"] not in ("COMPLETED", "NOT_PLANNED"):
            raise ValueError("unknown closure reason")
        if snapshot["head"] is not None and not re.fullmatch(r"[0-9a-f]{40}", snapshot["head"]):
            raise ValueError("head required")
        if not isinstance(snapshot["revision"], str) or not snapshot["revision"]:
            raise ValueError("revision required")
        event_id = delivery["delivery_id"]
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("delivery ID required")
        # Unknown effects survive process restart and take precedence over dedup.
        for effect in recorded_effects:
            if effect["identity"] != identity:
                continue
            if effect["outcome"] not in ("confirmed", "unknown"):
                raise ValueError("unknown journal disposition")
            if effect["outcome"] == "unknown":
                return {"decision": "refetch", "reason": "uncertain-effect"}
        if delivery["revision"] != snapshot["revision"]:
            return {"decision": "refetch", "reason": "revision-mismatch"}
        # A recorded confirmed emission binds origin to its delivery identity.
        # An origin string supplied by an issue/event alone is never authority.
        confirmed = [e for e in recorded_effects if e["identity"] == identity
                     and e["outcome"] == "confirmed"
                     and e["delivery_id"] == event_id]
        if confirmed:
            return {"decision": "ignore", "reason": "recorded-delivery"}
        # Correlation is supplied by the native trusted receipt path, not body origin.
        correlation = delivery.get("confirmed_effect_id")
        if correlation and any(e.get("effect_id") == correlation
                and e["identity"] == identity and e["outcome"] == "confirmed"
                for e in recorded_effects):
            return {"decision": "ignore", "reason": "recorded-effect-reflection"}
        if delivery.get("requests_write"):
            return {"decision": "blocked", "reason": "native-serialized-writer-required"}
        evidence = snapshot["evidence"]
        projection["delivered"] = (snapshot["state"] == "CLOSED"
            and snapshot["closure_reason"] == "COMPLETED"
            and snapshot["head"] is not None
            and evidence.get("head") == snapshot["head"]
            and evidence.get("accepted") is True
            and evidence.get("published") is True)
        # This is an observation of supplied evidence, never approval/closure.
        return {"decision": "project", "projection": projection}
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"decision": "blocked", "reason": "invalid-observation"}

"""
FinControl AI - Decision Layer
=================================
Module 6 of the pipeline. Plain Python, no AI: takes the Investigation
Agent's structured output (Module 5) and routes it with a simple
threshold rule. This is deliberately dumb on purpose -- the *judgment*
already happened in Module 5 (grounded in evidence, enforced in code);
this layer just applies a policy threshold to that judgment.

Rule (from the master build prompt):
    confidence >= 0.8            -> AUTO_SUGGESTED
    status == "UNRESOLVED"       -> NEEDS_HUMAN_REVIEW  (always wins)
    otherwise                    -> NEEDS_HUMAN_REVIEW

Run directly for a quick sanity check:
    python -m agents.decision
"""

AUTO_SUGGEST_CONFIDENCE_THRESHOLD = 0.8


def decide(investigation_result: dict) -> dict:
    """Add a `decision` field to one Module 5 output dict."""
    result = dict(investigation_result)

    if result.get("status") == "UNRESOLVED":
        result["decision"] = "NEEDS_HUMAN_REVIEW"
    elif result.get("confidence", 0.0) >= AUTO_SUGGEST_CONFIDENCE_THRESHOLD:
        result["decision"] = "AUTO_SUGGESTED"
    else:
        result["decision"] = "NEEDS_HUMAN_REVIEW"

    return result


def decide_all(investigation_results: list) -> list:
    return [decide(r) for r in investigation_results]


if __name__ == "__main__":
    examples = [
        {"transaction_id": "pay_0001", "status": "RESOLVED", "confidence": 0.91,
         "probable_cause": "platform fee deducted", "evidence_used": ["fee_policy.md"],
         "recommendation": "auto-explain, no action needed"},
        {"transaction_id": "pay_0002", "status": "RESOLVED", "confidence": 0.65,
         "probable_cause": "possible fee, ambiguous magnitude", "evidence_used": ["fee_policy.md"],
         "recommendation": "review before closing"},
        {"transaction_id": "pay_0003", "status": "UNRESOLVED", "confidence": 0.2,
         "probable_cause": None, "evidence_used": [], "recommendation": "route to human"},
    ]
    for r in decide_all(examples):
        print(f"{r['transaction_id']}: status={r['status']} confidence={r['confidence']} -> {r['decision']}")

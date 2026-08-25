"""
FinControl AI - Investigation Agent
=====================================
Module 5 of the pipeline. THE ONLY PLACE CLAUDE IS CALLED IN THIS SYSTEM.
Everything upstream (matching, classification) and downstream (routing)
is deterministic Python -- see reconciliation/ and agents/decision.py.

The agent's job: given one classified exception, its raw records, and
evidence retrieved from rag/retriever.py, produce a grounded explanation
-- or honestly say it cannot. Two independent layers enforce the
"never guess" rule from the master build prompt:
  1. The system prompt instructs the model to cite evidence and return
     UNRESOLVED when evidence is weak or absent.
  2. `_enforce_evidence_rule()` re-checks the model's own output in plain
     Python and forcibly downgrades to UNRESOLVED if the rule was
     violated -- so a bad output from the LLM can never reach a human as
     a confident, unsupported claim.

Run directly for a quick sanity check against one hand-built exception
(requires ANTHROPIC_API_KEY in .env):
    python -m agents.investigator
"""

import os
from typing import List, Literal, Optional

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from rag.retriever import PolicyRetriever, build_query

load_dotenv()

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

# Hard rule from the master build prompt: a RESOLVED status with confidence
# above this bar requires non-empty cited evidence, or it gets downgraded.
CONFIDENCE_REQUIRES_EVIDENCE_ABOVE = 0.5


class MissingAPIKeyError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not configured. See .env.example."""


class InvestigationResult(BaseModel):
    transaction_id: str
    probable_cause: Optional[str] = Field(
        default=None, description="Grounded explanation, or null if evidence is insufficient."
    )
    evidence_used: List[str] = Field(
        default_factory=list, description="Exact source filenames (e.g. 'fee_policy.md') actually relied on."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    recommendation: str
    status: Literal["RESOLVED", "UNRESOLVED"]


SYSTEM_PROMPT = """You are the Investigation Agent inside FinControl AI, a finance \
reconciliation system. You investigate ONE payment/invoice/settlement exception at a \
time, using ONLY the evidence snippets you are given.

Rules you must follow exactly:
1. You may only cite evidence that appears in the "RETRIEVED EVIDENCE" section below. \
Never invent a policy or cite a source that wasn't given to you.
2. Give a `probable_cause` ONLY if the retrieved evidence actually supports it. If the \
evidence is empty, weak, or contradicts a clean explanation, set `probable_cause` to \
null and `status` to "UNRESOLVED" -- do not guess.
3. `confidence` above 0.5 requires at least one entry in `evidence_used`. A confident \
answer with no cited evidence is worse than admitting you don't know -- this is a \
finance system and a wrong guess about money is dangerous.
4. Never perform arithmetic to decide the amounts or dates are correct/incorrect -- \
that has already been done deterministically upstream. Your job is only to explain \
WHY the numbers differ, using policy evidence.
5. Output structured JSON only, matching the required schema exactly."""


def _build_user_prompt(row: dict, evidence: list) -> str:
    evidence_block = "\n\n".join(
        f"[{e['source']}] {e['heading']}\n{e['snippet']}" for e in evidence
    ) or "(none retrieved -- no policy evidence matched this exception)"

    return f"""EXCEPTION RECORD
transaction_id: {row.get('transaction_id')}
exception_type (from rule-based classifier): {row.get('exception_type')}
records_present: {row.get('records_present')}
payment_amt: {row.get('payment_amt')}
invoice_amt: {row.get('invoice_amt')}
settlement_amt: {row.get('settlement_amt')}
difference: {row.get('difference')}
date_gap_days: {row.get('date_gap_days')}
is_duplicate: {row.get('is_duplicate')}

RETRIEVED EVIDENCE
{evidence_block}

Investigate this exception. Respond with the required JSON schema only."""


def _enforce_evidence_rule(result: InvestigationResult, evidence: list) -> InvestigationResult:
    """
    Code-side enforcement of the master prompt's hard rule (never trust the
    prompt alone): reject/downgrade any RESOLVED output with confidence > 0.5
    but no cited evidence, and reject any citation that wasn't actually
    retrieved (a hallucinated source).
    """
    retrieved_sources = {e["source"] for e in evidence}
    cited_but_not_retrieved = [s for s in result.evidence_used if s not in retrieved_sources]

    violates_confidence_rule = (
        result.confidence > CONFIDENCE_REQUIRES_EVIDENCE_ABOVE and not result.evidence_used
    )

    if cited_but_not_retrieved or violates_confidence_rule:
        reason = (
            f"cited unretrieved source(s) {cited_but_not_retrieved}" if cited_but_not_retrieved
            else f"confidence {result.confidence} > {CONFIDENCE_REQUIRES_EVIDENCE_ABOVE} with no cited evidence"
        )
        return InvestigationResult(
            transaction_id=result.transaction_id,
            probable_cause=None,
            evidence_used=[],
            confidence=0.0,
            recommendation=f"NEEDS_HUMAN_REVIEW -- AI output failed validation ({reason}); original claim discarded.",
            status="UNRESOLVED",
        )
    return result


def investigate_exception(
    row: dict,
    retriever: PolicyRetriever = None,
    client: anthropic.Anthropic = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Investigate a single classified exception row (as produced by
    reconciliation/classifier.py, converted to a dict). Returns a dict
    matching InvestigationResult's schema, already validated against the
    evidence-or-UNRESOLVED rule.
    """
    if row.get("exception_type") in (None, "NONE"):
        raise ValueError("investigate_exception() called on a non-exception row")

    retriever = retriever or PolicyRetriever()
    query = build_query(row["exception_type"], row)
    evidence = retriever.retrieve(query)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and client is None:
        raise MissingAPIKeyError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key "
            "(see https://console.anthropic.com/settings/keys)."
        )
    client = client or anthropic.Anthropic(api_key=api_key)

    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(row, evidence)}],
        output_format=InvestigationResult,
    )
    result = response.parsed_output
    result = _enforce_evidence_rule(result, evidence)
    return result.model_dump()


def investigate_all(classified_rows: list, model: str = DEFAULT_MODEL, verbose: bool = True) -> list:
    """
    Investigate every EXCEPTION row in `classified_rows` (a list of dicts,
    e.g. from classified_df.to_dict("records")). Fails fast with
    MissingAPIKeyError before making any calls if the key isn't configured
    -- one clear error beats N confusing per-row failures. Per-row API
    errors (rate limit, network, etc.) are caught individually so one bad
    call doesn't lose the rest of the batch; that row is recorded as
    UNRESOLVED with the error noted in `recommendation`.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise MissingAPIKeyError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key "
            "(see https://console.anthropic.com/settings/keys)."
        )

    client = anthropic.Anthropic(api_key=api_key)
    retriever = PolicyRetriever()
    results = []

    exceptions = [r for r in classified_rows if r.get("exception_type") not in (None, "NONE")]
    for i, row in enumerate(exceptions, 1):
        if verbose:
            print(f"[{i}/{len(exceptions)}] investigating {row['transaction_id']} ({row['exception_type']})...")
        try:
            results.append(investigate_exception(row, retriever=retriever, client=client, model=model))
        except anthropic.APIError as e:
            results.append({
                "transaction_id": row["transaction_id"],
                "probable_cause": None,
                "evidence_used": [],
                "confidence": 0.0,
                "recommendation": f"NEEDS_HUMAN_REVIEW -- AI call failed ({type(e).__name__}: {e}).",
                "status": "UNRESOLVED",
            })
    return results


if __name__ == "__main__":
    demo_row = {
        "transaction_id": "pay_demo",
        "exception_type": "FEE_DEDUCTION",
        "records_present": "PAYMENT,INVOICE,SETTLEMENT",
        "payment_amt": 1000.0,
        "invoice_amt": 1000.0,
        "settlement_amt": 980.0,
        "difference": 20.0,
        "date_gap_days": 2,
        "is_duplicate": False,
    }
    try:
        result = investigate_exception(demo_row)
        import json
        print(json.dumps(result, indent=2))
    except MissingAPIKeyError as e:
        print(f"MissingAPIKeyError: {e}")

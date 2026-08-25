"""
FinControl AI - Investigation Agent
=====================================
Module 5 of the pipeline. THE ONLY PLACE AN LLM IS CALLED IN THIS SYSTEM.
Everything upstream (matching, classification) and downstream (routing)
is deterministic Python -- see reconciliation/ and agents/decision.py.

Uses Groq (free tier) running Llama 3.3 70B, via Groq's OpenAI-compatible
chat completions API with JSON mode. Groq doesn't offer a schema-enforced
structured-output helper (unlike some other providers), so this module
does its own two-layer validation instead of trusting the raw model
output:
  1. The system prompt instructs the model to cite evidence, match an
     exact JSON schema, and return UNRESOLVED when evidence is weak/absent.
  2. In code: the JSON is parsed and validated against a pydantic schema
     (retried once on malformed JSON before giving up honestly), then
     `_enforce_evidence_rule()` re-checks the model's own claims and
     forcibly downgrades to UNRESOLVED if the "never guess" rule was
     violated -- a bad LLM output can never reach a human as a confident,
     unsupported claim.

Run directly for a quick sanity check against one hand-built exception
(requires GROQ_API_KEY in .env -- free at console.groq.com):
    python -m agents.investigator
"""

import json
import os
from typing import List, Literal, Optional

import groq
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from rag.retriever import PolicyRetriever, build_query

load_dotenv()

DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Hard rule from the master build prompt: a RESOLVED status with confidence
# above this bar requires non-empty cited evidence, or it gets downgraded.
CONFIDENCE_REQUIRES_EVIDENCE_ABOVE = 0.5

# How many times to retry the API call if the model returns JSON that
# doesn't parse or doesn't match the schema, before honestly giving up.
MAX_RETRIES = 1


class MissingAPIKeyError(RuntimeError):
    """Raised when GROQ_API_KEY is not configured. See .env.example."""


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


JSON_SCHEMA_DESCRIPTION = """{
  "transaction_id": string,
  "probable_cause": string or null,
  "evidence_used": array of strings (exact source filenames, e.g. "fee_policy.md"),
  "confidence": number between 0 and 1,
  "recommendation": string,
  "status": "RESOLVED" or "UNRESOLVED"
}"""

SYSTEM_PROMPT = f"""You are the Investigation Agent inside FinControl AI, a finance \
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
5. Respond with ONLY a single JSON object, no markdown fences, no commentary before or \
after it, matching exactly this schema:
{JSON_SCHEMA_DESCRIPTION}"""


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

Investigate this exception. Respond with the required JSON object only."""


def _parse_llm_json(raw_text: str) -> dict:
    """
    Groq's JSON mode guarantees syntactically valid JSON, but not schema
    conformance, and models occasionally wrap output in markdown fences
    despite instructions not to -- strip those defensively before parsing.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


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


def _fallback_unresolved(transaction_id: str, reason: str) -> dict:
    """Used whenever we cannot trust the model's output at all (malformed
    JSON after retries, schema violation, API failure) -- fail honest, not silent."""
    return InvestigationResult(
        transaction_id=transaction_id, probable_cause=None, evidence_used=[], confidence=0.0,
        recommendation=f"NEEDS_HUMAN_REVIEW -- {reason}", status="UNRESOLVED",
    ).model_dump()


def investigate_exception(
    row: dict,
    retriever: PolicyRetriever = None,
    client: groq.Groq = None,
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

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key and client is None:
        raise MissingAPIKeyError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key "
            "(free at https://console.groq.com/keys)."
        )
    client = client or groq.Groq(api_key=api_key)

    last_error = None
    for _ in range(MAX_RETRIES + 1):
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(row, evidence)},
            ],
        )
        raw_text = response.choices[0].message.content
        try:
            data = _parse_llm_json(raw_text)
            data["transaction_id"] = row["transaction_id"]  # never trust the model to echo this correctly
            result = InvestigationResult(**data)
            result = _enforce_evidence_rule(result, evidence)
            return result.model_dump()
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            last_error = e
            continue

    return _fallback_unresolved(
        row["transaction_id"], f"AI returned invalid/unparseable output after {MAX_RETRIES + 1} attempts ({last_error})."
    )


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
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise MissingAPIKeyError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key "
            "(free at https://console.groq.com/keys)."
        )

    client = groq.Groq(api_key=api_key)
    retriever = PolicyRetriever()
    results = []

    exceptions = [r for r in classified_rows if r.get("exception_type") not in (None, "NONE")]
    for i, row in enumerate(exceptions, 1):
        if verbose:
            print(f"[{i}/{len(exceptions)}] investigating {row['transaction_id']} ({row['exception_type']})...")
        try:
            results.append(investigate_exception(row, retriever=retriever, client=client, model=model))
        except groq.APIError as e:
            results.append(_fallback_unresolved(row["transaction_id"], f"AI call failed ({type(e).__name__}: {e})."))
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
        print(json.dumps(result, indent=2))
    except MissingAPIKeyError as e:
        print(f"MissingAPIKeyError: {e}")

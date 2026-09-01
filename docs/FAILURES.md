# FAILURES.md — what broke, and how it was fixed

Kept in real time as the system was built, per the master build prompt (Section 6:
*"Keep a running 'what broke' log as you build"*) and the buildathon's explicit
requirement to be able to explain something that broke during development and how
you recovered from it.

Two kinds of entries here: (A) real bugs found organically while writing tests
against real data, and (B) deliberate resilience tests — intentionally broken
inputs, run live, to prove the failure modes the design claims to handle are
actually handled and not just asserted in a docstring.

---

## A. Real bugs found during development

### A1. RAG retrieval quietly picked the wrong policy for routine cases

**What broke:** `rag/retriever.py`'s `build_query()` always included the settlement
date gap in its search query, even for a completely normal transaction (gap = 2
days, i.e. the standard T+2 window). `rag/policies/settlement_policy.md` happens to
describe the normal case in almost the same words: *"...settle... **T+2 business
days**... settlement_date is typically **2 days after** payment_date."*

TF-IDF search doesn't understand meaning, only shared words — so that boilerplate
phrase acted like a magnet, pulling the *"Standard settlement window"* section to
the top of the results for exceptions that had nothing to do with timing.

**How it was found:** not by inspection — a test in `tests/test_investigator.py`
expected a clean `FEE_DEDUCTION` case to come back `RESOLVED`, and it came back
`UNRESOLVED` instead, because `fee_policy.md` wasn't in the retrieved evidence at
all for that case.

**Real before/after** (payment ₹1000, settlement ₹980, normal 2-day gap):

| Rank | Before the fix | After the fix |
|---|---|---|
| 1 | `settlement_policy.md` — *What settlement timing does NOT explain* (0.214) | `fee_policy.md` — *What this looks like in reconciliation* (0.183) |
| 2 | `settlement_policy.md` — *Standard settlement window* (0.202) | `dispute_policy.md` — *Amount mismatches...* (0.132) |
| 3 | `fee_policy.md` — *What this looks like in reconciliation* (0.170) | `fee_policy.md` — *What this does NOT cover* (0.131) |

With the investigator's `top_k=2`, the actually-correct fee policy never made it
into the evidence the AI saw before the fix.

**The fix:** only mention the date gap when it's genuinely anomalous (more than 3
days off T+2) — the same threshold `reconciliation/classifier.py` already uses to
detect real `DATE_MISMATCH` exceptions:
```python
if date_gap is not None and abs(date_gap - 2) > 3:
    parts.append(f"settlement date arrived {date_gap} days after payment, far outside the normal window")
```

**Impact if unfixed:** not a money-safety issue (the evidence-enforcement rule
would have still forced `UNRESOLVED` rather than a wrong confident answer) — but a
real accuracy loss: routine, easily-explainable cases would have been needlessly
routed to human review because retrieval fed the model the wrong document.

Commit: `de427c2` / `607505f`.

---

### A2. A test tried to record an investigation for a transaction that didn't exist yet

**What broke:** `tests/test_db.py::test_write_investigations_stores_evidence_and_audits`
called `write_investigations()` without first calling `write_transactions()`, and hit:
```
sqlite3.IntegrityError: FOREIGN KEY constraint failed
```

**Root cause:** `database/db.py`'s `investigations` table has a real foreign key
into `transactions`. The test was wrong, not the schema — you genuinely cannot have
an AI investigation for a transaction that was never reconciled in the first place.

**The fix:** fixed the test to write the transaction first, matching how `run.py`
and `evaluation.evaluate.run_with_ai()` actually call these functions in order.
No production code changed. Left in this log because it's a good example of a test
catching a *real* invariant rather than getting weakened to pass.

Commit: `4bdf610`.

---

### A3. A boundary-value test bug in the classifier's fee-vs-ambiguous split

**What broke:** a unit test used a ₹5 gap on a ₹1000 payment (0.5% ratio) expecting
`AMBIGUOUS_MINOR_DIFFERENCE`, but got `FEE_DEDUCTION` — because 0.5% is exactly
`FEE_RATIO_MIN`, the classifier's own documented lower bound for a fee-shaped
difference.

**The fix:** the classifier was correct; the test picked a boundary value instead
of a clearly-inside-the-range one. Changed the test to a ₹2 gap (0.2% ratio,
unambiguously below the fee floor).

Commit: `85d85f1`.

---

## B. Deliberate resilience tests (run live, not just described)

### B1. Missing `GROQ_API_KEY` — full pipeline, no `.env` configured

```
$ unset GROQ_API_KEY ANTHROPIC_API_KEY
$ python run.py --skip-dashboard --seed 99

[1/6] Generating synthetic dataset (seed=99)...
...
[2/6] Reconciling + classifying...
      91 transactions: 35 MATCHED, 56 EXCEPTION
[3/6] Skipping AI investigation: GROQ_API_KEY is not set.
      Copy .env.example to .env and add a key to enable Module 5/6.
      The dashboard will still show all reconciliation/classification results.
[4/6] Writing to database...
      Database updated.
[5/6] Evaluating against ground truth...
============================================================
FinControl AI - Evaluation Report
============================================================
Records:                 91 (35 expected matched, 56 expected exceptions)
Reconciliation match rate: 100.00%
Exception detection:     precision=100.00%  recall=100.00%  f1=100.00%
...
AI resolution: N/A (run with investigator+decision output; see evaluate.py --with-ai)
============================================================
```
**No crash, no stack trace.** The pipeline detects the missing key once, up front
(`agents/investigator.py`'s `MissingAPIKeyError`), prints exactly what to do about
it, and still completes reconciliation, classification, storage, and evaluation —
because those don't need AI at all. The dashboard stays fully usable with the
deterministic results while `GROQ_API_KEY` is absent.

### B2. Malformed LLM JSON — the model returns non-JSON garbage on every attempt

Simulated with a mocked client (reproducible without live API calls or waiting on
a real model to misbehave):

```
=== Scenario: model returns non-JSON garbage on EVERY attempt ===

Groq API was called 2 times (1 initial attempt + 1 retry, per MAX_RETRIES=1)

Final result handed to the decision layer / database:
{
  "transaction_id": "pay_broken_demo",
  "probable_cause": null,
  "evidence_used": [],
  "confidence": 0.0,
  "recommendation": "NEEDS_HUMAN_REVIEW -- AI returned invalid/unparseable output after 2 attempts (Expecting value: line 1 column 1 (char 0)).",
  "status": "UNRESOLVED"
}

✅ Confirmed: no crash, no fabricated answer -- honest UNRESOLVED after exhausting retries.
```
`agents/investigator.py` retries once on a JSON parse/schema failure, then falls
back to an honest `UNRESOLVED` result rather than crashing the batch or letting a
`json.JSONDecodeError` propagate and kill every remaining exception in the run.
This exact scenario is also covered by
`tests/test_investigator.py::test_investigate_exception_gives_up_honestly_after_retries_exhausted`.

Worth noting: this failure mode became *real*, not hypothetical, the moment the
Investigation Agent was switched from Claude to Groq — Anthropic's structured-
output feature guarantees schema-valid JSON; Groq's JSON mode only guarantees
syntactically valid JSON, not that it matches our schema. The retry/fallback logic
above is what makes that provider swap safe.

### B3. Empty input CSV — zero transactions to reconcile

```
$ python -c "
from reconciliation.matcher import load_data
try:
    load_data('/tmp/empty_data')
except ValueError as e:
    print(f'ValueError (caught, not crashed): {e}')
"

ValueError (caught, not crashed): payments.csv at /tmp/empty_data/payments.csv has
no rows -- cannot reconcile an empty batch.
```
`reconciliation/matcher.py`'s `load_data()` checks each CSV for rows and raises a
specific, actionable `ValueError` naming the exact file — instead of pandas
silently reconciling zero transactions and every downstream metric (match rate,
precision, throughput) reporting `0/0` or `NaN` with no explanation. Same pattern
for a missing file entirely (`FileNotFoundError`, tested in
`tests/test_matcher.py::test_missing_file_raises_clear_error`).

---

## What this adds up to

Every failure mode the design claims to handle gracefully — missing credentials,
an untrustworthy LLM response, malformed/empty input — was actually triggered and
observed, not just asserted. Section A is proof the test suite catches real bugs
(not just wraps already-correct code); Section B is proof the deterministic
guardrails around the one AI call in this system (Module 5) hold up when that call
misbehaves in the ways it realistically can.

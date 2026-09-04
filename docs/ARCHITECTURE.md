# Architecture

FinControl AI is 9 small modules chained by `run.py`, split cleanly into two
zones: everything that touches numbers or matching is deterministic Python;
exactly one hop is an LLM call, and its output is validated in code before
anything downstream trusts it.

```
 DETERMINISTIC ZONE (no AI)                          AI ZONE (one call)
┌──────────────┐   ┌──────────┐   ┌──────────┐      ┌──────────────┐   ┌──────────┐
│ 1. Generate  │──▶│ 2. Match │──▶│ 3.Classify│─────▶│ 5. Investigate│──▶│ 6. Decide│
│  synthetic   │   │(matcher) │   │(classifier)│     │  (Groq LLM)   │   │(threshold)│
│    data      │   └──────────┘   └──────────┘      └──────┬───────┘   └────┬─────┘
└──────────────┘                       ▲                    │                │
                                        │            ┌───────┴───────┐        │
                                        │             │ 4. RAG        │        │
                                        │             │  retriever    │        │
                                        │             │ (evidence)    │        │
                                        │             └───────────────┘        │
                                        │                                      ▼
                                        │                              ┌──────────────┐
                                        └──────────────────────────────│ 7. Store +   │
                                                                        │  audit log   │
                                                                        └──────┬───────┘
                                                                               │
                                              ┌────────────────────────────────┼──────────┐
                                              ▼                                ▼          ▼
                                     ┌──────────────┐                ┌──────────────┐  ┌────────┐
                                     │ 8. Dashboard  │                │ 9. Evaluate  │  │(human) │
                                     │ human approval│◀───────────────│ vs ground truth│  │decision│
                                     └──────────────┘                └──────────────┘  └────────┘
```

## Module by module

### 1. Synthetic Data Generator — `data/generate_data.py`
- **Input:** none (fixed seed=42, override with `--seed`).
- **Processing:** generates 91 transactions across 12 categories, each with a
  known ground-truth answer.
- **Output:** `data/synthetic/{payments,invoices,settlements,ground_truth}.csv`.

### 2. Reconciliation Engine — `reconciliation/matcher.py`
- **Input:** the 3 source CSVs.
- **Processing:** outer-joins on `transaction_id`; compares amounts (0.01
  tolerance) and dates (T+2 ± 3 day window); flags duplicate charges via
  `(amount, merchant, method, date)` grouping. Pure pandas — **no AI**.
- **Output:** one row per transaction — `status`, amounts, `difference`,
  `records_present`, `date_gap_days`, `is_duplicate`.

### 3. Exception Classifier — `reconciliation/classifier.py`
- **Input:** `EXCEPTION` rows from Module 2.
- **Processing:** if/else rules only, in priority order — duplicate → missing
  invoice/settlement → date mismatch → full/partial refund → amount mismatch →
  fee deduction → ambiguous minor difference → unclassified. **No AI.**
- **Output:** an `exception_type` per exception row. See
  `docs/EVALUATION.md` for why this is deliberately imperfect on the fuzzy cases.

### 4. RAG / Evidence Retriever — `rag/retriever.py` + `rag/policies/*.md`
- **Input:** an exception's type + its actual numbers (via `build_query()`) and
  4 short markdown policy docs (fee, refund, settlement timing, dispute/duplicate).
- **Processing:** pure-stdlib TF-IDF cosine similarity over markdown sections
  (no embeddings/vector DB — not needed at this scale). Returns `[]` when
  nothing clears the similarity floor — a legitimate result the investigator
  must treat as "no evidence," not an error.
- **Output:** ranked `{source, heading, snippet, score}` list.

### 5. Investigation Agent — `agents/investigator.py` (the only AI call)
- **Input:** one classified exception + its evidence (Module 4).
- **Processing:** calls Groq (`openai/gpt-oss-120b`) with JSON-mode and a strict system
  prompt. Parses the response into a pydantic `InvestigationResult`
  (`probable_cause`, `evidence_used`, `confidence`, `recommendation`, `status`),
  retrying once on malformed JSON before honestly returning `UNRESOLVED`. Then
  `_enforce_evidence_rule()` re-checks the parsed result in plain Python: any
  `RESOLVED` claim with confidence > 0.5 and no cited evidence, or citing a
  source that was never actually retrieved, is **forcibly downgraded** to
  `UNRESOLVED` — this is enforced in code, not just requested in the prompt.
- **Output:**
```json
{
  "transaction_id": "pay_0007",
  "probable_cause": "platform fee deducted at settlement",
  "evidence_used": ["fee_policy.md"],
  "confidence": 0.91,
  "recommendation": "auto-explain, no action needed",
  "status": "RESOLVED"
}
```

### 6. Decision Layer — `agents/decision.py`
- **Input:** Module 5 output.
- **Processing:** plain Python threshold — `confidence >= 0.8` → `AUTO_SUGGESTED`;
  `status == "UNRESOLVED"` always wins → `NEEDS_HUMAN_REVIEW`, regardless of
  confidence; otherwise `NEEDS_HUMAN_REVIEW`. **No AI.**
- **Output:** the same dict with a `decision` field added.

### 7. Storage + Audit Log — `database/db.py`
- **Input:** outputs of every module above, plus dashboard actions.
- **Processing:** SQLite (`fincontrol.db`), 4 tables — `transactions`,
  `investigations` (FK → `transactions`), `human_decisions`, `audit_log`. Every
  write to the first three also appends a row to `audit_log` (timestamp, actor,
  action, evidence reference).
- **Output:** `fincontrol.db`, queryable by the dashboard.

### 8. Human Approval — `app/pages/3_investigation.py`
- **Input:** one case's full trail from Module 7.
- **Processing:** operator views the mismatch, retrieved evidence, AI reasoning,
  and clicks Approve / Reject / Mark Unresolved with an optional note. **All
  actions are labeled SIMULATED — no real money moves.**
- **Output:** a `human_decisions` row + an `audit_log` entry.

### 9. Evaluation — `evaluation/evaluate.py`
- **Input:** the system's own output + `ground_truth.csv`.
- **Processing:** compares predicted vs. expected status/type/resolution; computes
  match rate, precision/recall/F1, exception-type accuracy, AI resolution
  accuracy, false-positive rate, false-auto-resolve count, unresolved counts
  (system vs. true), and throughput.
- **Output:** printed report + `evaluation/results.json` — the single source of
  truth every number in the README/dashboard traces back to.

### 10. Dashboard — `app/dashboard.py` + `app/pages/*.py`
Streamlit, 6 pages: **Overview**, **Reconciliation Table**, **Exception
Investigation** (Module 8 lives here), **Exception Queue**, **Audit Log**,
**Evaluation**. Every page reads from `fincontrol.db` / `results.json` — nothing
is hand-typed.

## Design principles

1. **The LLM is a narrow specialist, not a generalist.** It is called exactly
   once per exception, with a fixed schema, and never for matching or
   arithmetic — those are 100% deterministic Python.
2. **Trust is enforced twice: prompt and code.** The system prompt instructs
   the model to refuse when unsure; `_enforce_evidence_rule()` re-validates that
   claim independently, so a bad model output can never reach a human as a
   confident, unsupported answer.
3. **Every metric traces to a file.** `evaluation/results.json` is the only
   source for numbers shown anywhere — no hand-typed claims.
4. **Fail honest, not silent.** Missing API key, malformed LLM JSON, and empty
   input CSVs are all caught with a specific, actionable message rather than a
   stack trace or (worse) a silently wrong result — see `docs/FAILURES.md`.

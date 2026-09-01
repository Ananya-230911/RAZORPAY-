# Evaluation

Methodology and current results for `evaluation/evaluate.py` (Module 9). Every
number below was produced by running the code in this repo against
`data/synthetic/ground_truth.csv` — reproduce any of it with the commands in
each section.

## Methodology

`data/generate_data.py` (seed=42, reproducible) generates 91 transactions where
the *correct answer is known in advance* — `ground_truth.csv` records the
expected `status`, `exception_type`, `resolution`, and a human-readable reason
for every one. `evaluate.py` never asks "does this look right?" — it directly
compares the system's output to that known answer.

```bash
python -m evaluation.evaluate            # deterministic metrics (Modules 2, 3, 9)
python -m evaluation.evaluate --with-ai  # + AI resolution metrics (Modules 5, 6, 9; needs GROQ_API_KEY)
```

## Metrics defined

| Metric | Definition |
|---|---|
| **Reconciliation match rate** | Fraction of all 91 transactions where predicted `status` (MATCHED/EXCEPTION) equals the ground-truth `status`. |
| **Precision / recall / F1** | Treating `EXCEPTION` as the positive class: precision = TP/(TP+FP), recall = TP/(TP+FN), across the same 91 transactions. |
| **False positive rate** | Of the transactions that were truly clean matches, how many did the system wrongly flag as exceptions: FP/(FP+TN). |
| **Exception-type accuracy** | Of the true exceptions, how many did Module 3's `exception_type` label match the ground-truth `expected_exception_type` exactly. |
| **AI resolution accuracy** | Of the exceptions the AI marked `RESOLVED`, how many had an `exception_type` matching ground truth (i.e., the AI resolved a case the classifier had actually tagged correctly). |
| **False auto-resolve count** | AI said `RESOLVED` but the underlying `exception_type` didn't match ground truth — a confident answer built on a wrong premise. This is the single most important number in the whole system: it's what the evidence-enforcement rule exists to keep at zero. |
| **System vs. true UNRESOLVED count** | How many exceptions the AI honestly refused to resolve, vs. how many the dataset actually designed to be unresolvable. |
| **Throughput** | Total records ÷ wall-clock seconds for the timed stage (deterministic-only for `evaluate()`, full pipeline including AI calls for `run_with_ai()`). |

## Current results (deterministic stage)

From `evaluation/results.json`, 91 records (35 expected `MATCHED`, 56 expected `EXCEPTION`):

| Metric | Value |
|---|---|
| Match rate | 100% |
| Precision | 100% |
| Recall | 100% |
| F1 | 100% |
| False positive rate | 0% |
| Exception-type accuracy | 94.64% (53/56) |
| Throughput | ~700–1300 records/sec (varies by run/machine — this is a small dataset, not a load test) |

**Why 100% match rate is real, not a data artifact:** the matcher's MATCHED/
EXCEPTION decision is computed purely from amount/date/presence comparisons — it
has no knowledge of `ground_truth.csv` at all. A 100% score means the
deterministic logic and the generator's category design agree perfectly, which
is expected: `matcher.py` was built to detect exactly the signals
`generate_data.py` deliberately introduces (missing records, amount deltas, date
drift, duplicate charges).

**Why exception-type accuracy is 94.64%, not 100%, and why that's correct:**
the 3 misses are exactly the 3 `UNRESOLVED`-category rows in the ground truth.
`generate_data.py` builds those rows to have *no* clean fee/refund/date
explanation on purpose — the classifier (Module 3) is rule-based and has no
`UNRESOLVED` tag to assign; it will always land on something like
`UNCLASSIFIED_DIFFERENCE` or, by chance, a percentage that happens to overlap
`PARTIAL_REFUND`'s range. That's not a classifier bug — it's the exact gap
Module 5 (the AI investigator) exists to close honestly, by looking at the
actual evidence and correctly returning `UNRESOLVED` for these cases rather than
forcing a label. See `docs/FAILURES.md` A1 for a related, previously-real bug in
how evidence was retrieved for these ambiguous cases.

## AI resolution metrics

Not populated in this repo's committed `results.json` because generating them
calls the live Groq API and needs `GROQ_API_KEY`. To produce them yourself:

```bash
cp .env.example .env   # add your key — free at console.groq.com/keys
python -m evaluation.evaluate --with-ai
```

This adds `resolved_count`, `resolution_accuracy`, `system_unresolved_count`,
`true_unresolved_count`, and `false_auto_resolve_count` to `results.json` and to
the dashboard's Overview and Evaluation pages automatically — no code changes
needed, since both already render `ai_resolution` conditionally.

**What "good" looks like here:** `false_auto_resolve_count == 0` matters far more
than a high `resolution_accuracy` number. A system that resolves fewer cases but
never resolves one wrongly with high confidence is the entire point of this
design — see the "honest exception list" framing in the buildathon's own bar for
this track.

## Known limitations of these numbers

- 91 records is small by design (the buildathon's stated minimum is 50+) — these
  precision/recall numbers describe behavior on *this* synthetic distribution,
  not a claim about arbitrary real-world reconciliation data.
- The classifier's fee-deduction vs. ambiguous-minor-difference boundary is
  genuinely ambiguous by construction (see `reconciliation/classifier.py`'s
  module docstring) — a small number of misclassifications there are expected
  and intentional, not something to chase to 100%.
- Throughput numbers are wall-clock on whatever machine ran the pipeline, not a
  controlled benchmark — useful as a sanity check ("is this obviously broken"),
  not as a performance claim.

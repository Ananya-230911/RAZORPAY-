# FinControl AI

**AI Finance Controller** — Razorpay AI Buildathon 2026, Track 4

Deterministic Python reconciles the books. An AI investigator, grounded only in
retrieved policy evidence, looks at the exceptions that genuinely need judgment —
and honestly says **UNRESOLVED** instead of guessing when the evidence isn't
there.

## The problem

Reconciliation tools today either match records reliably but dump every mismatch
on a human with zero explanation, or use AI to "explain" mismatches ungrounded —
producing confident-sounding but unverified reasons, which is dangerous with
money. FinControl AI does deterministic matching (100% reliable plain code) for
the math, and uses an LLM only to investigate exceptions that genuinely need
judgment — grounding every explanation in retrieved evidence, and honestly
reporting `UNRESOLVED` when it cannot prove a cause, instead of guessing.

**Target user:** a finance ops analyst reconciling payment/invoice/settlement
records who is currently doing this by hand, or with a tool that doesn't explain
the messy cases.

## Core principle (enforced in code, not just docs)

- **Deterministic Python** for: matching, amount/date comparison, duplicate
  detection, classification, every metric.
- **LLM** for: investigating exceptions, reading policy evidence, explaining
  probable cause, producing a confidence score, and refusing to answer
  (`UNRESOLVED`) when evidence is insufficient.
- The LLM never does arithmetic or matching, and it never gets to guess a cause
  without citing retrieved evidence — a confidence-above-0.5 claim with no cited
  evidence is forcibly downgraded to `UNRESOLVED` in code
  (`agents/investigator.py::_enforce_evidence_rule`), independent of whatever the
  model said.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full module-by-module
design, [`docs/EVALUATION.md`](docs/EVALUATION.md) for methodology and current
results, [`docs/SECURITY.md`](docs/SECURITY.md) for data-handling and API-key
practices, and [`docs/FAILURES.md`](docs/FAILURES.md) for real bugs found (and
fixed) during development plus three deliberately-triggered failure scenarios.

## Results (from `evaluation/results.json` — never hand-typed)

On the 91-record synthetic batch (35 expected clean matches, 56 expected
exceptions):

| Metric | Value |
|---|---|
| Reconciliation match rate | **100%** |
| Exception detection (precision / recall / F1) | **100% / 100% / 100%** |
| False positive rate | **0%** |
| Exception-type classification accuracy | **94.6%** (53/56) |
| Throughput | **~700–1300 records/sec** (deterministic stage; varies by run/machine) |

AI-resolution metrics (resolution accuracy, false auto-resolve rate, system vs.
true `UNRESOLVED` counts) require `GROQ_API_KEY` — see below — and are populated
by `python -m evaluation.evaluate --with-ai`.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python | Data + AI ecosystem |
| Data processing | pandas | Deterministic matching engine |
| LLM | [Groq](https://groq.com) (`openai/gpt-oss-120b`), free tier | Only one agentic hop needed; JSON-mode + code-side schema validation |
| RAG | Pure-stdlib TF-IDF over local markdown | 4 short policy docs don't need a vector DB for this scale |
| DB | SQLite | Zero setup, file-based, full audit trail |
| Dashboard | Streamlit | Fast to build, good for a demo |
| Secrets | `.env` + `python-dotenv` | Never hardcoded |

No Razorpay Test Mode API integration (records are reconciled, not paid) and no
MCP — neither is required for this track.

## Project structure

```
data/                   Synthetic dataset generator + generated CSVs
reconciliation/         matcher.py (Module 2), classifier.py (Module 3) — no AI
rag/                     4 policy docs + TF-IDF retriever (Module 4) — no AI
agents/                  investigator.py (Module 5, the only AI call), decision.py (Module 6) — no AI
database/                SQLite storage + audit log (Module 7)
evaluation/              evaluate.py (Module 9) + results.json
app/                     Streamlit dashboard, 6 pages (Module 8+10)
tests/                   Unit tests for every module above
docs/                    ARCHITECTURE.md, EVALUATION.md, SECURITY.md, FAILURES.md
run.py                   One command: generate -> reconcile -> classify -> investigate -> decide -> store -> evaluate -> dashboard
```

## Setup

```bash
git clone https://github.com/Ananya-230911/RAZORPAY-.git
cd RAZORPAY-
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# edit .env, add GROQ_API_KEY (free at https://console.groq.com/keys)
```

## Usage

```bash
python run.py                        # full pipeline, launches the dashboard
python run.py --skip-dashboard       # pipeline only, print the report, exit
python run.py --skip-ai              # skip the AI investigation step
python run.py --seed 7               # regenerate the synthetic dataset first

python -m pytest tests/ -v           # all tests
python -m evaluation.evaluate            # deterministic metrics only
python -m evaluation.evaluate --with-ai  # + AI resolution metrics (needs GROQ_API_KEY)
```

Without `GROQ_API_KEY` set, the pipeline does **not** crash — it prints a clear
message, skips the AI step, and still populates the database and dashboard from
reconciliation + classification alone. See `docs/FAILURES.md` for this
demonstrated live.

## Dataset

`data/generate_data.py` (seed=42 by default, reproducible) generates 91
transactions across 12 categories — clean matches, fee deductions, partial/full
refunds, amount mismatches, missing invoices/settlements, duplicate charges, date
mismatches, unknown transactions, ambiguous minor differences, and genuinely
unresolvable cases — each with a known ground-truth answer in
`data/synthetic/ground_truth.csv`, so every metric above is a real comparison,
not a guess.

## Limitations (stated honestly)

- The rule-based classifier (Module 3) is a first-pass heuristic, not a perfect
  oracle: fee-deduction-shaped and genuinely-ambiguous small differences overlap
  by design in the synthetic data — see `docs/EVALUATION.md` for why the 94.6%
  number is exactly right and not a bug.
- The TF-IDF retriever has no semantic understanding — it matches shared words,
  not meaning. Works well at this scale (4 short docs) but wouldn't scale to a
  large policy library without upgrading to embeddings.
- SQLite has no concurrent-write protection or auth — fine for a local demo, not
  for a multi-user production deployment.
- Every dashboard action is explicitly SIMULATED. Nothing here calls Razorpay or
  moves real money.

## Buildathon deliverables

- [x] Public GitHub repo, clean structure, working `run.py`
- [x] README.md (this file), ARCHITECTURE.md, EVALUATION.md, SECURITY.md
- [x] Real, reproducible metrics in `evaluation/results.json`
- [x] `docs/FAILURES.md` — real bugs + deliberate break tests, with captured output


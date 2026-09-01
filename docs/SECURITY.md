# Security

## No real financial actions, anywhere

This system never calls the Razorpay API and never moves real money. Every
action a human can take in the dashboard (`app/pages/3_investigation.py`) —
Approve, Reject, Mark Unresolved — is explicitly labeled **SIMULATED / TEST
MODE** in the UI and only ever writes to the local `fincontrol.db` file. This
is stated once here and enforced in three places: the dashboard's persistent
warning banner (`app/common.py::simulated_banner()`), the button label itself
("Record decision (SIMULATED)"), and the success message after submitting.

## API keys

- The only external credential this system uses is `GROQ_API_KEY` (Groq's LLM
  API, for `agents/investigator.py` — the one AI call in the whole system).
- Keys are read from a `.env` file via `python-dotenv`, never hardcoded.
  `.env.example` documents the required variable with a placeholder value;
  `.env` itself is listed in `.gitignore` and was never committed (verified —
  see below).
- If the key is missing, the system fails clearly (`MissingAPIKeyError` with an
  actionable message) rather than silently proceeding or crashing with an
  opaque stack trace. See `docs/FAILURES.md` B1 for this demonstrated live.
- No key rotation, secrets manager, or vault integration is implemented — this
  is a local/demo-scale project. For a production deployment, the key should
  move to a proper secrets manager rather than a local `.env` file.

## What data leaves the system

The only outbound network call carrying application data is to Groq's chat
completions API (`agents/investigator.py`), and only for exceptions that the
deterministic classifier (Module 3) has already flagged. What's sent:
- The exception's classified type, amounts, dates, and presence flags (from
  `reconciliation/matcher.py` + `classifier.py`).
- The retrieved policy evidence snippets (from `rag/retriever.py` — these are
  the project's own markdown files, not third-party or customer content).

**No real customer, card, or payment-instrument data ever exists in this
system.** All data comes from `data/generate_data.py`, a synthetic generator
with a fixed random seed — there is no path by which real Razorpay transaction
data could flow through this pipeline as currently built.

## LLM output is never trusted blindly

Two independent layers, because a prompt instruction alone is not a security
control:

1. **Schema validation.** The model's JSON response is parsed and validated
   against a pydantic schema (`InvestigationResult`) before anything downstream
   sees it. Malformed JSON is retried once, then fails to an honest
   `UNRESOLVED` result rather than propagating a parse error or fabricating a
   result — demonstrated live in `docs/FAILURES.md` B2.
2. **Evidence enforcement, in code.** `_enforce_evidence_rule()` independently
   re-checks the model's own claim: a `RESOLVED` status with confidence > 0.5
   and no cited evidence, or a citation to a policy source that was never
   actually retrieved (a hallucinated source), is forcibly downgraded to
   `UNRESOLVED`. This runs regardless of what the system prompt asked for —
   the prompt is a request, this check is the actual guarantee.

## Local storage

- `fincontrol.db` (SQLite) has no authentication, encryption at rest, or
  concurrent-write protection — appropriate for a local single-user demo, not
  for a shared or production deployment. It is `.gitignore`d and was never
  committed.
- The audit log (`audit_log` table) is append-only in practice (the code never
  issues an `UPDATE`/`DELETE` against it) but nothing at the database layer
  enforces immutability — a determined local user with direct DB access could
  edit it. Acceptable for a demo audit trail; would need a proper
  append-only/WORM store for a real compliance use case.

## Dependency & environment hygiene

- Dependencies are pinned to minimum versions in `requirements.txt`, not exact
  pins — reasonable for active development, should move to exact/locked
  versions (e.g. `pip-compile` or a lockfile) before any production use.
- No secrets, API keys, or database files are present in this repository —
  verified before every push:
  ```bash
  git ls-files | grep -iE '\.env$|\.db$|\.venv'   # → no output
  ```

## Out of scope for this project (stated explicitly, not silently skipped)

- No authentication/authorization on the dashboard — anyone with local access
  to the running Streamlit process can approve/reject cases (simulated only).
- No rate limiting on the Groq API calls beyond what the SDK's default retry
  behavior provides.
- No input sanitization beyond what pandas/SQLite parameterized queries provide
  by default (all SQL in `database/db.py` uses parameterized `?` placeholders —
  no string-formatted SQL anywhere in this codebase).

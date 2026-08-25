"""
FinControl AI - RAG / Evidence Retriever
==========================================
Module 4 of the pipeline. Simple TF-IDF retrieval over the local markdown
policy docs in rag/policies/ -- no ChromaDB, no embeddings API, pure
Python stdlib. That's a deliberate MVP choice (see master build prompt
Section 2, Module 4), not a corner cut: the point is that evidence
retrieval must be transparent and auditable, and a handful of short
policy docs don't need a vector DB.

Input:  a natural-language query (built from an exception's classified
        type + its numbers) + the markdown files in rag/policies/
Output: list of {source, heading, snippet, score} ranked by TF-IDF
        cosine similarity. An empty list means "no supporting evidence
        found" -- callers (agents/investigator.py) must treat that as a
        signal to return UNRESOLVED, not to guess.

Run directly for a quick sanity check:
    python -m rag.retriever
"""

import math
import os
import re
from collections import Counter

DEFAULT_POLICY_DIR = os.path.join(os.path.dirname(__file__), "policies")

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "of", "at", "by", "for", "with", "about",
    "to", "from", "in", "on", "as", "this", "that", "these", "those",
    "it", "its", "not", "no", "does", "do", "did", "has", "have", "had",
    "can", "should", "would", "could", "than", "then", "so", "into",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _split_into_sections(markdown_text: str, source: str) -> list:
    """Split a markdown file on '##' headings into {source, heading, text} chunks."""
    sections = []
    current_heading = source
    current_lines = []

    def flush():
        text = "\n".join(current_lines).strip()
        if text:
            sections.append({"source": source, "heading": current_heading, "text": text})

    for line in markdown_text.splitlines():
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            current_lines = []
        elif line.startswith("# "):
            continue  # top-level title, not a retrievable section on its own
        else:
            current_lines.append(line)
    flush()
    return sections


class PolicyRetriever:
    """Loads all markdown policy docs and answers TF-IDF similarity queries."""

    def __init__(self, policy_dir: str = DEFAULT_POLICY_DIR):
        self.policy_dir = policy_dir
        self.sections = self._load_sections()
        self._doc_freq, self._n_docs = self._build_doc_freq()
        self._section_vectors = [self._tfidf_vector(_tokenize(s["text"])) for s in self.sections]

    def _load_sections(self) -> list:
        if not os.path.isdir(self.policy_dir):
            raise FileNotFoundError(f"Policy directory not found: {self.policy_dir}")
        sections = []
        for fname in sorted(os.listdir(self.policy_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(self.policy_dir, fname)
            with open(path, "r") as f:
                text = f.read()
            sections.extend(_split_into_sections(text, fname))
        if not sections:
            raise ValueError(f"No policy sections found in {self.policy_dir} -- cannot retrieve evidence.")
        return sections

    def _build_doc_freq(self):
        df = Counter()
        for s in self.sections:
            for term in set(_tokenize(s["text"])):
                df[term] += 1
        return df, len(self.sections)

    def _idf(self, term: str) -> float:
        # +1 smoothing so an unseen term doesn't blow up to log(0) or divide by zero.
        return math.log((1 + self._n_docs) / (1 + self._doc_freq.get(term, 0))) + 1

    def _tfidf_vector(self, tokens: list) -> dict:
        if not tokens:
            return {}
        tf = Counter(tokens)
        max_tf = max(tf.values())
        return {term: (0.5 + 0.5 * count / max_tf) * self._idf(term) for term, count in tf.items()}

    @staticmethod
    def _cosine(a: dict, b: dict) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def retrieve(self, query: str, top_k: int = 2, min_score: float = 0.05) -> list:
        """
        Return up to top_k policy sections most relevant to `query`, each
        above min_score cosine similarity. Returns [] if nothing clears the
        bar -- that's a legitimate, expected result, not a bug.
        """
        query_vec = self._tfidf_vector(_tokenize(query))
        scored = []
        for section, vec in zip(self.sections, self._section_vectors):
            score = self._cosine(query_vec, vec)
            if score >= min_score:
                scored.append({
                    "source": section["source"],
                    "heading": section["heading"],
                    "snippet": section["text"].strip(),
                    "score": round(score, 4),
                })
        scored.sort(key=lambda s: s["score"], reverse=True)
        return scored[:top_k]


def build_query(exception_type: str, row: dict) -> str:
    """
    Build a natural-language retrieval query from a classified exception row
    (as produced by reconciliation/classifier.py). Keeps the query grounded
    in the actual numbers rather than just the category label, so retrieval
    quality doesn't collapse to a hardcoded type->file lookup table.
    """
    parts = [exception_type.replace("_", " ").lower()]

    payment_amt = row.get("payment_amt")
    settlement_amt = row.get("settlement_amt")
    invoice_amt = row.get("invoice_amt")
    date_gap = row.get("date_gap_days")

    if payment_amt is not None and settlement_amt is not None:
        diff = payment_amt - settlement_amt
        ratio = (diff / payment_amt * 100) if payment_amt else 0
        parts.append(f"payment amount {payment_amt} settlement amount {settlement_amt} "
                      f"difference {round(diff, 2)} which is {round(ratio, 2)} percent of payment")
    if invoice_amt is not None and payment_amt is not None and invoice_amt != payment_amt:
        parts.append(f"invoice amount {invoice_amt} differs from payment amount {payment_amt}")
    if date_gap is not None:
        parts.append(f"settlement date gap {date_gap} days after payment")
    if row.get("records_present"):
        parts.append(f"records present {row['records_present']}")
    if row.get("is_duplicate"):
        parts.append("duplicate charge same amount merchant method date")

    return " ".join(parts)


if __name__ == "__main__":
    retriever = PolicyRetriever()
    print(f"Loaded {len(retriever.sections)} policy sections from {retriever.policy_dir}")
    print()

    demo_queries = [
        ("FEE_DEDUCTION", {"payment_amt": 1000.0, "settlement_amt": 980.0, "invoice_amt": 1000.0}),
        ("PARTIAL_REFUND", {"payment_amt": 1000.0, "settlement_amt": 600.0, "invoice_amt": 1000.0}),
        ("MISSING_INVOICE", {"records_present": "PAYMENT,SETTLEMENT"}),
        ("UNCLASSIFIED_DIFFERENCE", {"payment_amt": 1000.0, "settlement_amt": 550.0, "invoice_amt": 1030.0}),
    ]
    for exc_type, row in demo_queries:
        query = build_query(exc_type, row)
        results = retriever.retrieve(query)
        print(f"[{exc_type}] query: {query}")
        if not results:
            print("  -> NO EVIDENCE FOUND")
        for r in results:
            print(f"  -> {r['source']} / {r['heading']} (score={r['score']})")
        print()

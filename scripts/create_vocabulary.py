#!/usr/bin/env python3
"""Create corpus vocabulary with total and document frequencies."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON on {path}:{line_number}") from error
    return records


def compute_vocabulary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_counts: Counter[str] = Counter()
    document_frequency: Counter[str] = Counter()
    issue_count = len(records)

    for record in records:
        tokens = record.get("tokens") or []
        total_counts.update(tokens)
        document_frequency.update(set(tokens))

    vocabulary = []
    for rank, (token, total_count) in enumerate(total_counts.most_common(), start=1):
        doc_freq = document_frequency[token]
        vocabulary.append(
            {
                "rank": rank,
                "token": token,
                "total_count": total_count,
                "document_frequency": doc_freq,
                "percent_of_documents": round((doc_freq / issue_count) * 100, 2) if issue_count else 0,
            }
        )
    return vocabulary


def write_vocabulary(path: Path, vocabulary: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "token",
        "total_count",
        "document_frequency",
        "percent_of_documents",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(vocabulary)


def read_candidates(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def top_candidate_rows(
    candidates: list[dict[str, str]],
    *,
    decision: str | None = None,
    source: str | None = None,
    has_candidate_class: bool | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    selected = []
    for row in candidates:
        if decision is not None and row.get("decision") != decision:
            continue
        if source is not None and row.get("source") != source:
            continue
        if has_candidate_class is not None:
            present = bool(row.get("candidate_class"))
            if present != has_candidate_class:
                continue
        selected.append(
            {
                "token": row.get("token"),
                "total_count": int(row.get("total_count") or 0),
                "document_frequency": int(row.get("document_frequency") or 0),
                "percent_documents": float(row.get("percent_documents") or 0),
                "candidate_class": row.get("candidate_class"),
                "decision": row.get("decision"),
                "source": row.get("source"),
                "reason": row.get("reason"),
            }
        )
        if len(selected) >= limit:
            break
    return selected


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def table(rows: list[dict[str, Any]], columns: list[str]) -> str:
        if not rows:
            return "_None found._\n"
        lines = [
            "| " + " | ".join(columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
        return "\n".join(lines) + "\n"

    content = [
        "# Week 1 Vocabulary Summary",
        "",
        f"- Issues: {summary['issue_count']}",
        f"- Total tokens: {summary['total_tokens']}",
        f"- Unique tokens: {summary['unique_tokens']}",
        f"- Vocabulary file: `{summary['vocabulary_file']}`",
        "",
        "## Highest Frequency Tokens",
        table(
            summary["top_tokens"],
            ["token", "total_count", "document_frequency", "percent_of_documents"],
        ),
        "## Candidate Tokens To Remove",
        "These are mostly Rust-cleaner marker tokens or project-generic terms. Treat them as review candidates before removing them from LDA input.",
        "",
        table(
            summary["candidate_tokens_to_remove"],
            ["token", "total_count", "document_frequency", "percent_documents", "candidate_class", "reason"],
        ),
        "## Candidate Tokens To Replace With Ontology Classes",
        "These are exact matches in the ontology workbook. They should be reviewed before replacement because project-specific terms can be meaningful.",
        "",
        table(
            summary["candidate_tokens_to_replace"],
            ["token", "total_count", "document_frequency", "percent_documents", "candidate_class"],
        ),
        "## Project-Specific Or Dominant Tokens",
        "These frequent tokens may dominate topics and should be reviewed after the first LDA run.",
        "",
        table(
            summary["dominant_project_or_unmatched_tokens"],
            ["token", "total_count", "document_frequency", "percent_documents", "reason"],
        ),
    ]
    path.write_text("\n".join(content), encoding="utf-8")


def build_summary(
    records: list[dict[str, Any]],
    vocabulary: list[dict[str, Any]],
    vocabulary_file: Path,
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    total_tokens = sum(row["total_count"] for row in vocabulary)
    top_tokens = vocabulary[:50]

    removal_candidates = top_candidate_rows(candidates, decision="remove", limit=50)
    replacement_candidates = top_candidate_rows(
        candidates,
        source="ontology_exact_match",
        has_candidate_class=True,
        limit=50,
    )
    dominant_unmatched = top_candidate_rows(
        candidates,
        source="high_frequency",
        has_candidate_class=False,
        limit=50,
    )
    manual_review = top_candidate_rows(candidates, source="manual_rule", limit=20)
    dominant_project_or_unmatched = manual_review + dominant_unmatched

    return {
        "issue_count": len(records),
        "total_tokens": total_tokens,
        "unique_tokens": len(vocabulary),
        "vocabulary_file": str(vocabulary_file),
        "top_tokens": top_tokens,
        "candidate_tokens_to_remove": removal_candidates,
        "candidate_tokens_to_replace": replacement_candidates,
        "dominant_project_or_unmatched_tokens": dominant_project_or_unmatched[:50],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tokens",
        type=Path,
        default=Path("data/processed/yarn_tokens.jsonl"),
        help="Tokenized issue JSONL.",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path("reports/week1/ontology_replacement_candidates.csv"),
        help="Ontology/removal candidates CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/vocabulary.csv"),
        help="Vocabulary CSV output.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("reports/week1/vocabulary_summary.json"),
        help="Vocabulary summary JSON output.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("reports/week1/vocabulary_report.md"),
        help="Markdown report answering Week 1 vocabulary questions.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = read_jsonl(args.tokens)
    vocabulary = compute_vocabulary(records)
    candidates = read_candidates(args.candidates)
    summary = build_summary(records, vocabulary, args.output, candidates)

    write_vocabulary(args.output, vocabulary)
    write_json(args.summary_output, summary)
    write_markdown_report(args.report_output, summary)

    print(f"Read {len(records)} tokenized issues")
    print(f"Total tokens: {summary['total_tokens']}")
    print(f"Unique tokens: {summary['unique_tokens']}")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.summary_output}")
    print(f"Wrote {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

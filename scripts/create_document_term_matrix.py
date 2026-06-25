#!/usr/bin/env python3
"""Create a sparse document-term matrix and LDA-compatible text files."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scipy import sparse


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


def read_vocabulary(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"No vocabulary rows found in {path}")
    return [row["token"] for row in rows]


def create_matrix(records: list[dict[str, Any]], vocabulary: list[str]) -> sparse.csr_matrix:
    token_to_column = {token: index for index, token in enumerate(vocabulary)}
    row_indices: list[int] = []
    column_indices: list[int] = []
    values: list[int] = []

    for row_index, record in enumerate(records):
        counts = Counter(record.get("tokens") or [])
        for token, count in counts.items():
            column_index = token_to_column.get(token)
            if column_index is None:
                continue
            row_indices.append(row_index)
            column_indices.append(column_index)
            values.append(count)

    return sparse.csr_matrix(
        (values, (row_indices, column_indices)),
        shape=(len(records), len(vocabulary)),
        dtype="int32",
    )


def write_terms(path: Path, vocabulary: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vocabulary, indent=2) + "\n", encoding="utf-8")


def write_issue_order(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["row_index", "key", "token_count"])
        writer.writeheader()
        for row_index, record in enumerate(records):
            writer.writerow(
                {
                    "row_index": row_index,
                    "key": record.get("key"),
                    "token_count": len(record.get("tokens") or []),
                }
            )


def safe_filename(issue_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", issue_key)


def write_txtfiles(records: list[dict[str, Any]], txtfiles_dir: Path, clear_existing: bool) -> None:
    if clear_existing and txtfiles_dir.exists():
        for path in txtfiles_dir.glob("*.txt"):
            path.unlink()
    txtfiles_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        issue_key = record["key"]
        tokens = record.get("tokens") or []
        path = txtfiles_dir / f"{safe_filename(issue_key)}.txt"
        path.write_text(" ".join(tokens) + "\n", encoding="utf-8")


def summarize(
    matrix: sparse.csr_matrix,
    records: list[dict[str, Any]],
    vocabulary: list[str],
    output_matrix: Path,
    terms_output: Path,
    issue_order_output: Path,
    txtfiles_dir: Path,
) -> dict[str, Any]:
    row_nonzero = matrix.getnnz(axis=1)
    column_nonzero = matrix.getnnz(axis=0)
    token_counts = [len(record.get("tokens") or []) for record in records]
    txt_file_count = sum(1 for _ in txtfiles_dir.glob("*.txt")) if txtfiles_dir.exists() else 0

    return {
        "document_count": matrix.shape[0],
        "term_count": matrix.shape[1],
        "matrix_shape": list(matrix.shape),
        "nonzero_entries": int(matrix.nnz),
        "density": matrix.nnz / (matrix.shape[0] * matrix.shape[1]) if matrix.shape[0] and matrix.shape[1] else 0,
        "total_token_count": int(matrix.sum()),
        "min_tokens_per_issue": min(token_counts) if token_counts else 0,
        "max_tokens_per_issue": max(token_counts) if token_counts else 0,
        "empty_matrix_rows": int((row_nonzero == 0).sum()),
        "empty_matrix_columns": int((column_nonzero == 0).sum()),
        "txt_file_count": txt_file_count,
        "outputs": {
            "document_term_matrix": str(output_matrix),
            "dtm_terms": str(terms_output),
            "dtm_issue_order": str(issue_order_output),
            "txtfiles_dir": str(txtfiles_dir),
        },
        "first_terms": vocabulary[:20],
        "first_issue_keys": [record.get("key") for record in records[:20]],
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
        "--vocabulary",
        type=Path,
        default=Path("data/processed/vocabulary.csv"),
        help="Vocabulary CSV created by create_vocabulary.py.",
    )
    parser.add_argument(
        "--matrix-output",
        type=Path,
        default=Path("data/processed/document_term_matrix.npz"),
        help="Sparse CSR document-term matrix output.",
    )
    parser.add_argument(
        "--terms-output",
        type=Path,
        default=Path("data/processed/dtm_terms.json"),
        help="JSON list mapping matrix columns to vocabulary terms.",
    )
    parser.add_argument(
        "--issue-order-output",
        type=Path,
        default=Path("data/processed/dtm_issue_order.csv"),
        help="CSV mapping matrix rows to issue keys.",
    )
    parser.add_argument(
        "--txtfiles-dir",
        type=Path,
        default=Path("data/txtfiles/Yarn"),
        help="Directory containing one token text file per issue.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("reports/week1/document_term_matrix_summary.json"),
        help="Summary report path.",
    )
    parser.add_argument(
        "--keep-existing-txt",
        action="store_true",
        help="Do not remove existing .txt files before writing current issue files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = read_jsonl(args.tokens)
    vocabulary = read_vocabulary(args.vocabulary)
    matrix = create_matrix(records, vocabulary)

    args.matrix_output.parent.mkdir(parents=True, exist_ok=True)
    sparse.save_npz(args.matrix_output, matrix)
    write_terms(args.terms_output, vocabulary)
    write_issue_order(args.issue_order_output, records)
    write_txtfiles(records, args.txtfiles_dir, clear_existing=not args.keep_existing_txt)

    summary = summarize(
        matrix,
        records,
        vocabulary,
        args.matrix_output,
        args.terms_output,
        args.issue_order_output,
        args.txtfiles_dir,
    )
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Created DTM with shape {matrix.shape[0]} x {matrix.shape[1]}")
    print(f"Nonzero entries: {matrix.nnz}")
    print(f"Total token count: {int(matrix.sum())}")
    print(f"Text files written: {summary['txt_file_count']}")
    print(f"Wrote {args.matrix_output}")
    print(f"Wrote {args.terms_output}")
    print(f"Wrote {args.issue_order_output}")
    print(f"Wrote {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

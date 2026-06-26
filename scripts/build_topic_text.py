#!/usr/bin/env python3
"""Build raw topic-modeling text from normalized Jira summary and description."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_text(summary: str | None, description: str | None) -> str:
    summary = (summary or "").strip()
    description = (description or "").strip()
    if summary and description:
        return f"{summary}\n{description}"
    return summary or description


def text_record(issue: dict[str, Any]) -> dict[str, Any]:
    summary = issue.get("summary") or ""
    description = issue.get("description") or ""
    return {
        "key": issue.get("key"),
        "summary": summary,
        "description": description,
        "text_raw": make_text(summary, description),
        "design_decisions": issue.get("design_decisions") or {},
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    char_lengths = [len(record["text_raw"]) for record in records]
    word_lengths = [len(record["text_raw"].split()) for record in records]
    empty_descriptions = sum(not record["description"].strip() for record in records)
    empty_texts = sum(not record["text_raw"].strip() for record in records)

    return {
        "issue_count": len(records),
        "empty_descriptions": empty_descriptions,
        "empty_topic_texts": empty_texts,
        "text_char_length": {
            "min": min(char_lengths) if char_lengths else 0,
            "max": max(char_lengths) if char_lengths else 0,
            "mean": mean(char_lengths) if char_lengths else 0,
            "median": median(char_lengths) if char_lengths else 0,
        },
        "text_word_length": {
            "min": min(word_lengths) if word_lengths else 0,
            "max": max(word_lengths) if word_lengths else 0,
            "mean": mean(word_lengths) if word_lengths else 0,
            "median": median(word_lengths) if word_lengths else 0,
        },
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/normalized/yarn_issues_normalized.json"),
        help="Normalized issue JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/yarn_text_raw.jsonl"),
        help="JSONL output containing summary+description text per issue.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("reports/week1/yarn_text_raw_summary.json"),
        help="Summary report path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_json(args.input)
    issues = payload.get("issues") or []
    records = [text_record(issue) for issue in issues]
    summary = summarize(records)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output, records)

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Built raw topic text for {len(records)} issues")
    print(f"Empty descriptions: {summary['empty_descriptions']}")
    print(f"Empty topic texts: {summary['empty_topic_texts']}")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

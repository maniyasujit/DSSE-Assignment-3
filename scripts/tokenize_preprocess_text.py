#!/usr/bin/env python3
"""Tokenize cleaned Jira text and apply stop-word removal plus lemmatization."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer


NLTK_RESOURCES = [
    ("punkt", "tokenizers/punkt"),
    ("punkt_tab", "tokenizers/punkt_tab"),
    ("stopwords", "corpora/stopwords"),
    ("wordnet", "corpora/wordnet"),
    ("omw-1.4", "corpora/omw-1.4"),
    ("averaged_perceptron_tagger", "taggers/averaged_perceptron_tagger"),
    ("averaged_perceptron_tagger_eng", "taggers/averaged_perceptron_tagger_eng"),
]
CONTRACTION_FRAGMENTS = {
    "'d",
    "'ll",
    "'m",
    "'re",
    "'s",
    "'ve",
    "n't",
}


def ensure_nltk_resources() -> None:
    for package, resource_path in NLTK_RESOURCES:
        try:
            nltk.data.find(resource_path)
        except LookupError:
            nltk.download(package, quiet=True)


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


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def wordnet_pos(treebank_tag: str) -> str:
    if treebank_tag.startswith("J"):
        return "a"
    if treebank_tag.startswith("V"):
        return "v"
    if treebank_tag.startswith("R"):
        return "r"
    return "n"


def is_punctuation_only(token: str) -> bool:
    return not any(char.isalnum() for char in token)


def normalize_token(token: str) -> str:
    token = token.strip().lower()
    # Keep words such as resource-aware as two useful tokens rather than one
    # punctuation-heavy token.
    return token.strip("'\"`.,;:!?()[]{}<>")


def keep_token(token: str, stop_words: set[str], min_token_length: int, keep_numeric: bool) -> bool:
    if not token:
        return False
    if token in CONTRACTION_FRAGMENTS:
        return False
    if is_punctuation_only(token):
        return False
    if not keep_numeric and token.isnumeric():
        return False
    if len(token) < min_token_length:
        return False
    return token not in stop_words


def tokenize_text(
    text: str,
    stop_words: set[str],
    lemmatizer: WordNetLemmatizer,
    min_token_length: int,
    keep_numeric: bool,
) -> list[str]:
    raw_tokens = nltk.word_tokenize(text.lower())
    normalized_tokens = []
    for token in raw_tokens:
        token = normalize_token(token)
        if not keep_token(token, stop_words, min_token_length, keep_numeric):
            continue
        normalized_tokens.append(token)

    tagged_tokens = nltk.pos_tag(normalized_tokens)
    lemmatized_tokens = []
    for token, tag in tagged_tokens:
        lemma = lemmatizer.lemmatize(token, wordnet_pos(tag))
        if keep_token(lemma, stop_words, min_token_length, keep_numeric):
            lemmatized_tokens.append(lemma)
    return lemmatized_tokens


def preprocess_records(
    records: list[dict[str, Any]],
    min_token_length: int,
    keep_numeric: bool,
) -> list[dict[str, Any]]:
    stop_words = set(stopwords.words("english"))
    lemmatizer = WordNetLemmatizer()
    output = []

    for record in records:
        tokens = tokenize_text(
            record.get("text_cleaned") or "",
            stop_words=stop_words,
            lemmatizer=lemmatizer,
            min_token_length=min_token_length,
            keep_numeric=keep_numeric,
        )
        output.append(
            {
                "key": record["key"],
                "tokens": tokens,
                "token_count": len(tokens),
                "design_decisions": record.get("design_decisions") or {},
            }
        )
    return output


def summarize(records: list[dict[str, Any]], min_token_length: int, keep_numeric: bool) -> dict[str, Any]:
    token_counts = [record["token_count"] for record in records]
    vocabulary = Counter(token for record in records for token in record["tokens"])
    document_frequency = Counter()
    for record in records:
        document_frequency.update(set(record["tokens"]))

    return {
        "issue_count": len(records),
        "preprocessing": {
            "lowercase": True,
            "tokenizer": "nltk.word_tokenize",
            "stopwords": "nltk.corpus.stopwords.words('english')",
            "remove_punctuation_only_tokens": True,
            "lemmatization": "nltk.stem.WordNetLemmatizer with POS tags",
            "stemming": False,
            "min_token_length": min_token_length,
            "keep_numeric_tokens": keep_numeric,
        },
        "empty_token_lists": sum(record["token_count"] == 0 for record in records),
        "token_count_per_issue": {
            "min": min(token_counts) if token_counts else 0,
            "max": max(token_counts) if token_counts else 0,
            "mean": mean(token_counts) if token_counts else 0,
            "median": median(token_counts) if token_counts else 0,
        },
        "total_tokens": sum(token_counts),
        "unique_tokens": len(vocabulary),
        "top_tokens": vocabulary.most_common(50),
        "top_document_frequency_tokens": document_frequency.most_common(50),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/yarn_text_cleaned.jsonl"),
        help="Cleaned JSONL produced by clean_topic_text_with_rust.py.",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("data/processed/yarn_tokens.jsonl"),
        help="Tokenized JSONL output.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data/processed/yarn_tokens.json"),
        help="Viewer-friendly JSON output.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("reports/week1/yarn_tokens_summary.json"),
        help="Summary report path.",
    )
    parser.add_argument(
        "--min-token-length",
        type=int,
        default=2,
        help="Drop tokens shorter than this length after normalization.",
    )
    parser.add_argument(
        "--keep-numeric",
        action="store_true",
        help="Keep purely numeric tokens. By default they are removed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_nltk_resources()

    input_records = read_jsonl(args.input)
    token_records = preprocess_records(
        input_records,
        min_token_length=args.min_token_length,
        keep_numeric=args.keep_numeric,
    )
    summary = summarize(token_records, args.min_token_length, args.keep_numeric)

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_jsonl, token_records)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(
            {
                "source": str(args.input),
                "issue_count": len(token_records),
                "issues": token_records,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Tokenized and preprocessed {len(token_records)} issues")
    print(f"Empty token lists: {summary['empty_token_lists']}")
    print(f"Total tokens: {summary['total_tokens']}")
    print(f"Unique tokens: {summary['unique_tokens']}")
    print(f"Wrote {args.output_jsonl}")
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

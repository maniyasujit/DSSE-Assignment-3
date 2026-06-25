# DSSE Assignment 3 - Week 1

This repository contains the Week 1 data-preparation pipeline for the **Yarn** project. The goal of Week 1 was to collect Jira issue data, normalize it into the required simplified structure, clean and preprocess issue text, create the vocabulary, and build the document-term matrix for later LDA/topic-modeling work.

## Inputs

- `data/input/Issues.xlsx`: assignment issue list. Only the `Yarn` sheet is used.
- `data/input/Bot Comments.rtf`: bot account names used to mark automated comments.
- Apache Jira REST API: used to download issue details and comments.
- PDF-linked ontology workbook: downloaded by `scripts/create_ontology_candidates.py`.

The three design-decision flags in `Issues.xlsx` are interpreted in this order:

```text
Existence, Property, Executive
```

## Pipeline

Run these commands from the project root.

```bash
python3 scripts/parse_issue_list.py --project Yarn
python3 scripts/download_jira_data.py
python3 scripts/normalize_jira_data.py
python3 scripts/summarize_parent_issues.py
python3 scripts/build_topic_text.py
./scripts/setup_rust_cleaner.sh
.venv/bin/python scripts/clean_topic_text_with_rust.py
.venv/bin/python scripts/tokenize_preprocess_text.py
python3 scripts/create_ontology_candidates.py
python3 scripts/create_vocabulary.py
.venv/bin/python scripts/create_document_term_matrix.py
```

## Main Outputs

- `data/normalized/yarn_issue_list.json`: parsed Yarn issue keys and design-decision flags.
- `data/normalized/yarn_issues_normalized.json`: normalized Jira issue data.
- `data/processed/yarn_text_raw.jsonl`: raw `summary + description` text.
- `data/processed/yarn_text_cleaned.jsonl`: text cleaned with the PDF-linked Rust cleaner.
- `data/processed/yarn_tokens.jsonl`: preprocessed token lists per issue.
- `data/processed/vocabulary.csv`: token total frequency and document frequency.
- `reports/week1/ontology_replacement_candidates.csv`: tokens to review for removal or ontology replacement.
- `data/processed/document_term_matrix.npz`: sparse document-term matrix.
- `data/processed/dtm_terms.json`: matrix column-to-token mapping.
- `data/processed/dtm_issue_order.csv`: matrix row-to-issue mapping.
- `data/txtfiles/Yarn/`: one token text file per issue for compatibility with the PDF-linked LDA examples.

## Result Summary

```text
Yarn issues: 1545
Raw Jira files downloaded: 1545
Issues with parent: 800
Issues without parent: 745
Total comments: 28497
Bot comments: 7816
Non-bot comments: 20681
Attachments: 5816
Vocabulary terms: 6481
Total preprocessed tokens: 77982
Document-term matrix shape: 1545 x 6481
LDA-compatible text files: 1545
```

## Notes

- `data/raw/jira/` and `data/txtfiles/` are generated and can be reproduced from scripts.
- The Rust cleaner setup is captured in `scripts/setup_rust_cleaner.sh`.
- Week 1 does not replace ontology candidates yet; it only identifies tokens that should be reviewed before Week 2 topic modeling.

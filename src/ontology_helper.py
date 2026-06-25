"""
src/ontology_helper.py
======================
Vocabulary analysis and ontology flagging for the YARN Jira corpus.

Functions
---------
* flag_vocabulary()   — Classifies each vocabulary term into one or more
                        ontology categories and flags Yarn-specific terms.
* apply_ontology()    — Replaces tokens in ``token_list`` column with their
                        ontology class labels (disabled by default).

Saves
-----
data/output/yarn_vocabulary_flags.csv

Columns in flags CSV:
    token, frequency, is_stopword_candidate, is_yarn_specific,
    ontology_class, flag_reason
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from src import config
from src.utils import ensure_dirs, get_logger, save_csv

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# THRESHOLDS
# ---------------------------------------------------------------------------
# Terms appearing in more than this fraction of documents are flagged
# as "extremely common" / stopword candidates.
_COMMON_FREQ_THRESHOLD = 0.5  # 50 % of documents


# ---------------------------------------------------------------------------
# ONTOLOGY FLAGGING
# ---------------------------------------------------------------------------

def flag_vocabulary(
    vocab_df: pd.DataFrame,
    df_issues: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Analyse the vocabulary and flag terms by category.

    Parameters
    ----------
    vocab_df:  Full vocabulary DataFrame (columns: token, frequency).
    df_issues: Optional — the cleaned issues DataFrame used to compute
               document frequency (for stopword candidate detection).

    Returns
    -------
    pd.DataFrame  Flags DataFrame saved to ``YARN_VOCAB_FLAGS_CSV``.
    """
    if vocab_df.empty:
        logger.warning(
            "Vocabulary is empty — no flags to generate. "
            "Run with Jira API enrichment enabled to populate vocabulary."
        )
        empty = pd.DataFrame(columns=[
            "token", "frequency", "is_stopword_candidate",
            "is_yarn_specific", "ontology_class", "flag_reason",
        ])
        ensure_dirs(config.OUTPUT_DIR)
        save_csv(empty, config.YARN_VOCAB_FLAGS_CSV, label="yarn_vocabulary_flags")
        return empty

    flags = vocab_df.copy()
    flags["is_stopword_candidate"] = False
    flags["is_yarn_specific"] = False
    flags["ontology_class"] = ""
    flags["flag_reason"] = ""

    # ------------------------------------------------------------------
    # Document frequency (if issues DataFrame provided)
    # ------------------------------------------------------------------
    doc_freq: dict[str, int] = {}
    n_docs = 0
    if df_issues is not None and "token_list" in df_issues.columns:
        n_docs = len(df_issues)
        import ast
        for raw in df_issues["token_list"].dropna():
            try:
                tokens = set(ast.literal_eval(str(raw)))
            except (ValueError, SyntaxError):
                tokens = set(str(raw).split())
            for t in tokens:
                doc_freq[t] = doc_freq.get(t, 0) + 1

    # ------------------------------------------------------------------
    # Classify each token
    # ------------------------------------------------------------------
    ontology_lower: dict[str, str] = {k.lower(): v for k, v in config.ONTOLOGY_MAP.items()}
    yarn_specific_lower: set[str] = {t.lower() for t in config.YARN_SPECIFIC_TERMS}

    for idx, row in flags.iterrows():
        token = str(row["token"]).lower()
        reasons: list[str] = []

        # Stopword candidate — appears in >50% of documents
        if n_docs > 0:
            df_count = doc_freq.get(token, 0)
            if df_count / n_docs > _COMMON_FREQ_THRESHOLD:
                flags.at[idx, "is_stopword_candidate"] = True
                reasons.append(f"high document frequency ({df_count}/{n_docs})")

        # Extremely high raw frequency (top 1% of vocab)
        top1pct_freq = vocab_df["frequency"].quantile(0.99)
        if row["frequency"] >= top1pct_freq:
            flags.at[idx, "is_stopword_candidate"] = True
            reasons.append("top 1% frequency")

        # Yarn-specific
        if token in yarn_specific_lower:
            flags.at[idx, "is_yarn_specific"] = True
            reasons.append("Yarn/Hadoop-specific term")

        # Ontology class
        if token in ontology_lower:
            flags.at[idx, "ontology_class"] = ontology_lower[token]
            reasons.append(f"ontology: {ontology_lower[token]}")

        flags.at[idx, "flag_reason"] = "; ".join(reasons)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    n_stopword = flags["is_stopword_candidate"].sum()
    n_yarn = flags["is_yarn_specific"].sum()
    n_ontology = (flags["ontology_class"] != "").sum()
    logger.info("Vocabulary flags summary:")
    logger.info("  Stopword candidates  : %d", n_stopword)
    logger.info("  Yarn-specific terms  : %d", n_yarn)
    logger.info("  Ontology-mapped terms: %d", n_ontology)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    ensure_dirs(config.OUTPUT_DIR)
    save_csv(flags, config.YARN_VOCAB_FLAGS_CSV, label="yarn_vocabulary_flags")

    return flags


# ---------------------------------------------------------------------------
# ONTOLOGY REPLACEMENT
# ---------------------------------------------------------------------------

def apply_ontology(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace tokens in ``token_list`` with their ontology class labels.

    Only executed when ``config.ENABLE_ONTOLOGY_REPLACEMENT = True``.
    Modifies ``token_list`` and rebuilds ``cleaned_text`` from the result.

    Parameters
    ----------
    df: Cleaned Yarn DataFrame with ``token_list`` column.

    Returns
    -------
    pd.DataFrame  Updated DataFrame (not saved here — caller must save).
    """
    if not config.ENABLE_ONTOLOGY_REPLACEMENT:
        logger.info("Ontology replacement is disabled (ENABLE_ONTOLOGY_REPLACEMENT=False).")
        return df

    import ast

    ontology_lower: dict[str, str] = {k.lower(): v for k, v in config.ONTOLOGY_MAP.items()}
    logger.info("Applying ontology replacement to token lists.")

    def _replace_tokens(raw: str) -> str:
        try:
            tokens: list[str] = ast.literal_eval(str(raw))
        except (ValueError, SyntaxError):
            tokens = str(raw).split()
        replaced = [ontology_lower.get(t.lower(), t) for t in tokens]
        return str(replaced)

    df = df.copy()
    df["token_list"] = df["token_list"].apply(_replace_tokens)
    df["cleaned_text"] = df["token_list"].apply(
        lambda raw: " ".join(ast.literal_eval(raw)) if raw else ""
    )
    logger.info("Ontology replacement complete.")
    return df

"""
src/parent_extractor.py
=======================
Determines parent issue information for each Yarn issue.

If ``parent_key`` / ``parent_summary`` columns already exist in the input
DataFrame (populated via Jira API enrichment or the xlsx), those values are
used directly.  Otherwise all parent fields remain empty.

Adds:
    has_parent (bool)  — True when a non-empty parent_key is present.

Saves:
    data/processed/yarn_issues_with_parents.csv
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src import config
from src.utils import ensure_dirs, get_logger, safe_str, save_csv

logger = get_logger(__name__)


def extract_parents(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract and validate parent issue information.

    Parameters
    ----------
    df: Filtered Yarn DataFrame (from data_loader or jira_enricher).

    Returns
    -------
    pd.DataFrame  DataFrame with ``parent_key``, ``parent_summary``,
                  ``has_parent`` columns populated, saved to CSV.
    """
    df = df.copy()

    # ------------------------------------------------------------------
    # Ensure parent columns exist
    # ------------------------------------------------------------------
    for col in ("parent_key", "parent_summary"):
        if col not in df.columns:
            df[col] = ""
            logger.warning(
                "Column '%s' not found in input. Created as empty. "
                "Enable Jira API enrichment to populate parent data.",
                col,
            )

    # ------------------------------------------------------------------
    # Normalise parent keys
    # ------------------------------------------------------------------
    df["parent_key"] = df["parent_key"].apply(safe_str).str.strip().str.upper()
    df["parent_summary"] = df["parent_summary"].apply(safe_str).str.strip()

    # ------------------------------------------------------------------
    # Compute has_parent
    # ------------------------------------------------------------------
    df["has_parent"] = df["parent_key"].apply(lambda v: bool(v) and v != "NAN")

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    total = len(df)
    with_parent = df["has_parent"].sum()
    without_parent = total - with_parent

    logger.info("Parent extraction results:")
    logger.info("  Total issues          : %d", total)
    logger.info("  Issues with parent    : %d  (%.1f%%)", with_parent,
                100 * with_parent / total if total else 0)
    logger.info("  Issues without parent : %d  (%.1f%%)", without_parent,
                100 * without_parent / total if total else 0)

    if with_parent == 0:
        logger.warning(
            "No parent keys found. This is expected when Jira API enrichment "
            "is disabled, since the xlsx does not contain parent metadata."
        )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    ensure_dirs(config.PROCESSED_DIR)
    save_csv(df, config.YARN_PARENTS_CSV, label="yarn_issues_with_parents")

    return df

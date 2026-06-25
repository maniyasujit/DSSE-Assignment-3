"""
src/vocabulary_builder.py
=========================
Builds a vocabulary from the tokenised Yarn corpus and produces
frequency statistics, ranked token CSVs, and bar-chart visualisations.

Outputs
-------
data/output/yarn_vocabulary.csv          — full vocabulary (token, frequency)
data/output/yarn_top_20_tokens.csv
data/output/yarn_top_50_tokens.csv
data/output/yarn_top_100_tokens.csv
data/output/yarn_top_20_terms.png        — horizontal bar chart
data/output/yarn_top_50_terms.png
"""

from __future__ import annotations

import ast
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # non-interactive backend (safe for scripts)
import matplotlib.pyplot as plt
import pandas as pd

from src import config
from src.utils import ensure_dirs, get_logger, save_csv

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# TOKEN EXTRACTION
# ---------------------------------------------------------------------------

def _extract_tokens(df: pd.DataFrame) -> list[str]:
    """
    Flatten the ``token_list`` column across all issues into a single list
    of tokens.

    ``token_list`` may be stored as a stringified Python list or a plain
    space-separated string.
    """
    all_tokens: list[str] = []

    for raw in df["token_list"].dropna():
        raw = str(raw).strip()
        if not raw or raw in ("[]", ""):
            continue
        # Try to parse as a Python list
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                all_tokens.extend(str(t) for t in parsed)
                continue
        except (ValueError, SyntaxError):
            pass
        # Fallback: space-separated tokens
        all_tokens.extend(raw.split())

    return all_tokens


# ---------------------------------------------------------------------------
# VOCABULARY BUILDER
# ---------------------------------------------------------------------------

def build_vocabulary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a frequency-sorted vocabulary from the cleaned token lists.

    Parameters
    ----------
    df: Preprocessed Yarn DataFrame with a ``token_list`` column.

    Returns
    -------
    pd.DataFrame  Vocabulary DataFrame with columns: ``token``, ``frequency``.
                  Also saves all output files.
    """
    if "token_list" not in df.columns:
        logger.error(
            "Column 'token_list' not found. Run preprocessing before building vocabulary."
        )
        return pd.DataFrame(columns=["token", "frequency"])

    # ------------------------------------------------------------------
    # Count frequencies
    # ------------------------------------------------------------------
    all_tokens = _extract_tokens(df)

    if not all_tokens:
        logger.warning(
            "No tokens found in 'token_list'. "
            "Vocabulary will be empty. "
            "This is expected if Jira API enrichment is disabled and all "
            "summary/description fields are empty."
        )
        empty_vocab = pd.DataFrame(columns=["token", "frequency"])
        _save_all(empty_vocab)
        return empty_vocab

    counter = Counter(all_tokens)
    logger.info(
        "Total tokens (with repetition): %d | Unique vocabulary: %d",
        len(all_tokens), len(counter),
    )

    # ------------------------------------------------------------------
    # Build vocabulary DataFrame
    # ------------------------------------------------------------------
    vocab_df = (
        pd.DataFrame.from_dict(counter, orient="index", columns=["frequency"])
        .reset_index()
        .rename(columns={"index": "token"})
        .sort_values("frequency", ascending=False)
        .reset_index(drop=True)
    )

    _save_all(vocab_df)
    return vocab_df


def _save_all(vocab_df: pd.DataFrame) -> None:
    """Save vocabulary CSVs and generate visualisations."""
    ensure_dirs(config.OUTPUT_DIR)

    # Full vocabulary
    save_csv(vocab_df, config.YARN_VOCAB_CSV, label="yarn_vocabulary")

    # Top-N subsets
    for n, path in [
        (20, config.YARN_TOP20_CSV),
        (50, config.YARN_TOP50_CSV),
        (100, config.YARN_TOP100_CSV),
    ]:
        top = vocab_df.head(n).copy()
        save_csv(top, path, label=f"top_{n}_tokens")

    # Visualisations
    if not vocab_df.empty:
        _plot_top_n(vocab_df, 20, config.YARN_TOP20_PNG)
        _plot_top_n(vocab_df, 50, config.YARN_TOP50_PNG)
    else:
        logger.info("Skipping plots — vocabulary is empty.")


# ---------------------------------------------------------------------------
# VISUALISATION
# ---------------------------------------------------------------------------

def _plot_top_n(vocab_df: pd.DataFrame, n: int, save_path: Path) -> None:
    """
    Generate and save a horizontal bar chart of the top-N vocabulary terms.

    Parameters
    ----------
    vocab_df:  Full vocabulary DataFrame sorted by frequency descending.
    n:         Number of top terms to display.
    save_path: Output PNG file path.
    """
    top = vocab_df.head(n)
    if top.empty:
        logger.info("No data for top-%d plot.", n)
        return

    fig, ax = plt.subplots(figsize=(10, max(4, n // 3)))
    ax.barh(
        top["token"][::-1],
        top["frequency"][::-1],
        color="#2563EB",
        edgecolor="white",
        linewidth=0.4,
    )
    ax.set_xlabel("Frequency", fontsize=11)
    ax.set_title(
        f"Top {n} Terms — YARN Jira Corpus",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", labelsize=8 if n > 30 else 10)

    plt.tight_layout()
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved plot → %s", save_path)

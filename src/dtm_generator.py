"""
src/dtm_generator.py
====================
Generates a Document-Term Matrix (DTM) from the preprocessed Yarn corpus.

Uses sklearn's CountVectorizer with the ``cleaned_text`` column from the
preprocessed DataFrame.

Outputs
-------
data/output/yarn_document_term_matrix.csv      — dense DTM (rows = issues)
data/output/yarn_document_term_matrix_sparse.npz — sparse matrix (scipy)
data/output/yarn_dtm_features.csv              — feature names (vocabulary)

Logged statistics
-----------------
  - Number of Yarn documents
  - Vocabulary size
  - Matrix dimensions (rows × cols)
  - Number of non-zero entries
  - Sparsity percentage
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import CountVectorizer

from src import config
from src.utils import ensure_dirs, get_logger, save_csv

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DTM GENERATION
# ---------------------------------------------------------------------------

def generate_dtm(df: pd.DataFrame) -> tuple[sp.csr_matrix, list[str]]:
    """
    Build the Document-Term Matrix from ``cleaned_text``.

    Parameters
    ----------
    df: Preprocessed Yarn DataFrame with a ``cleaned_text`` column.

    Returns
    -------
    tuple[scipy.sparse.csr_matrix, list[str]]
        (sparse DTM, feature names list)
    """
    if "cleaned_text" not in df.columns:
        logger.error(
            "Column 'cleaned_text' not found. "
            "Run preprocessing before generating the DTM."
        )
        return sp.csr_matrix((0, 0)), []

    texts = df["cleaned_text"].fillna("").tolist()

    # Filter out completely empty texts
    non_empty_texts = [t for t in texts if t.strip()]
    n_empty = len(texts) - len(non_empty_texts)
    if n_empty > 0:
        logger.warning(
            "%d issues have empty cleaned_text and will contribute zero-rows "
            "to the DTM. Enable Jira API enrichment to populate text.",
            n_empty,
        )

    if not non_empty_texts:
        logger.warning(
            "All documents are empty — returning empty DTM. "
            "This is expected when ENABLE_JIRA_API=False."
        )
        _save_empty_outputs(df)
        return sp.csr_matrix((0, 0)), []

    # ------------------------------------------------------------------
    # Fit CountVectorizer
    # ------------------------------------------------------------------
    # Use pre-tokenised text: tokens are already space-separated after
    # preprocessing, so we use a simple whitespace analyser.
    vectorizer = CountVectorizer(
        analyzer="word",
        token_pattern=r"(?u)\b[a-zA-Z]{3,}\b",  # alpha only, min 3 chars
        min_df=1,                                  # include all seen tokens
        max_df=1.0,
    )

    dtm_sparse: sp.csr_matrix = vectorizer.fit_transform(texts)
    feature_names: list[str] = vectorizer.get_feature_names_out().tolist()

    # ------------------------------------------------------------------
    # Log statistics
    # ------------------------------------------------------------------
    n_docs, n_terms = dtm_sparse.shape
    n_nonzero = dtm_sparse.nnz
    sparsity = (1 - n_nonzero / (n_docs * n_terms)) * 100 if (n_docs * n_terms) > 0 else 0

    logger.info("Document-Term Matrix statistics:")
    logger.info("  Documents (rows) : %d", n_docs)
    logger.info("  Vocabulary (cols): %d", n_terms)
    logger.info("  Dimensions       : %d × %d", n_docs, n_terms)
    logger.info("  Non-zero entries : %d", n_nonzero)
    logger.info("  Sparsity         : %.2f%%", sparsity)

    # ------------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------------
    ensure_dirs(config.OUTPUT_DIR)
    _save_sparse(dtm_sparse, config.YARN_DTM_SPARSE)
    _save_dense(dtm_sparse, feature_names, df, config.YARN_DTM_CSV)
    _save_features(feature_names, config.YARN_DTM_FEATURES_CSV)

    return dtm_sparse, feature_names


# ---------------------------------------------------------------------------
# SAVE HELPERS
# ---------------------------------------------------------------------------

def _save_sparse(matrix: sp.csr_matrix, path: Path) -> None:
    """Save the sparse DTM as a compressed .npz file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sp.save_npz(str(path), matrix)
    logger.info("Saved sparse DTM → %s", path)


def _save_dense(
    matrix: sp.csr_matrix,
    feature_names: list[str],
    df: pd.DataFrame,
    path: Path,
) -> None:
    """
    Save the DTM as a dense CSV.

    Rows are labelled with ``issue_key`` if available.
    For very large matrices (> 10 000 cells), logs a size warning.
    """
    path = Path(path)
    n_docs, n_terms = matrix.shape
    cell_count = n_docs * n_terms

    if cell_count > 5_000_000:
        logger.warning(
            "Dense DTM has %d cells (%d × %d). "
            "Writing may be slow and the file will be large. "
            "Consider using the sparse .npz version for downstream processing.",
            cell_count, n_docs, n_terms,
        )

    dense = matrix.toarray()
    index_labels = (
        df["issue_key"].values if "issue_key" in df.columns else list(range(n_docs))
    )
    dtm_df = pd.DataFrame(dense, columns=feature_names, index=index_labels)
    dtm_df.index.name = "issue_key"
    dtm_df.reset_index(inplace=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    dtm_df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info("Saved dense DTM → %s  (%d × %d)", path, n_docs, n_terms)


def _save_features(feature_names: list[str], path: Path) -> None:
    """Save feature names (vocabulary) to a single-column CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"feature": feature_names}).to_csv(path, index=False, encoding="utf-8-sig")
    logger.info("Saved DTM features → %s  (%d features)", path, len(feature_names))


def _save_empty_outputs(df: pd.DataFrame) -> None:
    """Create empty placeholder output files when the corpus has no text."""
    ensure_dirs(config.OUTPUT_DIR)

    # Empty sparse matrix
    empty_sparse = sp.csr_matrix((0, 0))
    sp.save_npz(str(config.YARN_DTM_SPARSE), empty_sparse)

    # Empty dense CSV
    pd.DataFrame(columns=["issue_key"]).to_csv(
        config.YARN_DTM_CSV, index=False, encoding="utf-8-sig"
    )

    # Empty features CSV
    pd.DataFrame(columns=["feature"]).to_csv(
        config.YARN_DTM_FEATURES_CSV, index=False, encoding="utf-8-sig"
    )

    logger.info("Saved empty DTM placeholder files to %s.", config.OUTPUT_DIR)

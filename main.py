"""
main.py
=======
Week 1 — YARN Jira Issue Mining Pipeline

Run with:
    python main.py

Pipeline steps
--------------
 1. Create required output directories
 2. Load Issues.xlsx
 3. Inspect sheets and columns
 4. Standardise columns
 5. Map data into simplified Jira structure
 6. Filter Yarn/YARN issues only
 7. (Optional) Enrich with Jira API if ENABLE_JIRA_API=True
 8. Extract parent issue information
 9. Load bot comment list from Bot Comments.rtf
10. Parse comments and attachments where available
11. Preprocess summary + description text
12. Build vocabulary
13. Generate vocabulary statistics and charts
14. Flag ontology / project-specific terms
15. (Optional) Apply ontology replacement if ENABLE_ONTOLOGY_REPLACEMENT=True
16. Create document-term matrix
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on the Python path so "src.*" imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config
from src.utils import ensure_dirs, setup_logging, get_logger


def main() -> None:
    # -----------------------------------------------------------------------
    # Initialise logging
    # -----------------------------------------------------------------------
    setup_logging(level=config.LOG_LEVEL, log_file=config.LOG_FILE)
    logger = get_logger("main")
    logger.info("=" * 70)
    logger.info("YARN Jira Issue Mining — Week 1 Pipeline")
    logger.info("=" * 70)

    # -----------------------------------------------------------------------
    # Step 1: Create required directories
    # -----------------------------------------------------------------------
    logger.info("[Step 1] Creating output directories…")
    ensure_dirs(
        config.RAW_DIR,
        config.PROCESSED_DIR,
        config.OUTPUT_DIR,
    )

    # -----------------------------------------------------------------------
    # Steps 2–6: Load, inspect, standardise, filter
    # -----------------------------------------------------------------------
    logger.info("[Steps 2–6] Loading and filtering Issues.xlsx…")
    from src.data_loader import load_yarn_issues
    df = load_yarn_issues(
        xlsx_path=config.ISSUES_XLSX,
        sheet_name=config.SHEET_NAME,
    )
    logger.info("Yarn issues loaded: %d", len(df))

    # -----------------------------------------------------------------------
    # Step 7: Optional Jira API enrichment
    # -----------------------------------------------------------------------
    if config.ENABLE_JIRA_API:
        logger.info("[Step 7] Enriching with Jira REST API…")
        from src.jira_enricher import enrich_yarn_issues
        df = enrich_yarn_issues(df)
        logger.info("Enrichment complete. Working with enriched data.")
    else:
        logger.info(
            "[Step 7] Jira API enrichment is DISABLED. "
            "Set ENABLE_JIRA_API=True in src/config.py to enable it."
        )

    # -----------------------------------------------------------------------
    # Step 8: Parent issue extraction
    # -----------------------------------------------------------------------
    logger.info("[Step 8] Extracting parent issue information…")
    from src.parent_extractor import extract_parents
    df = extract_parents(df)

    # -----------------------------------------------------------------------
    # Step 9: Load bot comment list
    # -----------------------------------------------------------------------
    logger.info("[Step 9] Loading bot comment list from Bot Comments.rtf…")
    from src.bot_handler import load_bot_list, annotate_bot_comments
    bot_list = load_bot_list(config.BOT_COMMENTS_RTF)

    # -----------------------------------------------------------------------
    # Step 10: Parse comments and attachments; annotate bot comments
    # -----------------------------------------------------------------------
    logger.info("[Step 10] Annotating bot comments…")
    df = annotate_bot_comments(df, bot_list)

    # -----------------------------------------------------------------------
    # Step 11: Text preprocessing
    # -----------------------------------------------------------------------
    logger.info("[Step 11] Preprocessing issue text (summary + description)…")
    try:
        from src.preprocessing import preprocess_dataframe
        df = preprocess_dataframe(df)
    except RuntimeError as exc:
        logger.error("Preprocessing failed: %s", exc)
        logger.error(
            "To fix, run the setup commands and retry:\n"
            "    python -m spacy download en_core_web_sm\n"
            "    python -c \"import nltk; nltk.download('stopwords')\""
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 12: Build vocabulary
    # -----------------------------------------------------------------------
    logger.info("[Step 12] Building vocabulary from token lists…")
    from src.vocabulary_builder import build_vocabulary
    vocab_df = build_vocabulary(df)
    logger.info("Vocabulary size: %d unique tokens", len(vocab_df))

    # -----------------------------------------------------------------------
    # Step 13: Vocabulary statistics are generated inside build_vocabulary()
    # (charts are saved automatically).
    # -----------------------------------------------------------------------
    logger.info("[Step 13] Vocabulary statistics and charts saved.")

    # -----------------------------------------------------------------------
    # Step 14: Flag ontology / Yarn-specific terms
    # -----------------------------------------------------------------------
    logger.info("[Step 14] Flagging ontology and project-specific terms…")
    from src.ontology_helper import flag_vocabulary, apply_ontology
    flag_vocabulary(vocab_df, df_issues=df)

    # -----------------------------------------------------------------------
    # Step 15: Optional ontology replacement
    # -----------------------------------------------------------------------
    if config.ENABLE_ONTOLOGY_REPLACEMENT:
        logger.info("[Step 15] Applying ontology token replacement…")
        df = apply_ontology(df)
    else:
        logger.info(
            "[Step 15] Ontology replacement is DISABLED "
            "(ENABLE_ONTOLOGY_REPLACEMENT=False)."
        )

    # -----------------------------------------------------------------------
    # Step 16: Document-Term Matrix
    # -----------------------------------------------------------------------
    logger.info("[Step 16] Generating Document-Term Matrix…")
    from src.dtm_generator import generate_dtm
    dtm_sparse, feature_names = generate_dtm(df)

    # -----------------------------------------------------------------------
    # Done
    # -----------------------------------------------------------------------
    logger.info("=" * 70)
    logger.info("Pipeline complete. Output files:")
    output_paths = [
        config.YARN_RAW_CSV,
        config.YARN_STRUCTURED_CSV,
        config.YARN_PARENTS_CSV,
        config.YARN_CLEANED_CSV,
        config.YARN_VOCAB_CSV,
        config.YARN_TOP20_CSV,
        config.YARN_TOP50_CSV,
        config.YARN_TOP100_CSV,
        config.YARN_TOP20_PNG,
        config.YARN_TOP50_PNG,
        config.YARN_VOCAB_FLAGS_CSV,
        config.YARN_DTM_CSV,
        config.YARN_DTM_SPARSE,
        config.YARN_DTM_FEATURES_CSV,
    ]
    if config.ENABLE_JIRA_API:
        output_paths.insert(1, config.YARN_ENRICHED_CSV)

    for p in output_paths:
        status = "OK" if Path(p).exists() else "MISSING"
        logger.info("  [%s] %s", status, p)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

# YARN Jira Issue Mining — Week 1

## Execution Instructions

### 1. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

**Windows**
```powershell
venv\Scripts\activate
```

**macOS / Linux**
```bash
source venv/bin/activate
```

---

### 2. Install Requirements

```bash
pip install -r requirements.txt
```

---

### 3. Install spaCy English Model

```bash
python -m spacy download en_core_web_sm
```

---

### 4. Download NLTK Resources

```python
python -c "import nltk; nltk.download('stopwords'); nltk.download('punkt')"
```

---

### 5. Configure Jira API (Optional)

Jira API enrichment is **disabled by default**.

The xlsx (`Issues.xlsx`) contains only issue keys and design-decision labels.
To retrieve full metadata (summary, description, comments, etc.),
enable the Jira API:

1. Create a `.env` file in the project root:

```
JIRA_BASE_URL=https://issues.apache.org/jira
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_api_token
```

2. Open `src/config.py` and set:

```python
ENABLE_JIRA_API = True
```

> **Note:** For Apache's public Jira instance, you may not need credentials
> for public issues. Leave `JIRA_EMAIL` and `JIRA_API_TOKEN` blank to use
> unauthenticated access.

---

### 6. Run the Pipeline

```bash
python main.py
```

---

### 7. Output Files

| File | Description |
|---|---|
| `data/raw/yarn_issues_raw.csv` | Filtered YARN issues from xlsx |
| `data/raw/yarn_issues_enriched.csv` | API-enriched issues *(if API enabled)* |
| `data/processed/yarn_issues_structured.csv` | Structured Jira-format dataset |
| `data/processed/yarn_issues_with_parents.csv` | Issues with parent info |
| `data/processed/yarn_issues_cleaned.csv` | Issues with preprocessed text |
| `data/output/yarn_vocabulary.csv` | Full vocabulary (token, frequency) |
| `data/output/yarn_top_20_tokens.csv` | Top 20 tokens |
| `data/output/yarn_top_50_tokens.csv` | Top 50 tokens |
| `data/output/yarn_top_100_tokens.csv` | Top 100 tokens |
| `data/output/yarn_top_20_terms.png` | Bar chart — top 20 terms |
| `data/output/yarn_top_50_terms.png` | Bar chart — top 50 terms |
| `data/output/yarn_vocabulary_flags.csv` | Ontology and Yarn-specific flags |
| `data/output/yarn_document_term_matrix.csv` | Dense DTM |
| `data/output/yarn_document_term_matrix_sparse.npz` | Sparse DTM |
| `data/output/yarn_dtm_features.csv` | DTM feature (term) names |

Logs are also written to `pipeline.log` in the project root.
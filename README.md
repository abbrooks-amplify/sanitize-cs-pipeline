# Customer Support Data Sanitizer

A Python pipeline that pulls recent customer support cases from Snowflake, redacts PII using the Amplify Sanitizer Service, and writes the results to a CSV for review.

---

## What it does

1. **Fetch data** — Runs `sql/fetch-cs-data.sql`, which joins various tables to aggregate the first 50 customer support interactions from the last 7 days. The results are then loaded into a DataFrame
2. **Sanitize** — Sends customer support free text to the `/bulk/sanitize` endpoint of Amplify's [sanitizer service](https://github.com/amplify-education/sanitizer-service/tree/main/src/classes) ([docs](https://sanitizer-service-devci.poc.learning.amplify.com/docs#/))
3. **Output** — Writes the original data alongside sanitized text and redacted entity types to `output/sanitized_results.csv`, which should not be committed and is ignored by `.gitignore`.

---

## Setup

### 1. Set up snowflake connection
This project uses the Snowflake VSCode extension / Snowflake CLI `connections.toml` for authentication — no credentials are stored in this repo.

`.snowflake/connections.toml` should contain the following fields

```
[connection_name]
account = "eb65335.us-east-1"
user = <username>
role = "FNC_GRP__PRODUCT__PRIVILEGED"
database = "PROD_TRANSFORMED"
warehouse = "ANALYSIS_XS_WH"
schema = "PREP_SALESFORCE"
```

Within the project root, create a `.env` file and set the name of your connection: `SNOWFLAKE_CONN=your_connection_name`

### 2. Install dependencies

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
uv run main.py
```
---

## Output

`output/sanitized_results.csv` contains all original columns from Snowflake plus:

| Column | Description |
|---|---|
| `SANITIZED_TEXT` | Original text with PII replaced by tokens |
| `SANITIZED_KEYS` | Dict mapping each token to its original value and entity type |
| `REDACTED_ENTITIES` | List of entity type keys found in `SANITIZED_KEYS` (e.g. `["PERSON", "PHONE"]`) |

Null `TEXT_PREVIEW` rows are passed through with empty sanitized columns.

---
## Useage notes
### Sanitation types

The `sanitation_type` argument in `bulk_sanitize()` controls the redaction mode. Currently set to `encrypt_tokenized` in `main()`:

| Type | Output columns |
|---|---|
| `encrypt_tokenized` | `SANITIZED_TEXT`, `SANITIZED_KEYS`, `REDACTED_ENTITIES` |
| `encrypt` | `SANITIZED_TEXT` |


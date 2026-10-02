import requests
import snowflake.connector
import os
import pandas as pd
from dotenv import load_dotenv
import json
import ast
from datetime import datetime, timezone
from collections import Counter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


API_BASE_URL        = "https://sanitizer-service-devci.poc.learning.amplify.com"
BULK_SANITIZE_PATH  = "/bulk/sanitize"

SQL_FILE    = "sql/fetch-cs-data.sql"
OUTPUT_FILE = "output/sanitized_results.csv"
CHUNK_SIZE = 100
SANITIZER_CONFIG = {
    "type_allow_list": [],
    "allow_list": [],
    "use_local_llm": False,
    "skip_llm_on_no_pii": False,
}

load_dotenv()
CONN_NAME = os.getenv("SNOWFLAKE_CONN")


def fetch_cs_data(sql: str) -> pd.DataFrame:
    """Fetch customer support data from Snowflake."""
    conn = snowflake.connector.connect(connection_name=CONN_NAME)
    try:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
    finally:
        conn.close()
    print(f"[snowflake] Fetched {len(rows)} rows.")
    return pd.DataFrame(rows)


def chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]

def parse_redaction_types(key_val) -> list[str]:
    if key_val is None:
        return []

    # Fresh from API — already a dict
    if isinstance(key_val, dict):
        return list(key_val.keys())

    # Read back from CSV — dict was serialized to a string
    if isinstance(key_val, str):
        try:
            data = ast.literal_eval(key_val)
            return list(data.keys()) if isinstance(data, dict) else []
        except (ValueError, SyntaxError):
            return []

    return []


def bulk_sanitize(df: pd.DataFrame, sanitation_type: str, config: dict) -> pd.DataFrame:
    """
    Sends non-null TEXT_PREVIEW values to the bulk sanitize endpoint in batches.
    Appends relevant sanitized text to original df, preserving order, and returns df with relevant columns.
    Appended columns depends on encryption specified in config:
        encrypt_tokenized: returns clean tokens and encrypted key dictionary in the same order as `texts`.
            New columns are "SANITIZED_TEXT", "SANITIZED_KEYS"
        encrypt: encrypted strings in the same order as `texts`.
    """
    
    mask = df["TEXT_PREVIEW"].notna()
    non_null_texts = df.loc[mask, "TEXT_PREVIEW"].tolist()

    if not non_null_texts:
        print("No non-null TEXT_PREVIEW values found. Nothing to sanitize.")
        return
    
    all_results = []

    for i, batch in enumerate(chunk(non_null_texts, CHUNK_SIZE), start=1):
        print(f"[api] Sending batch {i} ({len(batch)} items)...")
        
        payload = {
            "texts": batch,
            "task": sanitation_type,
            **config
            }

        response = requests.post(
            f"{API_BASE_URL}{BULK_SANITIZE_PATH}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )

        if not response.ok:
            print(f"[api] Error {response.status_code}: {response.text}")
            response.raise_for_status()

        batch_results = response.json()

        if not isinstance(batch_results, list):
            raise ValueError(f"Unexpected API response shape: {batch_results}")

        all_results.extend(batch_results)
        print(f"[api] Batch {i} done.")

    sanitized_df = pd.DataFrame(all_results)
    
    match sanitation_type:
        case "encrypt":
            df[["SANITIZED_TEXT"]] = None
            df.loc[mask, ["SANITIZED_TEXT"]] = sanitized_df[["text"]].values
            
        case "encrypt_tokenized":
            df[["SANITIZED_TEXT", "SANITIZED_KEYS"]] = None
            df.loc[mask, ["SANITIZED_TEXT", "SANITIZED_KEYS"]] = sanitized_df[["text", "key"]].values
            df["REDACTED_ENTITIES"] = df['SANITIZED_KEYS'].apply(parse_redaction_types)

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql = f.read()

    df = fetch_cs_data(sql)

    print(f"[info] Sending {len(df)} values to sanitizer...")
    df = bulk_sanitize(df=df, sanitation_type="encrypt_tokenized", config=SANITIZER_CONFIG)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Done. {len(df)} rows written to '{OUTPUT_FILE}'.")


if __name__ == "__main__":
    main()
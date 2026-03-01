"""
Sync exercise logs from a Notion database via the Notion API.

Fetches all pages from the configured database, maps properties to the same
schema as the Excel export, runs the cleaning pipeline, and writes
data/clean_data.csv and docs/data.json for the dashboard.

Requires: NOTION_API_KEY, NOTION_DATABASE_ID (environment or .env).
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Property name aliases (normalized to lowercase, no extra spaces) -> our column name
PROPERTY_ALIASES = {
    "exercise": "exercise",
    "name": "exercise",
    "load": "load",
    "load (kg)": "load",
    "weight": "load",
    "reps": "reps",
    "repetitions": "reps",
    "sets": "sets",
    "rpe": "rpe",
    "week": "week_num",
    "week_num": "week_num",
    "week number": "week_num",
    "notes": "notes",
    "note": "notes",
}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower())


def _load_env_file(path: Path) -> None:
    """Read a .env file and set os.environ (simple KEY=value parsing)."""
    if not path.is_file():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"").strip()
            if key:
                os.environ.setdefault(key, value)


def _load_env():
    """Load NOTION_API_KEY and NOTION_DATABASE_ID from env or .env file."""
    # Try python-dotenv first (loads from project root and/or cwd)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        load_dotenv()  # also current working directory
    except ImportError:
        # Fallback: manually read .env from project root and cwd
        _load_env_file(ROOT / ".env")
        _load_env_file(Path.cwd() / ".env")
    api_key = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")
    return api_key, database_id


def _get_database_schema(api_key: str, database_id: str) -> dict:
    """Fetch database and return mapping: our_column -> (property_id, notion_type)."""
    r = requests.get(
        f"{NOTION_API_BASE}/databases/{database_id}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    schema = {}  # our_column -> (prop_id, type)
    aliases_inv = {}  # normalized alias -> our_column
    for k, v in PROPERTY_ALIASES.items():
        aliases_inv[_norm(k)] = v
    for prop_id, prop_spec in data.get("properties", {}).items():
        name = (prop_spec.get("name") or "").strip()
        if not name:
            continue
        n = _norm(name)
        our_col = aliases_inv.get(n)
        if not our_col:
            continue
        # Exercise can come from title (page name) or from a select/multi_select "Exercise" property
        prop_type = prop_spec.get("type", "")
        if our_col == "exercise" and prop_type not in ("title", "select", "multi_select"):
            continue
        if our_col not in schema:
            schema[our_col] = (prop_id, prop_type)
        elif our_col == "exercise":
            # Prefer the "Exercise" property (select/multi_select) over the page title ("Name")
            existing_type = schema[our_col][1]
            if prop_type in ("select", "multi_select") and existing_type == "title":
                schema[our_col] = (prop_id, prop_type)
    return schema


def _extract_property_value(prop: dict, notion_type: str) -> str | float | int | None:
    """Extract a single value from a Notion property value object."""
    if not prop or notion_type not in prop:
        return None
    val = prop.get(notion_type)
    if val is None:
        return None
    if notion_type == "title":
        if isinstance(val, list):
            return "".join(t.get("plain_text", "") for t in val).strip() or None
        return None
    if notion_type == "rich_text":
        if isinstance(val, list):
            return "".join(t.get("plain_text", "") for t in val).strip() or None
        return None
    if notion_type == "number":
        return val if isinstance(val, (int, float)) else None
    if notion_type == "date":
        if isinstance(val, dict) and val.get("start"):
            return val["start"]
        return None
    if notion_type == "people":
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val[0].get("name") or val[0].get("id") or None
        return None
    if notion_type == "select":
        if isinstance(val, dict) and val.get("name"):
            return val["name"].strip()
        return None
    if notion_type == "multi_select":
        if isinstance(val, list) and val:
            names = [x.get("name", "").strip() for x in val if isinstance(x, dict) and x.get("name")]
            return ", ".join(names) if names else None
        return None
    return None


def _fetch_user_name(api_key: str, user_id: str) -> str:
    """Resolve a Notion user id to a display name."""
    r = requests.get(
        f"{NOTION_API_BASE}/users/{user_id}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
        },
        timeout=10,
    )
    if r.status_code != 200:
        return user_id
    data = r.json()
    if isinstance(data.get("name"), str):
        return data["name"].strip()
    return user_id


def _query_database(api_key: str, database_id: str) -> list[dict]:
    """Query all pages from the database with pagination."""
    all_pages = []
    start_cursor = None
    while True:
        body = {}
        if start_cursor:
            body["start_cursor"] = start_cursor
        body["sorts"] = [{"timestamp": "created_time", "direction": "ascending"}]
        r = requests.post(
            f"{NOTION_API_BASE}/databases/{database_id}/query",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        all_pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")
        if not start_cursor:
            break
    return all_pages


def _pages_to_rows(
    api_key: str,
    pages: list[dict],
    schema: dict,
) -> list[dict]:
    """Convert Notion page objects to row dicts (exercise, created_by, created_time, load, ...)."""
    user_cache = {}

    def created_by_name(created_by: dict) -> str:
        uid = (created_by or {}).get("id")
        if not uid:
            return "Unknown"
        if uid not in user_cache:
            user_cache[uid] = _fetch_user_name(api_key, uid)
        return user_cache[uid]

    rows = []
    for page in pages:
        created_time = page.get("created_time") or ""
        created_by = page.get("created_by") or {}
        by_name = created_by_name(created_by)

        row = {
            "exercise": None,
            "created_by": by_name,
            "created_time": created_time,
            "load": None,
            "reps": None,
            "sets": None,
            "rpe": None,
            "week_num": None,
            "notes": None,
        }
        props = page.get("properties") or {}
        for our_col, (prop_id, notion_type) in schema.items():
            if our_col not in row:
                continue
            prop_val = props.get(prop_id)
            v = _extract_property_value(prop_val, notion_type)
            if v is not None:
                row[our_col] = v
        rows.append(row)
    return rows


def _write_json(df: pd.DataFrame, output_path: Path) -> None:
    """Write DataFrame to JSON with NaN -> null."""
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                record[key] = None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Notion exercise database to clean_data.csv and docs/data.json")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and clean but do not write files")
    args = parser.parse_args()

    api_key, database_id = _load_env()
    if not api_key:
        env_path = ROOT / ".env"
        print("Error: NOTION_API_KEY (or NOTION_TOKEN) is not set.", file=sys.stderr)
        print(f"  Set it in the environment or in a .env file at: {env_path}", file=sys.stderr)
        return 1
    if not database_id:
        env_path = ROOT / ".env"
        print("Error: NOTION_DATABASE_ID is not set.", file=sys.stderr)
        print(f"  Set it in the environment or in a .env file at: {env_path}", file=sys.stderr)
        return 1


    print("Fetching database schema...")
    schema = _get_database_schema(api_key, database_id)
    if "exercise" not in schema:
        print("Error: Database has no property that maps to 'exercise' (e.g. a Title column named Exercise).", file=sys.stderr)
        return 1

    print("Querying database...")
    pages = _query_database(api_key, database_id)
    print(f"Fetched {len(pages)} pages.")

    rows = _pages_to_rows(api_key, pages, schema)
    df = pd.DataFrame(rows)

    sys.path.insert(0, str(ROOT))
    from clean_notion_export import clean_export_df

    cleaned = clean_export_df(df)
    print(f"After cleaning: {len(cleaned)} rows.")

    if args.dry_run:
        print("Dry run: skipping file writes.")
        return 0

    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / "clean_data.csv"
    cleaned.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"Wrote {csv_path}")

    json_path = ROOT / "docs" / "data.json"
    _write_json(cleaned, json_path)
    print(f"Wrote {json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

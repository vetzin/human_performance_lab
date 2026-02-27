"""
Clean notion_export.xlsx exercise logs for dashboard use.

Input:  data/notion_export.xlsx
Output: data/clean_data.csv

Pipeline:
1. Normalize headers, drop empty rows (no exercise)
2. Parse dates, load, reps with per-set handling
3. Cross-reference load/reps/sets — expand single values to match multi
4. Compute 1RM estimates (Epley, Brzycki, Lombardi) + average
5. Compute total volume, session IDs, data quality flags
6. Export clean CSV
"""

import re
import pandas as pd
from pathlib import Path

MAX_SANE_REPS = 100
MAX_SANE_LOAD = 600


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_values(raw, max_sane: float | None = None) -> list[float]:
    """Parse raw cell into a list of floats.

    Handles: single numbers, 'Nkg' suffixes, comma / hyphen / space separated
    lists. Returns empty list for unparseable or missing values.
    """
    if pd.isna(raw):
        return []
    s = str(raw).strip()
    if not s:
        return []
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return []
    s = s.lower().replace("kg", "").strip()
    s = re.sub(r"(?<=\d)\s*-\s*(?=\d)", ",", s)
    s = re.sub(r"\s+", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    vals: list[float] = []
    for p in parts:
        try:
            v = float(p)
            if max_sane is not None and abs(v) > max_sane:
                return []
            vals.append(v)
        except ValueError:
            pass
    return vals


def fmt_val(v: float) -> str:
    """Integer string when whole, one-decimal otherwise."""
    return str(int(v)) if v == int(v) else f"{v:.1f}"


# ---------------------------------------------------------------------------
# 1-Rep-Max estimation formulas
# ---------------------------------------------------------------------------

def _e1rm_epley(w: float, r: float) -> float | None:
    """Epley: W × (1 + r/30)"""
    if w <= 0 or r <= 0:
        return None
    return w if r == 1 else round(w * (1 + r / 30), 1)


def _e1rm_brzycki(w: float, r: float) -> float | None:
    """Brzycki: W × 36 / (37 − r)  (valid for r < 37)"""
    if w <= 0 or r <= 0:
        return None
    if r == 1:
        return w
    if r >= 37:
        return None
    return round(w * 36 / (37 - r), 1)


def _e1rm_lombardi(w: float, r: float) -> float | None:
    """Lombardi: W × r^0.10"""
    if w <= 0 or r <= 0:
        return None
    return w if r == 1 else round(w * (r ** 0.10), 1)


_E1RM_FNS = [
    ("epley", _e1rm_epley),
    ("brzycki", _e1rm_brzycki),
    ("lombardi", _e1rm_lombardi),
]


def best_e1rm(load_vals: list[float], reps_vals: list[float]) -> dict:
    """Best (max) estimated 1RM across all set pairs, plus average."""
    best: dict[str, float | None] = {k: None for k, _ in _E1RM_FNS}
    for w, r in zip(load_vals, reps_vals):
        for key, fn in _E1RM_FNS:
            val = fn(w, r)
            if val is not None and (best[key] is None or val > best[key]):
                best[key] = val
    vals = [v for v in best.values() if v is not None]
    best["avg"] = round(sum(vals) / len(vals), 1) if vals else None
    return best


# ---------------------------------------------------------------------------
# Row-level cleaning
# ---------------------------------------------------------------------------

def clean_row(raw_load, raw_reps, raw_sets) -> dict:
    """Parse and cross-reference load / reps / sets for one exercise row."""
    load_vals = parse_values(raw_load, max_sane=MAX_SANE_LOAD)
    reps_vals = parse_values(raw_reps, max_sane=MAX_SANE_REPS)
    sets_raw = int(float(raw_sets)) if pd.notna(raw_sets) else None

    num_sets = max(len(load_vals), len(reps_vals), sets_raw or 0) or None

    load_is_multi = len(load_vals) > 1
    reps_is_multi = len(reps_vals) > 1
    either_multi = load_is_multi or reps_is_multi

    # Expand single side to match multi side
    if either_multi and num_sets and num_sets > 1:
        if len(load_vals) == 1:
            load_vals = load_vals * num_sets
        if len(reps_vals) == 1:
            reps_vals = reps_vals * num_sets

    # Pad mismatched lengths with last value
    if len(load_vals) > 1 and len(reps_vals) > 1:
        target = max(len(load_vals), len(reps_vals))
        while len(load_vals) < target:
            load_vals.append(load_vals[-1])
        while len(reps_vals) < target:
            reps_vals.append(reps_vals[-1])

    # --- Load ---
    load_per_set = (
        ",".join(fmt_val(v) for v in load_vals) if len(load_vals) > 1 else None
    )
    load_avg = round(sum(load_vals) / len(load_vals), 1) if load_vals else None
    load_min = min(load_vals) if load_vals else None
    load_max = max(load_vals) if load_vals else None

    # --- Reps ---
    if either_multi and len(reps_vals) > 1:
        reps_per_set = ",".join(fmt_val(v) for v in reps_vals)
        reps_total = sum(reps_vals)
        reps_avg = round(reps_total / len(reps_vals), 1)
    elif reps_vals:
        reps_per_set = None
        reps_total = reps_vals[0] * (num_sets or 1)
        reps_avg = reps_vals[0]
    else:
        reps_per_set = None
        reps_total = None
        reps_avg = None

    sets = num_sets

    # --- Volume = Σ(load_i × reps_i) across all sets ---
    if load_vals and reps_vals and len(load_vals) == len(reps_vals) and len(load_vals) > 1:
        volume = round(sum(w * r for w, r in zip(load_vals, reps_vals)), 1)
    elif load_avg is not None and reps_total is not None:
        volume = round(load_avg * reps_total, 1)
    else:
        volume = None

    # --- 1RM ---
    e1rm = best_e1rm(load_vals, reps_vals) if load_vals and reps_vals else {}

    # --- Data quality flags ---
    flags: list[str] = []
    raw_load_str = str(raw_load).strip() if pd.notna(raw_load) else ""
    raw_reps_str = str(raw_reps).strip() if pd.notna(raw_reps) else ""
    if raw_load_str and not load_vals:
        flags.append("unparseable_load")
    if raw_reps_str and not reps_vals:
        flags.append("unparseable_reps")
    if not raw_load_str and not load_vals:
        flags.append("missing_load")
    if not raw_reps_str and not reps_vals:
        flags.append("missing_reps")
    orig_load_len = len(parse_values(raw_load, MAX_SANE_LOAD))
    orig_reps_len = len(parse_values(raw_reps, MAX_SANE_REPS))
    if orig_load_len > 1 and orig_reps_len > 1 and orig_load_len != orig_reps_len:
        flags.append("load_reps_count_mismatch")
    if sets_raw and num_sets and num_sets != sets_raw:
        flags.append(f"sets_adjusted_{sets_raw}_to_{num_sets}")

    return {
        "sets": int(sets) if sets else None,
        "load_per_set": load_per_set,
        "load_avg": load_avg,
        "load_min": load_min,
        "load_max": load_max,
        "reps_per_set": reps_per_set,
        "reps_avg": reps_avg,
        "reps_total": int(reps_total) if reps_total is not None else None,
        "total_volume": volume,
        "e1rm_epley": e1rm.get("epley"),
        "e1rm_brzycki": e1rm.get("brzycki"),
        "e1rm_lombardi": e1rm.get("lombardi"),
        "e1rm_avg": e1rm.get("avg"),
        "data_quality_flag": "|".join(flags) if flags else None,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    data_dir = Path(__file__).resolve().parent / "data"
    input_path = data_dir / "notion_export.xlsx"
    output_path = data_dir / "clean_data.csv"

    df = pd.read_excel(input_path)

    # 1. Normalize headers
    df.columns = [re.sub(r"\s+", "_", c.strip().lower()) for c in df.columns]

    # 2. Drop rows with no exercise (empty Notion rows)
    df = df.dropna(subset=["exercise"]).reset_index(drop=True)

    # 3. Athlete name (strip whitespace), drop original "name"
    df["athlete"] = df["created_by"].str.strip()

    # 4. Dates
    df["date"] = pd.to_datetime(df["created_time"], format="mixed", errors="coerce")
    df["date_only"] = df["date"].dt.strftime("%Y-%m-%d")
    df["day_of_week"] = df["date"].dt.day_name()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 5. Exercise name cleanup (strip whitespace)
    df["exercise"] = df["exercise"].str.strip()

    # 6. Process load / reps / sets
    cleaned = df.apply(
        lambda r: clean_row(r["load"], r["reps"], r["sets"]),
        axis=1,
        result_type="expand",
    )
    for col in cleaned.columns:
        df[col] = cleaned[col]

    # 7. Session ID: deterministic from athlete + date
    df["session_id"] = (
        df["athlete"].str.lower().str.replace(" ", "_", regex=False)
        + "_"
        + df["date_only"].str.replace("-", "", regex=False)
    )

    # 8. Sort and assign row ID
    df = df.sort_values(["date", "athlete", "exercise"]).reset_index(drop=True)
    df["row_id"] = range(1, len(df) + 1)

    # 9. Select output columns
    out_cols = [
        "row_id",
        "session_id",
        "athlete",
        "date",
        "date_only",
        "day_of_week",
        "week_num",
        "exercise",
        "sets",
        "load_per_set",
        "load_avg",
        "load_min",
        "load_max",
        "reps_per_set",
        "reps_avg",
        "reps_total",
        "rpe",
        "e1rm_epley",
        "e1rm_brzycki",
        "e1rm_lombardi",
        "e1rm_avg",
        "total_volume",
        "notes",
        "data_quality_flag",
    ]
    result = df[[c for c in out_cols if c in df.columns]]

    result.to_csv(output_path, index=False, encoding="utf-8")
    print(f"Wrote {result.shape[0]} rows x {result.shape[1]} cols -> {output_path}")
    return result


if __name__ == "__main__":
    main()

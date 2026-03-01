"""
Clean notion_export.xlsx exercise logs for dashboard use.

Input:  data/notion_export.xlsx
Output: data/clean_data.csv

Pipeline:
1. Normalize headers, drop empty rows (no exercise)
2. Parse dates, load, reps with per-set handling
3. Always expand per-set strings — single values fill across all sets
4. RPE-adjusted 1RM via Reps-In-Reserve (RIR) method (Zourdos et al., 2016)
   - RIR = 10 - RPE; if RPE missing, assume RPE 9 (RIR=1, not stored)
   - Effective reps = actual_reps + RIR for 1RM estimation
   - Average of Epley, Brzycki, Lombardi formulas; best set taken
5. Compute total volume, session IDs, data quality flags
6. Export clean CSV
"""

import re
import pandas as pd
from pathlib import Path

MAX_SANE_REPS = 100
MAX_SANE_LOAD = 600
DEFAULT_RPE = 9.0   # assumed when RPE not recorded — never written to output


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_values(raw, max_sane: float | None = None) -> list[float]:
    """Parse raw cell into a list of floats.

    Handles single numbers, 'Nkg' suffixes, comma / hyphen / space lists.
    Returns [] for unparseable or missing values.
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
# RPE-adjusted 1RM
# ---------------------------------------------------------------------------
# Source: Zourdos MC, et al. (2016). A Novel Percent 1-RM Algorithm for
# Resistance Exercise Based on the Repetitions-in-Reserve (RIR) Continuum.
# J Strength Cond Res, 30(1):267-275.
#
# Principle: RPE on the 0-10 scale implies RIR = 10 - RPE.
# Adding RIR to actual reps gives the *estimated* maximum reps possible at
# that load, which feeds standard load-reps 1RM formulas far more accurately
# than raw reps alone (which would underestimate 1RM for sub-maximal sets).

def _rpe_to_rir(rpe: float | None) -> float:
    """Reps In Reserve from RPE. Falls back to DEFAULT_RPE silently."""
    effective_rpe = rpe if (rpe is not None and not pd.isna(rpe)) else DEFAULT_RPE
    effective_rpe = max(1.0, min(10.0, effective_rpe))
    return 10.0 - effective_rpe


def _e1rm_epley(w: float, r: float) -> float | None:
    if w <= 0 or r <= 0:
        return None
    return w if r == 1 else round(w * (1 + r / 30), 1)


def _e1rm_brzycki(w: float, r: float) -> float | None:
    if w <= 0 or r <= 0 or r >= 37:
        return None
    return w if r == 1 else round(w * 36 / (37 - r), 1)


def _e1rm_lombardi(w: float, r: float) -> float | None:
    if w <= 0 or r <= 0:
        return None
    return w if r == 1 else round(w * (r ** 0.10), 1)


_E1RM_FNS = [_e1rm_epley, _e1rm_brzycki, _e1rm_lombardi]


def compute_e1rm_avg(load_vals: list[float], reps_vals: list[float], rpe: float | None) -> float | None:
    """Best RPE-adjusted estimated 1RM across all sets, averaged over three formulas.

    For each set pair (load, reps) the effective reps = reps + RIR (Zourdos 2016).
    Best set (highest estimate) is selected; Epley/Brzycki/Lombardi are averaged.
    """
    if not load_vals or not reps_vals:
        return None
    rir = _rpe_to_rir(rpe)
    best: float | None = None
    for w, r in zip(load_vals, reps_vals):
        eff_r = r + rir
        estimates = [fn(w, eff_r) for fn in _E1RM_FNS]
        estimates = [v for v in estimates if v is not None]
        if not estimates:
            continue
        candidate = round(sum(estimates) / len(estimates), 1)
        if best is None or candidate > best:
            best = candidate
    return best


# ---------------------------------------------------------------------------
# Row-level cleaning
# ---------------------------------------------------------------------------

def clean_row(raw_load, raw_reps, raw_sets, raw_rpe) -> dict:
    """Parse and cross-reference load / reps / sets / rpe for one exercise row."""
    load_vals = parse_values(raw_load, max_sane=MAX_SANE_LOAD)
    reps_vals = parse_values(raw_reps, max_sane=MAX_SANE_REPS)
    sets_raw = int(float(raw_sets)) if pd.notna(raw_sets) else None
    rpe = float(raw_rpe) if pd.notna(raw_rpe) else None

    num_sets = max(len(load_vals), len(reps_vals), sets_raw or 0) or None

    # Expand single-value sides to fill all sets (always, not just when the other is multi)
    if num_sets and num_sets > 1:
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

    # --- Load per set (always populated when sets >= 1 and load available) ---
    if load_vals:
        load_per_set = ",".join(fmt_val(v) for v in load_vals)
        load_avg = round(sum(load_vals) / len(load_vals), 1)
        load_min = min(load_vals)
        load_max = max(load_vals)
    else:
        load_per_set = None
        load_avg = None
        load_min = None
        load_max = None

    # --- Reps per set (always populated when sets >= 1 and reps available) ---
    if reps_vals:
        reps_per_set = ",".join(fmt_val(v) for v in reps_vals)
        reps_total = int(sum(reps_vals))
        reps_avg = round(sum(reps_vals) / len(reps_vals), 1)
    else:
        reps_per_set = None
        reps_total = None
        reps_avg = None

    sets = num_sets

    # --- Volume = Σ(load_i × reps_i) across all sets ---
    if load_vals and reps_vals and len(load_vals) == len(reps_vals):
        volume = round(sum(w * r for w, r in zip(load_vals, reps_vals)), 1)
    elif load_avg is not None and reps_total is not None:
        volume = round(load_avg * reps_total, 1)
    else:
        volume = None

    # --- RPE-adjusted 1RM ---
    e1rm_avg = compute_e1rm_avg(load_vals, reps_vals, rpe)

    # --- Data quality flags ---
    flags: list[str] = []
    raw_load_str = str(raw_load).strip() if pd.notna(raw_load) else ""
    raw_reps_str = str(raw_reps).strip() if pd.notna(raw_reps) else ""
    if raw_load_str and not load_vals:
        flags.append("unparseable_load")
    if raw_reps_str and not reps_vals:
        flags.append("unparseable_reps")
    if not raw_load_str:
        flags.append("missing_load")
    if not raw_reps_str:
        flags.append("missing_reps")
    orig_load_len = len(parse_values(raw_load, MAX_SANE_LOAD))
    orig_reps_len = len(parse_values(raw_reps, MAX_SANE_REPS))
    if orig_load_len > 1 and orig_reps_len > 1 and orig_load_len != orig_reps_len:
        flags.append("load_reps_count_mismatch")
    if sets_raw and num_sets and num_sets != sets_raw:
        flags.append(f"sets_adjusted_{sets_raw}_to_{num_sets}")

    return {
        "sets": int(sets) if sets else None,
        "reps_avg": reps_avg,
        "load_avg": load_avg,
        "reps_per_set": reps_per_set,
        "load_per_set": load_per_set,
        "reps_total": reps_total,
        "total_volume": volume,
        "load_min": load_min,
        "load_max": load_max,
        "e1rm_avg": e1rm_avg,
        "data_quality_flag": "|".join(flags) if flags else None,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def clean_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full cleaning pipeline on a DataFrame (no file I/O).

    Expects columns compatible with Notion export: exercise, created_by,
    created_time, load, reps, sets, rpe, and optionally week_num, notes.
    Returns the cleaned DataFrame with standard column order.
    """
    # 1. Normalize headers
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", str(c).strip().lower()) for c in df.columns]

    # 2. Drop rows with no exercise (empty Notion rows)
    df = df.dropna(subset=["exercise"]).reset_index(drop=True)
    if df.empty:
        return df

    # 3. Athlete name
    df["athlete"] = df["created_by"].astype(str).str.strip()

    # 4. Dates
    df["date"] = pd.to_datetime(df["created_time"], format="mixed", errors="coerce")
    df["date_only"] = df["date"].dt.strftime("%Y-%m-%d")
    df["day_of_week"] = df["date"].dt.day_name()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 5. Exercise name cleanup
    df["exercise"] = df["exercise"].astype(str).str.strip()

    # 6. Process load / reps / sets / rpe (ensure columns exist for apply)
    for col in ("load", "reps", "sets", "rpe"):
        if col not in df.columns:
            df[col] = None
    cleaned = df.apply(
        lambda r: clean_row(r["load"], r["reps"], r["sets"], r["rpe"]),
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

    # 9. Column order: context → metrics → extras → IDs
    out_cols = [
        "date_only",
        "day_of_week",
        "athlete",
        "exercise",
        "sets",
        "reps_avg",
        "load_avg",
        "reps_per_set",
        "load_per_set",
        "reps_total",
        "total_volume",
        "load_min",
        "load_max",
        "rpe",
        "e1rm_avg",
        "week_num",
        "notes",
        "data_quality_flag",
        "date",
        "session_id",
        "row_id",
    ]
    return df[[c for c in out_cols if c in df.columns]]


def main():
    data_dir = Path(__file__).resolve().parent / "data"
    input_path = data_dir / "notion_export.xlsx"
    output_path = data_dir / "clean_data.csv"

    df = pd.read_excel(input_path)
    result = clean_export_df(df)
    result.to_csv(output_path, index=False, encoding="utf-8")
    print(f"Wrote {result.shape[0]} rows x {result.shape[1]} cols -> {output_path}")
    return result


if __name__ == "__main__":
    main()

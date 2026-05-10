"""
Fiscal year utilities for Argentine insurance companies.

Fiscal year: July 1 – June 30.
SSN quarterly codes (YYYY-QN where N = calendar quarter):
  Q3 (Jul-Sep) → FY = year+1, month  3 of FY
  Q4 (Oct-Dec) → FY = year+1, month  6 of FY
  Q1 (Jan-Mar) → FY = year,   month  9 of FY
  Q2 (Apr-Jun) → FY = year,   month 12 of FY  ← annual closing
"""
from __future__ import annotations
import pandas as pd

_Q_TO_FY = {
    3: (1,  3, False),   # (fy_offset, months, is_close)
    4: (1,  6, False),
    1: (0,  9, False),
    2: (0, 12, True),
}

# Calendar quarter → human start/end month labels
_Q_DATE_RANGE = {
    3: ("Jul", "Sep"),
    4: ("Jul", "Dic"),
    1: ("Jul", "Mar"),
    2: ("Jul", "Jun"),
}


def parse_quarter(q_label: str) -> tuple[int, int]:
    """'2024-Q3' → (2024, 3)"""
    year, qpart = q_label.split("-Q")
    return int(year), int(qpart)


def fiscal_info(q_label: str) -> dict:
    """
    Return a dict with:
      fy          – fiscal year (int, e.g. 2025)
      months      – months elapsed since Jul 1 (3 / 6 / 9 / 12)
      is_close    – True only for the June 30 annual closing
      short_label – compact label e.g. "EJ2025 · 6m"
      long_label  – verbose  e.g. "EJ2025 · 6 meses (Jul–Dic 2024)"
      fy_start_year – calendar year when the fiscal year started
    """
    year, q = parse_quarter(q_label)
    fy_offset, months, is_close = _Q_TO_FY[q]
    fy = year + fy_offset
    fy_start_year = fy - 1  # e.g. FY2025 starts in 2024

    start_m, end_m = _Q_DATE_RANGE[q]
    # start calendar year is always fy_start_year; end year depends on quarter
    end_year = year  # Q3→same year, Q4→same year, Q1→next year, Q2→next year
    # actually start_year of the range is always fy_start_year
    date_range = f"{start_m} {fy_start_year}–{end_m} {year}"

    if is_close:
        short = f"EJ{fy} · Cierre"
        long  = f"EJ{fy} · Cierre anual ({date_range})"
    else:
        short = f"EJ{fy} · {months}m"
        long  = f"EJ{fy} · {months} meses ({date_range})"

    return dict(
        fy=fy,
        months=months,
        is_close=is_close,
        short_label=short,
        long_label=long,
        fy_start_year=fy_start_year,
    )


def enrich_quarters(df: pd.DataFrame) -> pd.DataFrame:
    """Add fy, months_elapsed, is_close, fy_label columns to the DataFrame."""
    infos = {q: fiscal_info(q) for q in df["quarter"].unique()}
    df = df.copy()
    df["fy"]             = df["quarter"].map(lambda q: infos[q]["fy"])
    df["months_elapsed"] = df["quarter"].map(lambda q: infos[q]["months"])
    df["is_close"]       = df["quarter"].map(lambda q: infos[q]["is_close"])
    df["fy_label"]       = df["quarter"].map(lambda q: infos[q]["short_label"])
    return df


def same_position_prior_year(q_label: str, all_quarters: list[str]) -> str | None:
    """
    Return the quarter label from the PREVIOUS fiscal year with the same
    months_elapsed (e.g. EJ2025 6m → EJ2024 6m).
    """
    info = fiscal_info(q_label)
    target_fy     = info["fy"] - 1
    target_months = info["months"]
    for q in all_quarters:
        i = fiscal_info(q)
        if i["fy"] == target_fy and i["months"] == target_months:
            return q
    return None


def prior_within_fy(q_label: str, all_quarters: list[str]) -> str | None:
    """
    Return the previous quarter within the same fiscal year
    (e.g. EJ2025 6m → EJ2025 3m), or None if it's the first quarter.
    """
    info = fiscal_info(q_label)
    prev_months = info["months"] - 3
    if prev_months == 0:
        return None
    for q in all_quarters:
        i = fiscal_info(q)
        if i["fy"] == info["fy"] and i["months"] == prev_months:
            return q
    return None


def decumulate_pnl(current: dict, prior: dict) -> dict:
    """
    Subtract prior cumulative P&L from current to get the standalone quarter.
    Both dicts must be outputs of pnl.compute_pnl().
    """
    keys = [
        "tech_rev", "fin_rev", "extra_rev", "gross_rev",
        "tech_cost", "fin_cost", "extra_loss", "gross_exp",
        "pretax", "tax", "third", "net",
    ]
    return {k: current[k] - prior[k] for k in keys}


def quarter_options(all_quarters: list[str]) -> list[dict]:
    """
    Return a list of dicts for display in a UI selector, sorted chronologically.
    Each dict has: quarter, short_label, long_label, fy, months, is_close.
    """
    opts = []
    for q in sorted(all_quarters):
        info = fiscal_info(q)
        opts.append({"quarter": q, **info})
    return opts

"""
Ranking tab data prep: builds per-indicator ranking tables with Δ-rank
vs prior fiscal-year same-position quarter.

Inputs come from `metrics.compute_with_yoy(df, quarter)`.
"""
from __future__ import annotations
import pandas as pd


# Default sort direction per indicator code.
# True  = ascending  → rank 1 means LOWEST value (e.g. lowest expense ratio = best operator)
# False = descending → rank 1 means HIGHEST value (e.g. largest market share)
DEFAULT_ASCENDING: dict[str, bool] = {
    "A":  False,   # market share
    "B":  True,    # cantidad de juicios — fewer is better
    "C":  False,   # créditos / activos (interpretation ambiguous; default desc)
    "D":  False,   # liquidity
    "D'": False,   # liquidity ampliada
    "E":  False,   # cobertura técnica
    "F":  False,   # inversiones / activos
    "G":  False,   # superávit / capital requerido — higher is better
    "H":  False,   # disp+inv / compromisos exigibles — higher is better
    "I":  False,   # % cesión (interpretation ambiguous; default desc)
    "J":  True,    # siniestralidad — lower is better (loss ratio)
    "K":  True,    # gastos producción — lower is better
    "L":  True,    # gastos explotación — lower is better
    "M":  True,    # gastos totales — lower is better
    "N":  False,   # resultado / primas — higher is better
}


def build_ranking(
    indicators: pd.DataFrame,
    indicator_code: str,
    ascending: bool | None = None,
) -> pd.DataFrame:
    """
    Return one row per company with current value, prior value, current rank,
    prior rank, and Δrank, sorted by current rank ascending (rank 1 first).

    Δrank > 0  ⇒ company moved UP (improved standing — rank number decreased)
    Δrank < 0  ⇒ company moved DOWN
    """
    if ascending is None:
        ascending = DEFAULT_ASCENDING.get(indicator_code, False)

    sub = indicators.loc[indicators["indicator"] == indicator_code].copy()

    sub["rank"] = sub["value"].rank(
        method="min", ascending=ascending, na_option="bottom"
    ).astype("Int64")
    sub["rank_prior"] = sub["value_prior"].rank(
        method="min", ascending=ascending, na_option="bottom"
    ).astype("Int64")
    sub["delta_rank"] = sub["rank_prior"] - sub["rank"]

    return sub.sort_values(
        ["rank", "razon_social"], na_position="last"
    ).reset_index(drop=True)


def build_wide_table(indicators: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot the long-format indicator table to wide: one row per company,
    one column per indicator.
    """
    wide = indicators.pivot_table(
        index=["cod_cia", "razon_social"],
        columns="indicator",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    return wide


def delta_rank_arrow(delta: int | float | None) -> str:
    """↑3 / ↓2 / — / · (no prior)"""
    if delta is None or pd.isna(delta):
        return "·"
    d = int(delta)
    if d == 0:
        return "—"
    return f"↑{d}" if d > 0 else f"↓{-d}"

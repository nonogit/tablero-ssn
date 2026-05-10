"""
Peer-benchmark utilities: percentile rank within a peer set, and
nearest-peers detection using normalized Euclidean distance over indicators.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def percentile_rank(
    values: pd.Series,
    target: float | None,
    ascending: bool = False,
) -> float | None:
    """
    Percentile rank (0–100) of `target` within `values`.

    `ascending=False` (default, "higher is better"): 100 means target is the
    best in the population (no peers exceed it).
    `ascending=True` ("lower is better"): inverted.
    """
    if target is None or pd.isna(target):
        return None
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if len(vals) == 0:
        return None
    if ascending:
        return 100.0 * (vals > target).sum() / len(vals)
    return 100.0 * (vals < target).sum() / len(vals)


def quartile_label(pct: float | None) -> str:
    if pct is None or pd.isna(pct):
        return "—"
    if pct >= 75:
        return "Q1 (top)"
    if pct >= 50:
        return "Q2"
    if pct >= 25:
        return "Q3"
    return "Q4 (bottom)"


def nearest_peers(
    ind_wide: pd.DataFrame,
    focus_cod: str,
    top_n: int = 5,
    indicators: list[str] | None = None,
) -> pd.DataFrame:
    """
    Return the `top_n` companies most similar to `focus_cod`, ranked by
    z-score-normalized Euclidean distance.

    `ind_wide` must be a DataFrame indexed by cod_cia with one column per
    indicator. Pass `indicators=[...]` to restrict the distance metric to a
    subset (otherwise all numeric columns are used).
    """
    if focus_cod not in ind_wide.index:
        return pd.DataFrame(columns=["cod_cia", "distance"])

    cols = indicators if indicators is not None else [
        c for c in ind_wide.columns if pd.api.types.is_numeric_dtype(ind_wide[c])
    ]
    sub = ind_wide[cols].copy()

    # Drop columns that are entirely NaN within the population
    sub = sub.dropna(axis=1, how="all")
    if sub.shape[1] == 0:
        return pd.DataFrame(columns=["cod_cia", "distance"])

    # Z-score normalize, then fill remaining NaN with column mean (=0 after z)
    means = sub.mean()
    stds = sub.std().replace(0, 1.0)
    z = (sub - means) / stds
    z = z.fillna(0.0)

    focus_vec = z.loc[focus_cod]
    distances = np.sqrt(((z - focus_vec) ** 2).sum(axis=1))
    distances = distances.drop(focus_cod)

    out = (
        distances.nsmallest(top_n)
                 .reset_index()
                 .rename(columns={0: "distance"})
    )
    out.columns = ["cod_cia", "distance"]
    return out

"""
SSN-official indicators per company, in long format.

Indicator definitions and account-code mappings are documented in
`docs/account_mapping.md`. Run this module directly to validate computed
values against the Excel oracle (Input/ssn_202512_indicadores_mercado1.xlsx)
for ALLIANZ 2025-Q4.
"""
from __future__ import annotations
import pandas as pd
from pathlib import Path

from .fiscal import same_position_prior_year, fiscal_info
from .external_indicators import EXTERNAL_DEFS, load_external_long


# ── account-code aggregation keys ─────────────────────────────────────────────
# Trailing dot is required to avoid '1.01.' matching against '1.10.'.

_L2_KEYS = {
    "activo":      "1.",
    "disp":        "1.01.",
    "inv":         "1.02.",
    "creditos":    "1.03.",
    "inmuebles":   "1.04.",
    "pasivo":      "2.",
    "compr_tec":   "2.02.",
    "pn":          "3.",
    "ganancias":   "5.",
    "perdidas":    "4.",
}

_L3_KEYS = {
    "deudas_aseg":         "2.01.01.",
    "primas_y_recargos":   "5.01.01.",
    "anulaciones":         "4.01.04.",
    "primas_cedidas":      "4.01.03.",
    "siniestros":          "4.01.01.",
    "gastos_prod":         "4.01.06.",
    "gastos_exp":          "4.01.07.",
    "gastos_a_reaseg":     "5.01.03.",
    "creditos_recuperos":  "5.01.04.",
}


# ── aggregate builder ─────────────────────────────────────────────────────────

def _company_totals(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """Filter to non-subramo (company-aggregate) rows for the given quarter."""
    mask = (df["quarter"] == quarter) & (
        df["desc_subramo"].isna() | (df["desc_subramo"] == "")
    )
    return df.loc[mask, ["cod_cia", "cod_cuenta", "nivel", "importe"]]


def _agg_by_prefix(df: pd.DataFrame, prefix: str, level: int) -> pd.Series:
    mask = (df["nivel"] == level) & df["cod_cuenta"].str.startswith(prefix)
    return df.loc[mask].groupby("cod_cia")["importe"].sum()


def build_aggregates(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """
    Wide DataFrame indexed by cod_cia with one column per aggregate key.
    Missing (company, key) pairs are filled with 0.0.
    """
    sub = _company_totals(df, quarter)
    out = pd.DataFrame(index=sorted(sub["cod_cia"].unique()))
    for name, prefix in _L2_KEYS.items():
        out[name] = _agg_by_prefix(sub, prefix, level=2)
    for name, prefix in _L3_KEYS.items():
        out[name] = _agg_by_prefix(sub, prefix, level=3)
    return out.fillna(0.0)


# ── indicator formulas ────────────────────────────────────────────────────────

def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return (100.0 * num / den).where(den != 0)


def _primas_emitidas(a: pd.DataFrame) -> pd.Series:
    return a["primas_y_recargos"] - a["anulaciones"]


def _ind_A(a: pd.DataFrame) -> pd.Series:
    pe = _primas_emitidas(a)
    market_total = pe.sum()
    return _safe_div(pe, pd.Series(market_total, index=a.index))


def _ind_C(a):  return _safe_div(a["creditos"], a["activo"])
def _ind_D(a):  return _safe_div(a["disp"] + a["inv"], a["deudas_aseg"])
def _ind_Dp(a): return _safe_div(a["disp"] + a["inv"] + a["inmuebles"], a["deudas_aseg"])
def _ind_E(a):  return _safe_div(a["disp"] + a["inv"] + a["inmuebles"],
                                  a["deudas_aseg"] + a["compr_tec"])
def _ind_F(a):  return _safe_div(a["inv"] + a["inmuebles"], a["activo"])

def _ind_I(a):  return _safe_div(a["primas_cedidas"], _primas_emitidas(a))
def _ind_K(a):  return _safe_div(a["gastos_prod"], _primas_emitidas(a))
def _ind_L(a):  return _safe_div(a["gastos_exp"], _primas_emitidas(a))
def _ind_M(a):
    gastos_totales = a["gastos_prod"] + a["gastos_exp"] - a["gastos_a_reaseg"]
    return _safe_div(gastos_totales, _primas_emitidas(a))
def _ind_N(a):
    net = a["ganancias"] - a["perdidas"]
    return _safe_div(net, _primas_emitidas(a))


# code, name, category, status, fn
# Indicators computed from the balance parquet.
INDICATOR_DEFS: list[tuple[str, str, str, str, callable]] = [
    ("A",  "% Producción Total",                              "patrimonial", "tunable",     _ind_A),
    ("C",  "% Créditos / Activos",                            "patrimonial", "exact",       _ind_C),
    ("D",  "(Disp+Inv) / Deudas c/Aseg.",                     "patrimonial", "exact",       _ind_D),
    ("D'", "(Disp+Inv+Inmuebles) / Deudas c/Aseg.",           "patrimonial", "exact",       _ind_Dp),
    ("E",  "Cobertura Técnica",                               "patrimonial", "approximate", _ind_E),
    ("F",  "% (Inv+Inmuebles) / Activos",                     "patrimonial", "exact",       _ind_F),
    ("I",  "% Cesión",                                        "gestion",     "close",       _ind_I),
    ("K",  "% Gastos Producción / Primas Emitidas",           "gestion",     "close",       _ind_K),
    ("L",  "% Gastos Explotación / Primas Emitidas",          "gestion",     "close",       _ind_L),
    ("M",  "% Gastos Totales / Primas Emitidas",              "gestion",     "close",       _ind_M),
    ("N",  "% Resultado / Primas Emitidas",                   "gestion",     "close",       _ind_N),
]

# Combined indicator list including external (Excel-only) indicators.
# UI consumers iterate this for the full set; the source attribute tells
# them whether data is available for arbitrary quarters or only when the
# corresponding Excel report exists.
ALL_INDICATOR_DEFS: list[tuple[str, str, str, str, str]] = [
    (code, name, cat, status, "parquet")
    for code, name, cat, status, _fn in INDICATOR_DEFS
] + [
    (code, name, cat, "external", "excel")
    for code, name, cat in EXTERNAL_DEFS
]


# ── public API ────────────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """
    Compute every SSN-official indicator for every company in `quarter`.

    Parquet-derived indicators are computed from balance accounts; external
    indicators (B, G, H, J) are pulled from the SSN-published Excel report
    for the matching quarter, if available.

    Returns long-format columns:
        cod_cia, razon_social, quarter, indicator, name, category, status,
        source, value

    `value` is in percentage units for ratios, raw count for B (juicios).
    """
    a = build_aggregates(df, quarter)

    pieces = []
    for code, name, category, status, fn in INDICATOR_DEFS:
        s = fn(a)
        pieces.append(pd.DataFrame({
            "cod_cia":   s.index,
            "indicator": code,
            "name":      name,
            "category":  category,
            "status":    status,
            "source":    "parquet",
            "value":     s.values,
        }))
    out = pd.concat(pieces, ignore_index=True)

    # Merge external (Excel-sourced) indicators for this quarter
    ext_long = load_external_long(df, quarter)
    if not ext_long.empty:
        ext_meta = {code: (name, cat) for code, name, cat in EXTERNAL_DEFS}
        ext_long = ext_long.copy()
        ext_long["name"]     = ext_long["indicator"].map(lambda c: ext_meta[c][0])
        ext_long["category"] = ext_long["indicator"].map(lambda c: ext_meta[c][1])
        ext_long["status"]   = "external"
        ext_long["source"]   = "excel"
        out = pd.concat(
            [out, ext_long[["cod_cia", "indicator", "name", "category", "status", "source", "value"]]],
            ignore_index=True,
        )

    out["quarter"] = quarter

    names = (
        df.loc[df["quarter"] == quarter, ["cod_cia", "razon_social"]]
          .drop_duplicates("cod_cia")
          .set_index("cod_cia")["razon_social"]
    )
    out["razon_social"] = out["cod_cia"].map(names)

    return out[["cod_cia", "razon_social", "quarter", "indicator",
                "name", "category", "status", "source", "value"]]


def compute_with_yoy(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """
    Compute indicators for `quarter` and merge prior-fiscal-year same-position
    values, adding `value_prior` and `delta_pp` columns.
    """
    all_quarters = sorted(df["quarter"].unique().tolist())
    current = compute_indicators(df, quarter)

    prior_q = same_position_prior_year(quarter, all_quarters)
    if prior_q is None:
        current["value_prior"] = float("nan")
        current["delta_pp"]    = float("nan")
        return current

    prior = compute_indicators(df, prior_q)[["cod_cia", "indicator", "value"]]
    prior = prior.rename(columns={"value": "value_prior"})

    out = current.merge(prior, on=["cod_cia", "indicator"], how="left")
    out["delta_pp"] = out["value"] - out["value_prior"]
    return out


# ── validation ────────────────────────────────────────────────────────────────

# Excel oracle for ALLIANZ (cod_cia=0036), 2025-Q4 (Dec 2025 close).
# Source: Input/ssn_202512_indicadores_mercado1.xlsx
_ALLIANZ_2025Q4_ORACLE = {
    "A":  2.5948,
    "C":  29.2196,
    "D":  231.3383,
    "D'": 237.0484,
    "E":  173.3547,
    "F":  61.2341,
    "I":  22.0756,
    "K":  19.7422,
    "L":  16.5097,
    "M":  32.0064,
    "N":  10.1534,
}

# Tolerances per status. Anything outside the tolerance fails validation.
_TOLERANCE_PP = {
    "exact":       0.01,
    "close":       0.30,
    "tunable":     0.05,
    "approximate": 12.0,   # E is known to be ~11.7pp off until net-of-reinsurance is applied
}


def validate_against_oracle(df: pd.DataFrame, *, verbose: bool = True) -> bool:
    """
    Reconcile computed Allianz 2025-Q4 indicators against the Excel oracle.
    Returns True if every indicator passes its status-specific tolerance.
    """
    res = compute_indicators(df, "2025-Q4")
    allz = res[res["cod_cia"] == "0036"]
    by_code = dict(zip(allz["indicator"], allz["value"]))
    status_by_code = dict(zip(allz["indicator"], allz["status"]))

    if verbose:
        print(f"{'Ind':<5}{'Computed':>12}{'Excel':>12}{'Δ pp':>10}  {'Status':<12} Result")

    all_pass = True
    for code, expected in _ALLIANZ_2025Q4_ORACLE.items():
        computed = by_code.get(code)
        status = status_by_code.get(code, "unknown")
        tol = _TOLERANCE_PP.get(status, 1.0)
        if computed is None or pd.isna(computed):
            ok, line = False, f"{code:<5}{'n/a':>12}{expected:>12.4f}{'':>10}  {status:<12} ✗ missing"
        else:
            gap = computed - expected
            ok = abs(gap) <= tol
            mark = "✓" if ok else "✗"
            line = f"{code:<5}{computed:>12.4f}{expected:>12.4f}{gap:>+10.4f}  {status:<12} {mark}"
        all_pass = all_pass and ok
        if verbose:
            print(line)

    return all_pass


if __name__ == "__main__":
    cache = Path(__file__).parent.parent / "data" / "balance_cache.parquet"
    df = pd.read_parquet(cache)
    quarters = sorted(df["quarter"].unique())
    print(f"Loaded {len(df):,} rows · {df['cod_cia'].nunique()} companies · {len(quarters)} quarters")
    print(f"Range: {quarters[0]} ({fiscal_info(quarters[0])['short_label']}) → "
          f"{quarters[-1]} ({fiscal_info(quarters[-1])['short_label']})")
    print()
    print("=== Validation: ALLIANZ 2025-Q4 vs Excel oracle ===")
    ok = validate_against_oracle(df)
    print()
    print("Overall:", "PASS ✓" if ok else "FAIL ✗")

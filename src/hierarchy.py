"""
Account hierarchy utilities for the SSN chart of accounts.
"""
import pandas as pd

ROOT_MAP = {
    "1": "ACTIVO",
    "2": "PASIVO",
    "3": "PATRIMONIO NETO",
    "4": "PERDIDAS",
    "5": "GANANCIAS",
}

# Human-friendly labels for level-2 P&L accounts
PNL_LABELS = {
    "4.01": "Costos Técnicos",
    "4.02": "Costos Financieros",
    "4.03": "Part. de Terceros",
    "4.04": "Resultados Extr. (−)",
    "4.05": "Impuesto a las Ganancias",
    "5.01": "Ingresos Técnicos",
    "5.02": "Ingresos Financieros",
    "5.03": "Resultados Extr. (+)",
}


def root_of(cod_cuenta: str) -> str:
    """Return root category name for an account code."""
    first = str(cod_cuenta).split(".")[0]
    return ROOT_MAP.get(first, "OTRO")


def prefix2(cod_cuenta: str) -> str:
    """Return the level-2 prefix (e.g. '4.01') for any account code."""
    parts = str(cod_cuenta).split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return parts[0]


def level2_label(cod_cuenta: str) -> str:
    p2 = prefix2(cod_cuenta)
    return PNL_LABELS.get(p2, p2)


def get_level2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter to exactly level-2 rows (the canonical working grain).
    Avoids double-counting from parent roll-up rows.
    """
    return df[df["nivel"] == 2].copy()


def get_subtree(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """All rows whose account code starts with the given prefix."""
    return df[df["cod_cuenta"].str.startswith(prefix)].copy()


def pnl_summary(df: pd.DataFrame, cod_cia: str, quarter: str) -> pd.DataFrame:
    """
    Return a DataFrame with one row per level-2 P&L account for the
    selected company and period. Columns: cod_l2, label, root, importe.
    """
    mask = (df["cod_cia"] == cod_cia) & (df["quarter"] == quarter) & (df["nivel"] == 2)
    sub = df[mask].copy()

    sub["root"] = sub["cod_cuenta"].apply(root_of)
    pnl = sub[sub["root"].isin(["PERDIDAS", "GANANCIAS"])].copy()

    pnl["cod_l2"] = pnl["cod_cuenta"].apply(prefix2)
    pnl["label"] = pnl["cod_l2"].apply(lambda c: PNL_LABELS.get(c, c))

    result = (
        pnl.groupby(["cod_l2", "label", "root"], as_index=False)["importe"].sum()
    )
    return result.sort_values("cod_l2").reset_index(drop=True)


COST_LABELS = {
    "4.01.01": "Siniestros",
    "4.01.02": "Otras Indemn.",
    "4.01.03": "Primas Cedidas a Reaseg.",
    "4.01.04": "Anulaciones de Primas",
    "4.01.05": "Compromisos Técnicos",
    "4.01.06": "Comisiones",
    "4.01.07": "Gastos de Explotación",
    "4.01.50": "Otros Egresos",
}


def costos_tecnicos_por_componente(
    df: pd.DataFrame,
    cod_cia: str,
    quarter: str,
) -> pd.DataFrame:
    """
    Return technical costs (4.01) broken down by nivel-3 component.
    Columns: cod_l3, label, importe (ARS). Only non-zero rows returned,
    sorted descending by importe.
    """
    mask = (
        (df["cod_cia"] == cod_cia)
        & (df["quarter"] == quarter)
        & (df["cod_cuenta"].str.startswith("4.01"))
        & (df["nivel"] == 3)
        & ((df["desc_subramo"].isna()) | (df["desc_subramo"] == ""))
    )
    sub = df[mask].copy()
    if sub.empty:
        return pd.DataFrame(columns=["cod_l3", "label", "importe"])

    sub["cod_l3"] = sub["cod_cuenta"].apply(
        lambda c: ".".join(c.split(".")[:3])
    )
    sub["label"] = sub["cod_l3"].map(COST_LABELS).fillna(sub["cod_l3"])

    result = (
        sub.groupby(["cod_l3", "label"], as_index=False)["importe"]
        .sum()
        .sort_values("importe", ascending=False)
    )
    return result[result["importe"] > 0].reset_index(drop=True)


def ingresos_por_ramo(
    df: pd.DataFrame,
    cod_cia: str,
    quarter: str,
    max_ramos: int = 9,
) -> pd.DataFrame:
    """
    Return technical income (5.01) broken down by subramo (insurance branch).

    Leaf-node detection:
      - At nivel=7, a row is a parent if any nivel=8 row shares its first 7
        account segments (the SSN pattern: .XX.00 parent → .XX.NN child).
      - Combine true nivel=7 leaves + all nivel=8 rows and aggregate by subramo.

    Returns DataFrame with columns: cod_subramo, desc_subramo, importe (ARS),
    sorted descending by importe.  Rows beyond max_ramos are collapsed into
    a single 'Otros Ramos' entry so the Sankey stays readable.
    """
    mask = (
        (df["cod_cia"] == cod_cia)
        & (df["quarter"] == quarter)
        & (df["cod_cuenta"].str.startswith("5.01"))
        & (df["desc_subramo"].notna())
        & (df["desc_subramo"] != "")
    )
    sub = df[mask].copy()
    if sub.empty:
        return pd.DataFrame(columns=["cod_subramo", "desc_subramo", "importe"])

    sub7 = sub[sub["nivel"] == 7]
    sub8 = sub[sub["nivel"] == 8]

    # First 7 dot-segments identify the parent/child relationship
    def _prefix7(code: str) -> str:
        return ".".join(code.split(".")[:7])

    nivel8_prefixes = set(sub8["cod_cuenta"].apply(_prefix7))

    leaf7 = sub7[~sub7["cod_cuenta"].apply(_prefix7).isin(nivel8_prefixes)]
    leaves = pd.concat([leaf7, sub8], ignore_index=True)

    ramos = (
        leaves.groupby(["cod_subramo", "desc_subramo"], as_index=False)["importe"]
        .sum()
        .sort_values("importe", ascending=False)
        .reset_index(drop=True)
    )

    if len(ramos) > max_ramos:
        top = ramos.head(max_ramos - 1)
        otros_val = ramos.iloc[max_ramos - 1 :]["importe"].sum()
        otros = pd.DataFrame([{
            "cod_subramo": "OTROS",
            "desc_subramo": f"Otros ({len(ramos) - max_ramos + 1} ramos)",
            "importe": otros_val,
        }])
        ramos = pd.concat([top, otros], ignore_index=True)

    return ramos


def balance_summary(df: pd.DataFrame, cod_cia: str, quarter: str) -> pd.DataFrame:
    """
    Return a DataFrame with one row per level-2 balance account for the
    selected company and period. Columns: cod_l2, desc_cuenta, root, importe.
    """
    mask = (df["cod_cia"] == cod_cia) & (df["quarter"] == quarter) & (df["nivel"] == 2)
    sub = df[mask].copy()
    sub["root"] = sub["cod_cuenta"].apply(root_of)

    bs = sub[sub["root"].isin(["ACTIVO", "PASIVO", "PATRIMONIO NETO"])].copy()
    bs["cod_l2"] = bs["cod_cuenta"].apply(prefix2)

    result = (
        bs.groupby(["cod_l2", "desc_cuenta", "root"], as_index=False)["importe"].sum()
    )
    return result.sort_values("cod_l2").reset_index(drop=True)

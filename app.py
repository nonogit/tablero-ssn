"""
SSN Comparison Dashboard — Streamlit entry point.

Run:  streamlit run app.py
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.extractor import load_data, company_list, period_list
from src.metrics import ALL_INDICATOR_DEFS, INDICATOR_DEFS, build_aggregates, compute_with_yoy
from src.ranking import DEFAULT_ASCENDING, build_ranking, build_wide_table, delta_rank_arrow
from src.benchmark import nearest_peers, percentile_rank, quartile_label
from src.fiscal import fiscal_info, same_position_prior_year


# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SSN Comparativo",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
  [data-testid="stMetricValue"]  { font-size: 1.4rem; }
  [data-testid="stMetricDelta"]  { font-size: 0.85rem; }
  .block-container               { padding-top: 1.2rem; }
  h1, h2, h3                     { font-weight: 600; }
  h1                             { font-size: 1.4rem !important; }
  h3                             { font-size: 1.05rem !important; }
</style>
""",
    unsafe_allow_html=True,
)


# ── cached data loaders ───────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cargando datos SSN…")
def _get_data() -> pd.DataFrame:
    return load_data()


@st.cache_data(show_spinner=False)
def _get_companies(df: pd.DataFrame) -> pd.DataFrame:
    return company_list(df)


@st.cache_data(show_spinner=False)
def _get_companies_for_quarter(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """Companies present in the given quarter, with unique cod_cia → razon_social."""
    sub = (
        df.loc[df["quarter"] == quarter, ["cod_cia", "razon_social"]]
          .drop_duplicates("cod_cia")
          .sort_values("razon_social")
          .reset_index(drop=True)
    )
    return sub


@st.cache_data(show_spinner=False)
def _get_periods(df: pd.DataFrame) -> list[str]:
    return period_list(df)


@st.cache_data(show_spinner="Calculando indicadores…")
def _get_indicators(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    return compute_with_yoy(df, quarter)


@st.cache_data(show_spinner="Calculando series temporales…")
def _get_indicators_all(df: pd.DataFrame) -> pd.DataFrame:
    """Long-format indicators stacked across every loaded quarter (used by Trends)."""
    from src.metrics import compute_indicators
    quarters = sorted(df["quarter"].unique())
    return pd.concat(
        [compute_indicators(df, q) for q in quarters], ignore_index=True
    )


@st.cache_data(show_spinner=False)
def _get_aggregates(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    return build_aggregates(df, quarter)


# ── formatting helpers ────────────────────────────────────────────────────────
def fmt_ars_b(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"${value/1e9:,.1f} B"


def fmt_pct(value: float | None, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}%"


def pct_delta(current: float | None, prior: float | None) -> str | None:
    if current is None or prior is None or prior == 0 or pd.isna(current) or pd.isna(prior):
        return None
    return f"{(current - prior) / abs(prior) * 100:+.1f}%"


def pp_delta(current: float | None, prior: float | None) -> str | None:
    if current is None or prior is None or pd.isna(current) or pd.isna(prior):
        return None
    return f"{current - prior:+.2f} pp"


# ── shared indicator metadata (used by all tabs) ─────────────────────────────
# Use ALL_INDICATOR_DEFS so external (Excel-sourced) indicators B, G, H, J
# appear in selectors. Their values are only populated for quarters where
# the SSN Excel report is available — otherwise they're NaN and skipped.
INDICATOR_OPTIONS = [(code, f"{code} — {name}") for code, name, *_ in ALL_INDICATOR_DEFS]
CODE_TO_LABEL = dict(INDICATOR_OPTIONS)
INDICATOR_CODES = [c for c, _ in INDICATOR_OPTIONS]
INDICATOR_SOURCE = {code: src for code, name, cat, status, src in ALL_INDICATOR_DEFS}


def _indicator_index(code: str) -> int:
    """Position of `code` in INDICATOR_CODES (for selectbox defaults)."""
    return INDICATOR_CODES.index(code) if code in INDICATOR_CODES else 0


def _resolve_cods(names: list[str], companies_df: pd.DataFrame) -> list[str]:
    """Map razon_social list → cod_cia list, preserving order, dropping unknowns."""
    lookup = companies_df.set_index("razon_social")["cod_cia"]
    return [lookup[n] for n in names if n in lookup.index]


def _min_primas_keep(agg_df: pd.DataFrame, threshold_b: float) -> set[str]:
    """Set of cod_cia whose Primas Emitidas ≥ threshold (in ARS billions)."""
    primas = agg_df["primas_y_recargos"] - agg_df["anulaciones"]
    return set(primas[primas >= threshold_b * 1e9].index)


# ── sidebar ───────────────────────────────────────────────────────────────────
df = _get_data()
periods = _get_periods(df)
debug_mode = "debug" in st.query_params

with st.sidebar:
    st.title("📊 SSN Comparativo")
    st.caption("Superintendencia de Seguros de la Nación")
    st.divider()

    period_labels = {q: fiscal_info(q)["short_label"] for q in periods}
    selected_quarter = st.selectbox(
        "Período",
        options=periods[::-1],
        format_func=lambda q: f"{period_labels[q]}  ({q})",
        index=0,
    )

    # Companies present in the selected quarter only
    companies = _get_companies_for_quarter(df, selected_quarter)

    st.divider()

    company_names = companies["razon_social"].tolist()
    default_focus_idx = next(
        (i for i, n in enumerate(company_names) if "ALLIANZ" in str(n).upper()),
        0,
    )
    focus_company = st.selectbox(
        "Compañía foco",
        options=company_names,
        index=default_focus_idx,
        help="Empresa de referencia. Se usa en Peer Benchmark y Tendencias.",
    )
    focus_cod = companies.loc[companies["razon_social"] == focus_company, "cod_cia"].iloc[0]

    side_by_side = st.multiselect(
        "Comparar (lado a lado)",
        options=company_names,
        default=[focus_company],
        max_selections=5,
        help="Hasta 5 empresas para la solapa Lado a Lado.",
    )

    st.divider()
    st.subheader("Filtros")

    min_primas_b = st.slider(
        "Primas Emitidas mínimas (B ARS)",
        min_value=0.0,
        max_value=50.0,
        value=1.0,
        step=0.5,
        help=(
            "Excluye empresas con Primas Emitidas por debajo del umbral en "
            "gráficos de distribución (no afecta el ranking ni las tablas)."
        ),
    )

    peer_mode = st.radio(
        "Conjunto de pares",
        options=["Todo el mercado", "Top-10 por primas", "Top-20 por primas", "Manual"],
        index=0,
        help="Determina contra quién se compara la compañía foco en Peer Benchmark.",
    )

    st.divider()
    st.caption(f"Datos: {len(companies)} compañías en {selected_quarter} · {len(periods)} períodos cargados")
    st.caption("Validación: 11/11 indicadores ≤ tolerancia (Allianz 2025-Q4)")

    with st.expander("ℹ️ Acerca del tablero"):
        st.markdown(
            """
            Comparación de compañías de seguros argentinas usando los indicadores
            oficiales que publica la **Superintendencia de Seguros de la Nación**.

            **Convenciones clave:**
            - El año fiscal SSN va de **julio a junio**. Cada trimestre publicado
              acumula desde el 1 de julio (Q3 = 3m, Q4 = 6m, Q1 = 9m, Q2 = Cierre 12m).
            - Las comparaciones interanuales se hacen contra la **misma posición fiscal**
              del año anterior (p.ej. EJ2025·6m vs EJ2024·6m).
            - Los indicadores siguen las definiciones del Anexo I de la SSN
              (`docs/account_mapping.md` para detalles).

            Indicadores no derivables del balance (B juicios, G capital regulatorio,
            H compromisos exigibles) se omiten en v1.
            """
        )


# ── sector KPI strip ──────────────────────────────────────────────────────────
agg = _get_aggregates(df, selected_quarter)
prior_q = same_position_prior_year(selected_quarter, periods)
agg_prior = _get_aggregates(df, prior_q) if prior_q else None


def _sector_kpis(a: pd.DataFrame) -> dict:
    primas = (a["primas_y_recargos"] - a["anulaciones"]).sum()
    net = (a["ganancias"] - a["perdidas"]).sum()
    gastos_tot = a["gastos_prod"].sum() + a["gastos_exp"].sum() - a["gastos_a_reaseg"].sum()
    return {
        "n_companies": len(a),
        "primas":      primas,
        "net":         net,
        "M":           100 * gastos_tot / primas if primas else None,
        "N":           100 * net / primas if primas else None,
    }


k = _sector_kpis(agg)
kp = _sector_kpis(agg_prior) if agg_prior is not None else None

period_long = fiscal_info(selected_quarter)["long_label"]
st.markdown(f"### Mercado Asegurador — {period_long}")
if prior_q:
    st.caption(f"Δ vs {fiscal_info(prior_q)['short_label']} ({prior_q}) — misma posición fiscal")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Compañías", f"{k['n_companies']}")
c2.metric(
    "Σ Primas Emitidas",
    fmt_ars_b(k["primas"]),
    delta=pct_delta(k["primas"], kp["primas"]) if kp else None,
)
c3.metric(
    "Σ Resultado del Ejercicio",
    fmt_ars_b(k["net"]),
    delta=pct_delta(k["net"], kp["net"]) if kp else None,
)
c4.metric(
    "Gastos Totales / Primas (M)",
    fmt_pct(k["M"]),
    delta=pp_delta(k["M"], kp["M"] if kp else None),
    delta_color="inverse",  # lower is better
)
c5.metric(
    "Resultado / Primas (N)",
    fmt_pct(k["N"]),
    delta=pp_delta(k["N"], kp["N"] if kp else None),
)


# ── tabs ──────────────────────────────────────────────────────────────────────
tab_ranking, tab_sxs, tab_peer, tab_quad, tab_trend = st.tabs([
    "🏆 Ranking",
    "↔️ Lado a Lado",
    "🎯 Peer Benchmark",
    "🔲 Cuadrante",
    "📈 Tendencias",
])

with tab_ranking:
    ind = _get_indicators(df, selected_quarter)

    cl, cm, cr = st.columns([2, 1, 1])
    with cl:
        rank_code = st.selectbox(
            "Rankear por",
            options=INDICATOR_CODES,
            format_func=lambda c: CODE_TO_LABEL[c],
            index=0,
        )
    with cm:
        ascending = st.toggle(
            "Menor → mejor",
            value=DEFAULT_ASCENDING.get(rank_code, False),
            help="Activá para indicadores donde un valor más bajo es mejor (p.ej. M = gastos totales).",
        )
    with cr:
        apply_min_primas = st.toggle(
            "Excluir empresas chicas",
            value=(rank_code != "A"),  # off for market share (size IS the metric); on for ratios
            help=f"Excluye empresas con Primas Emitidas < ${min_primas_b:.1f}B (umbral en la barra lateral).",
        )

    # Apply the min-primas filter if toggled
    excluded = 0
    if apply_min_primas and min_primas_b > 0:
        keep = _min_primas_keep(agg, min_primas_b)
        before = ind["cod_cia"].nunique()
        ind_filtered = ind[ind["cod_cia"].isin(keep)]
        excluded = before - ind_filtered["cod_cia"].nunique()
    else:
        ind_filtered = ind

    ranking = build_ranking(ind_filtered, rank_code, ascending=ascending)
    n_total = len(ranking)
    n_with_value = ranking["value"].notna().sum()
    if excluded:
        st.caption(f"{excluded} empresas excluidas por Primas Emitidas < ${min_primas_b:.1f}B.")

    # Focus-company callout
    focus_row = ranking[ranking["cod_cia"] == focus_cod]
    if not focus_row.empty:
        fr = focus_row.iloc[0]
        rank_str = f"#{int(fr['rank'])}" if pd.notna(fr["rank"]) else "n/a"
        delta_str = delta_rank_arrow(fr["delta_rank"])
        value_str = fmt_pct(fr["value"], 2)
        st.markdown(
            f"**{focus_company}** — rank {rank_str} de {n_with_value}  ·  "
            f"valor: {value_str}  ·  Δ vs período anterior: {delta_str}"
        )

    # Top-20 bar chart
    top = ranking.head(20).copy()
    top = top.iloc[::-1]  # plot top-1 at the top
    bar_colors = [
        "#1f77b4" if cod != focus_cod else "#d62728"
        for cod in top["cod_cia"]
    ]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=top["value"],
        y=top["razon_social"],
        orientation="h",
        marker_color=bar_colors,
        hovertemplate="<b>%{y}</b><br>" + CODE_TO_LABEL[rank_code] + ": %{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Top-20 · {CODE_TO_LABEL[rank_code]}",
        height=520,
        margin=dict(l=0, r=20, t=50, b=20),
        xaxis_title=None,
        yaxis_title=None,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Sortable table — full ranking with key columns
    display = ranking[[
        "rank", "razon_social", "value", "value_prior", "delta_pp", "delta_rank",
    ]].copy()
    display.columns = ["Rank", "Compañía", "Valor", "Valor previo", "Δ pp", "Δ rank"]
    display["Δ rank"] = display["Δ rank"].apply(delta_rank_arrow)

    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=420,
        column_config={
            "Rank":         st.column_config.NumberColumn(format="%d", width="small"),
            "Valor":        st.column_config.NumberColumn(format="%.2f"),
            "Valor previo": st.column_config.NumberColumn(format="%.2f"),
            "Δ pp":         st.column_config.NumberColumn(format="%+.2f"),
        },
    )

    if n_total > n_with_value:
        st.caption(f"{n_total - n_with_value} compañías sin valor para este indicador (ubicadas al final).")

with tab_sxs:
    if len(side_by_side) < 2:
        st.info(
            "Seleccioná al menos 2 empresas en la barra lateral "
            "(*Comparar lado a lado*) para ver la comparación detallada."
        )
    else:
        # Resolve cod_cia for each selected company name
        sxs_cods = (
            companies.set_index("razon_social")
                     .loc[side_by_side, "cod_cia"]
                     .tolist()
        )
        ind = _get_indicators(df, selected_quarter)

        # ── Comparison table ─────────────────────────────────────────────
        ind_sxs = ind[ind["cod_cia"].isin(sxs_cods)]
        wide = ind_sxs.pivot_table(
            index=["indicator", "name"],
            columns="razon_social",
            values="value",
            aggfunc="first",
        )
        # Reorder columns to match the user's selection order
        wide = wide[[c for c in side_by_side if c in wide.columns]]
        wide = wide.reset_index()

        st.markdown("#### Tabla comparativa")

        # Direction-aware best/worst styling: green = best, red = worst
        def _style_row(row: pd.Series):
            code = row["indicator"]
            ascending = DEFAULT_ASCENDING.get(code, False)
            company_cols = [c for c in row.index if c not in ("indicator", "name")]
            vals = pd.to_numeric(row[company_cols], errors="coerce")
            if vals.notna().sum() < 2:
                return ["" for _ in row]
            best  = vals.min() if ascending else vals.max()
            worst = vals.max() if ascending else vals.min()
            styles = []
            for c in row.index:
                if c in company_cols and pd.notna(row[c]):
                    if row[c] == best:
                        styles.append("background-color: #d4edda; font-weight: 600")
                    elif row[c] == worst:
                        styles.append("background-color: #f8d7da")
                    else:
                        styles.append("")
                else:
                    styles.append("")
            return styles

        fmt_cols = {c: "{:,.2f}" for c in wide.columns if c not in ("indicator", "name")}
        styled = (
            wide.style
                .apply(_style_row, axis=1)
                .format(fmt_cols)
        )
        st.dataframe(styled, hide_index=True, use_container_width=True)
        st.caption("🟢 mejor · 🔴 peor — dirección por indicador (M/K/L: menor es mejor; resto: mayor es mejor).")

        # ── Radar chart ──────────────────────────────────────────────────
        st.markdown("#### Radar — perfil normalizado")

        radar_codes = ["A", "D", "E", "F", "I", "M", "N"]
        radar_data = wide[wide["indicator"].isin(radar_codes)].set_index("indicator")
        # Normalize each indicator 0–1 within the selected set, flipping ascending ones
        # so that 1 always means "best".
        norm = radar_data.copy()
        for code in radar_codes:
            if code not in norm.index:
                continue
            row_vals = pd.to_numeric(norm.loc[code, side_by_side], errors="coerce")
            lo, hi = row_vals.min(), row_vals.max()
            if pd.isna(lo) or pd.isna(hi) or hi == lo:
                norm.loc[code, side_by_side] = 0.5
                continue
            scaled = (row_vals - lo) / (hi - lo)
            if DEFAULT_ASCENDING.get(code, False):
                scaled = 1 - scaled
            norm.loc[code, side_by_side] = scaled

        theta_labels = [
            f"{c} — {radar_data.loc[c, 'name']}" if c in radar_data.index else c
            for c in radar_codes
            if c in norm.index
        ]
        valid_codes = [c for c in radar_codes if c in norm.index]

        radar_fig = go.Figure()
        for company in side_by_side:
            radar_fig.add_trace(go.Scatterpolar(
                r=[norm.loc[c, company] for c in valid_codes],
                theta=theta_labels,
                fill="toself",
                name=company[:30] + ("…" if len(company) > 30 else ""),
                opacity=0.55,
            ))
        radar_fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            showlegend=True,
            height=520,
            margin=dict(l=40, r=40, t=30, b=30),
        )
        st.plotly_chart(radar_fig, use_container_width=True)
        st.caption("Cada eje normalizado 0–1 sobre el set seleccionado · 1 = mejor (M/K/L invertidos).")

        # ── Balance composition (stacked bar) ────────────────────────────
        st.markdown("#### Composición del Activo")

        agg_sxs = agg.loc[sxs_cods]
        balance_components = [
            ("disp",      "Disponibilidades"),
            ("inv",       "Inversiones"),
            ("creditos",  "Créditos"),
            ("inmuebles", "Inmuebles"),
        ]

        scale_mode = st.radio(
            "Escala",
            options=["Absoluto (B ARS)", "% del Activo"],
            horizontal=True,
            label_visibility="collapsed",
        )

        bar_fig = go.Figure()
        for col, label in balance_components:
            values = agg_sxs[col]
            if scale_mode == "% del Activo":
                values = 100 * values / agg_sxs["activo"]
            else:
                values = values / 1e9
            # x axis = company names in selection order
            x_labels = [
                companies.set_index("cod_cia").loc[cod, "razon_social"]
                for cod in agg_sxs.index
            ]
            bar_fig.add_trace(go.Bar(
                name=label,
                x=x_labels,
                y=values,
                hovertemplate="<b>%{x}</b><br>" + label + ": %{y:,.1f}<extra></extra>",
            ))
        bar_fig.update_layout(
            barmode="stack",
            height=420,
            margin=dict(l=20, r=20, t=20, b=20),
            xaxis_title=None,
            yaxis_title=("B ARS" if scale_mode == "Absoluto (B ARS)" else "% del Activo"),
        )
        st.plotly_chart(bar_fig, use_container_width=True)

with tab_peer:
    ind = _get_indicators(df, selected_quarter)
    ind_wide = build_wide_table(ind).set_index("cod_cia")

    # ── Resolve peer set from the sidebar `peer_mode` ──────────────────
    primas_emit = (agg["primas_y_recargos"] - agg["anulaciones"])
    if peer_mode == "Top-10 por primas":
        peer_cods = set(primas_emit.nlargest(10).index)
    elif peer_mode == "Top-20 por primas":
        peer_cods = set(primas_emit.nlargest(20).index)
    elif peer_mode == "Manual":
        if len(side_by_side) >= 2:
            peer_cods = set(
                companies.set_index("razon_social")
                         .loc[side_by_side, "cod_cia"]
                         .tolist()
            )
        else:
            peer_cods = set(primas_emit.nlargest(20).index)
            st.warning("Modo Manual seleccionado pero hay <2 empresas en *Comparar lado a lado*. Se usa Top-20 como fallback.")
    else:  # "Todo el mercado"
        peer_cods = set(primas_emit.index)

    # Always include the focus company in the peer set so it shows up on charts
    peer_cods.add(focus_cod)
    n_peers = len(peer_cods)

    st.markdown(
        f"**{focus_company}** vs **{peer_mode}** "
        f"({n_peers} compañías incluyendo la empresa foco)"
    )

    if focus_cod not in ind_wide.index:
        st.error(f"La compañía foco no tiene datos en {selected_quarter}.")
        st.stop()

    # Apply min-primas filter on top of peer set, but always retain the focus company
    if min_primas_b > 0:
        keep = _min_primas_keep(agg, min_primas_b) | {focus_cod}
        peer_cods = peer_cods & keep

    ind_wide_peer = ind_wide.loc[list(peer_cods & set(ind_wide.index))]

    # ── Distribution charts (6 indicators in a 2×3 grid) ──────────────
    st.markdown("#### Distribución de indicadores en el set de pares")

    dist_codes = ["A", "D", "E", "F", "M", "N"]
    code_names = {code: name for code, name, *_ in INDICATOR_DEFS}

    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=[f"{c} — {code_names[c]}" for c in dist_codes],
        vertical_spacing=0.18,
        horizontal_spacing=0.08,
    )
    for i, code in enumerate(dist_codes):
        row, col = (i // 3) + 1, (i % 3) + 1
        if code not in ind_wide_peer.columns:
            continue
        vals = pd.to_numeric(ind_wide_peer[code], errors="coerce").dropna()
        focus_val = ind_wide_peer.loc[focus_cod, code] if focus_cod in ind_wide_peer.index else None

        fig.add_trace(
            go.Box(
                x=vals.values,
                name=code,
                marker_color="#1f77b4",
                boxpoints="all",
                jitter=0.35,
                pointpos=0,
                marker=dict(size=4, opacity=0.5),
                showlegend=False,
                orientation="h",
                hovertemplate=f"{code}: %{{x:,.2f}}<extra></extra>",
            ),
            row=row, col=col,
        )
        if focus_val is not None and pd.notna(focus_val):
            fig.add_trace(
                go.Scatter(
                    x=[focus_val], y=[code],
                    mode="markers",
                    marker=dict(size=14, color="#d62728", symbol="diamond",
                                line=dict(width=2, color="white")),
                    name=focus_company,
                    showlegend=(i == 0),
                    hovertemplate=f"<b>{focus_company}</b><br>{code}: %{{x:,.2f}}<extra></extra>",
                ),
                row=row, col=col,
            )

    fig.update_layout(
        height=460,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("🔷 = compañía foco · puntos = empresas del set · caja = cuartiles 25–75 + mediana.")

    # ── Percentile rank table ─────────────────────────────────────────
    st.markdown("#### Percentil de la compañía foco")

    pct_rows = []
    for code, name, *_ in INDICATOR_DEFS:
        if code not in ind_wide_peer.columns:
            continue
        vals = ind_wide_peer[code]
        target = ind_wide_peer.loc[focus_cod, code] if focus_cod in ind_wide_peer.index else None
        ascending = DEFAULT_ASCENDING.get(code, False)
        pct = percentile_rank(vals, target, ascending=ascending)
        pct_rows.append({
            "Indicador":  code,
            "Nombre":     name,
            "Valor foco": target,
            "Percentil":  pct,
            "Cuartil":    quartile_label(pct),
            "Dirección":  "menor=mejor" if ascending else "mayor=mejor",
        })
    pct_df = pd.DataFrame(pct_rows)

    st.dataframe(
        pct_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Valor foco": st.column_config.NumberColumn(format="%.2f"),
            "Percentil":  st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=100,
            ),
        },
    )
    st.caption("Percentil interpretado como *betterness*: 100 = mejor que todos los pares; 0 = peor.")

    # ── Nearest peers ─────────────────────────────────────────────────
    st.markdown("#### Empresas más cercanas en perfil")

    np_df = nearest_peers(ind_wide_peer, focus_cod, top_n=5)
    if np_df.empty:
        st.info("No hay suficientes pares para calcular vecinos cercanos.")
    else:
        np_df["Compañía"] = np_df["cod_cia"].map(
            companies.set_index("cod_cia")["razon_social"]
        )
        np_df = np_df[["Compañía", "distance"]].rename(columns={"distance": "Distancia"})
        st.dataframe(
            np_df, hide_index=True, use_container_width=True,
            column_config={"Distancia": st.column_config.NumberColumn(format="%.3f")},
        )
        st.caption("Distancia euclídea sobre indicadores z-score-normalizados — menor = perfil más similar.")

with tab_quad:
    ind = _get_indicators(df, selected_quarter)
    ind_wide = build_wide_table(ind).set_index("cod_cia")


    cx, cy, csize = st.columns(3)
    with cx:
        x_code = st.selectbox(
            "Eje X",
            options=[c for c, _ in INDICATOR_OPTIONS],
            format_func=lambda c: CODE_TO_LABEL[c],
            index=[c for c, _ in INDICATOR_OPTIONS].index("M"),
        )
    with cy:
        y_code = st.selectbox(
            "Eje Y",
            options=[c for c, _ in INDICATOR_OPTIONS],
            format_func=lambda c: CODE_TO_LABEL[c],
            index=[c for c, _ in INDICATOR_OPTIONS].index("N"),
        )
    with csize:
        size_metric = st.selectbox(
            "Tamaño de burbuja",
            options=["Primas Emitidas", "Activo total", "Patrimonio Neto"],
            index=0,
        )

    apply_filter_q = st.toggle(
        "Excluir empresas chicas (filtro de Primas mínimas de la barra lateral)",
        value=True,
    )

    # Build the working DataFrame: cod_cia × (x, y, size, name)
    work = ind_wide[[x_code, y_code]].copy()
    work.columns = ["x", "y"]
    primas_emit = (agg["primas_y_recargos"] - agg["anulaciones"])
    size_map = {
        "Primas Emitidas":  primas_emit,
        "Activo total":     agg["activo"],
        "Patrimonio Neto":  agg["pn"],
    }
    work["size"] = size_map[size_metric].reindex(work.index)
    work["name"] = (
        companies.set_index("cod_cia")
                 .reindex(work.index)["razon_social"]
    )

    if apply_filter_q and min_primas_b > 0:
        threshold = min_primas_b * 1e9
        work = work[primas_emit.reindex(work.index) >= threshold]

    work = work.dropna(subset=["x", "y"])
    if len(work) == 0:
        st.warning("No hay empresas con datos para ambos ejes después de aplicar el filtro.")
    else:
        # Color by selection: focus = red, side-by-side picks = orange, rest = blue
        sxs_cods = set(
            companies.set_index("razon_social")
                     .reindex(side_by_side)["cod_cia"]
                     .dropna()
                     .tolist()
        )
        def _color(cod):
            if cod == focus_cod: return "#d62728"          # red
            if cod in sxs_cods:  return "#ff7f0e"          # orange
            return "rgba(31,119,180,0.5)"                   # blue translucent

        # Bubble size scaling: sqrt for area-proportionality, then to plotly's px range
        size_vals = work["size"].abs().fillna(0)
        max_size = size_vals.max() if size_vals.max() > 0 else 1
        bubble_px = 8 + 32 * (size_vals / max_size).pow(0.5)

        x_med = work["x"].median()
        y_med = work["y"].median()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=work["x"],
            y=work["y"],
            mode="markers",
            marker=dict(
                size=bubble_px,
                color=[_color(c) for c in work.index],
                line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
            ),
            text=work["name"],
            customdata=work[["size"]].values / 1e9,
            hovertemplate=(
                "<b>%{text}</b><br>"
                f"{CODE_TO_LABEL[x_code]}: %{{x:,.2f}}<br>"
                f"{CODE_TO_LABEL[y_code]}: %{{y:,.2f}}<br>"
                f"{size_metric}: $%{{customdata[0]:,.1f}} B"
                "<extra></extra>"
            ),
            showlegend=False,
        ))
        # Quadrant median lines
        fig.add_hline(y=y_med, line_dash="dot", line_color="gray", opacity=0.6,
                      annotation_text=f"mediana Y = {y_med:.2f}", annotation_position="top right")
        fig.add_vline(x=x_med, line_dash="dot", line_color="gray", opacity=0.6,
                      annotation_text=f"mediana X = {x_med:.2f}", annotation_position="top right")

        fig.update_layout(
            height=560,
            margin=dict(l=20, r=20, t=30, b=40),
            xaxis_title=CODE_TO_LABEL[x_code],
            yaxis_title=CODE_TO_LABEL[y_code],
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"🔴 compañía foco · 🟠 selección lado-a-lado · 🔵 resto del set ({len(work)} empresas) · "
            "líneas punteadas = mediana sectorial."
        )

with tab_trend:

    cl, cm, cr = st.columns([2, 1, 1])
    with cl:
        trend_code = st.selectbox(
            "Indicador",
            options=[c for c, _ in INDICATOR_OPTIONS],
            format_func=lambda c: CODE_TO_LABEL[c],
            index=[c for c, _ in INDICATOR_OPTIONS].index("N"),
        )
    with cm:
        show_median = st.toggle("Mediana sectorial", value=True)
    with cr:
        show_fy_bands = st.toggle("Bandas FY", value=True)

    # Pull all-quarter long-format indicators (cached once for the whole app)
    all_ind = _get_indicators_all(df)
    series = all_ind.loc[all_ind["indicator"] == trend_code, ["cod_cia", "quarter", "value"]]

    # X axis: fiscal short labels ordered chronologically by SSN quarter
    x_categories = [fiscal_info(q)["short_label"] for q in periods]
    q_to_x = dict(zip(periods, x_categories))

    # Lines: focus + side-by-side selection (excluding focus duplicate)
    sxs_cods = (
        companies.set_index("razon_social")
                 .reindex(side_by_side)["cod_cia"]
                 .dropna()
                 .tolist()
    )
    line_cods = [focus_cod] + [c for c in sxs_cods if c != focus_cod]

    fig = go.Figure()

    # FY shading bands (drawn first so lines render on top)
    if show_fy_bands:
        prev_fy = None
        band_start_idx = 0
        for i, q in enumerate(periods):
            fy = fiscal_info(q)["fy"]
            if prev_fy is None:
                prev_fy = fy
            elif fy != prev_fy:
                if (band_start_idx // 2) % 2 == 0:  # alternate band fill
                    fig.add_vrect(
                        x0=x_categories[band_start_idx],
                        x1=x_categories[i - 1],
                        fillcolor="rgba(200,200,200,0.18)",
                        layer="below",
                        line_width=0,
                    )
                band_start_idx = i
                prev_fy = fy
        # close the last band if it has even index
        if (band_start_idx // 2) % 2 == 0 and band_start_idx < len(periods):
            fig.add_vrect(
                x0=x_categories[band_start_idx],
                x1=x_categories[-1],
                fillcolor="rgba(200,200,200,0.18)",
                layer="below",
                line_width=0,
            )

    # Sector median line — exclude tiny-primas outliers from the median calc
    if show_median:
        keep = _min_primas_keep(agg, min_primas_b)
        med_series = series[series["cod_cia"].isin(keep)] if min_primas_b > 0 else series
        med = med_series.groupby("quarter")["value"].median()
        fig.add_trace(go.Scatter(
            x=[q_to_x[q] for q in periods],
            y=[med.get(q) for q in periods],
            mode="lines+markers",
            name="Mediana sectorial",
            line=dict(width=2, dash="dash", color="rgba(80,80,80,0.7)"),
            marker=dict(size=6),
            hovertemplate="<b>Mediana</b><br>%{x}: %{y:,.2f}<extra></extra>",
        ))

    # Per-company lines
    cod_to_name = (
        df.drop_duplicates("cod_cia")
          .set_index("cod_cia")["razon_social"]
    )
    pivot = series.pivot_table(index="cod_cia", columns="quarter", values="value", aggfunc="first")

    for cod in line_cods:
        if cod not in pivot.index:
            continue
        is_focus = (cod == focus_cod)
        name = cod_to_name.get(cod, cod)
        y_vals = [pivot.at[cod, q] if q in pivot.columns else None for q in periods]
        fig.add_trace(go.Scatter(
            x=[q_to_x[q] for q in periods],
            y=y_vals,
            mode="lines+markers",
            name=name[:30] + ("…" if len(name) > 30 else ""),
            line=dict(
                width=3.5 if is_focus else 2,
                color="#d62728" if is_focus else None,
            ),
            marker=dict(size=8 if is_focus else 6),
            hovertemplate=f"<b>{name}</b><br>%{{x}}: %{{y:,.2f}}<extra></extra>",
        ))

    fig.update_layout(
        height=500,
        margin=dict(l=20, r=20, t=30, b=40),
        xaxis_title=None,
        yaxis_title=CODE_TO_LABEL[trend_code],
        xaxis=dict(type="category", categoryorder="array", categoryarray=x_categories),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Eje X = posición fiscal SSN (ordenada cronológicamente, julio = inicio FY). "
        "Bandas grises alternan ejercicios fiscales."
    )

    # Mini-table: focus + peers values across periods
    if pivot.size > 0:
        focus_cods_set = [c for c in line_cods if c in pivot.index]
        if focus_cods_set:
            mini = pivot.loc[focus_cods_set].copy()
            mini.columns = [q_to_x[q] for q in mini.columns]
            mini.index = [cod_to_name.get(c, c) for c in mini.index]
            mini.index.name = "Compañía"
            st.markdown("##### Valores por período")
            st.dataframe(
                mini.round(2), use_container_width=True,
            )


# ── footer (debug aid — only when ?debug=1 in the URL) ────────────────────────
if debug_mode:
    with st.expander("🔍 Debug: indicadores de la compañía foco", expanded=True):
        ind = _get_indicators(df, selected_quarter)
        focus_ind = ind[ind["cod_cia"] == focus_cod].sort_values("indicator")
        st.dataframe(
            focus_ind[["indicator", "name", "value", "value_prior", "delta_pp", "status"]],
            hide_index=True,
            use_container_width=True,
        )

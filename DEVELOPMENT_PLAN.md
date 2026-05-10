# Tablero SSN — Development Plan

## Overview

Streamlit dashboard for **comparing Argentine insurance companies** across multiple dimensions, using SSN quarterly data already ingested by the upstream PnL_SSN project.

Where PnL_SSN focused on a single-company drill-down (Sankey, balance, trends), this dashboard inverts the lens: the company is one of many, and the goal is to surface relative performance, peer benchmarks, and cross-sector patterns.

---

## Data Foundation (already in place)

| Asset | Path | Notes |
|---|---|---|
| Parquet cache | `data/balance_cache.parquet` | 16 MB, 9 quarters (2023-Q3 → 2025-Q4), ~190 companies, all account levels |
| Extractor | `src/extractor.py` | Falls back to cache if no MDBs present (Linux/cloud-friendly) |
| Account hierarchy | `src/hierarchy.py` | `root_of`, `prefix2`, `pnl_summary`, `balance_summary`, `ingresos_por_ramo`, `costos_tecnicos_por_componente` |
| Fiscal calendar | `src/fiscal.py` | Argentine FY (Jul–Jun): `fiscal_info`, `same_position_prior_year`, `prior_within_fy`, `decumulate_pnl` |

Raw `.mdb` files are not duplicated — they live in `PnL_SSN/Input/`. To refresh data, regenerate the parquet there and copy it over.

---

## Comparison Styles × Measures

The dashboard mixes four comparison styles, picking the one that fits each measure best. This is the core design choice.

| Style | Best for | Example measures |
|---|---|---|
| **Ranking / leaderboard** | Volume and absolute-size measures where order matters | Premium volume, market share, net result (ARS), total assets |
| **Side-by-side (2–5 companies)** | Detailed multi-metric inspection of a chosen handful | Full P&L, balance composition, ratio panel for selected peers |
| **Peer-group benchmark** | Contextualizing one company against its segment | Solvency vs sector median, combined ratio vs top-10 average, percentile rank |

**Peer-group dimensions available:**
- **Legal form (NJ)** — Sociedades Anónimas (A) / Cooperativas y Mutuales (C) / Sucursales Extranjeras (E) / Organismos Oficiales (O). SSN already publishes subtotals on these, so they're a familiar grouping.
- **Patrimoniales y Mixtas vs especializadas** — SSN distinguishes general-line insurers from specialized (life-only, retirement, ART, etc.). Pattern is visible in the Excel as a sub-classification under each NJ.
- **Dominant subramo** — derived from `5.01` distribution per company (largest line of business).
- **Size buckets** — top-10, top-20, mid, small (by premium volume).
- **Manual** — user-selected list.
| **Scatter / quadrant** | Two-axis pattern discovery across the full population | Growth vs margin, leverage vs solvency, premium volume vs technical result |

---

## Time Treatment

**Critical: SSN P&L data is cumulative within the fiscal year (Jul 1 → Jun 30).**

| SSN quarter | Fiscal position | What it contains |
|---|---|---|
| Qx-Q3 (Sep) | FY(x+1), 3 months | Jul–Sep cumulative |
| Qx-Q4 (Dec) | FY(x+1), 6 months | Jul–Dec cumulative |
| Q(x+1)-Q1 (Mar) | FY(x+1), 9 months | Jul–Mar cumulative |
| Q(x+1)-Q2 (Jun) | FY(x+1), 12 months — **annual close** | Jul–Jun cumulative |

Implications baked into the design:

1. **Cross-company comparisons must use the same SSN quarter** — a 12-month cumulative cannot be put next to a 3-month cumulative. The single-period sidebar selector enforces this naturally.
2. **YoY deltas use same fiscal position**, not literal calendar gap. E.g. EJ2025 6m vs EJ2024 6m, both Dec snapshots — handled by `fiscal.same_position_prior_year`. Never compare 9m vs 12m.
3. **Standalone-quarter view** (e.g. "what happened Oct–Dec only") requires decumulation: subtract prior cumulative within the same FY (`fiscal.decumulate_pnl`). Default view stays cumulative; a sidebar toggle can switch to standalone.
4. **Balance sheet figures are point-in-time snapshots, NOT cumulative** — solvency, leverage, asset composition are read directly per quarter without any decumulation.
5. **Avoid naive annualization.** Doubling a Q4 (6m) to "estimate the year" assumes flat seasonality, which is rarely true for insurance. Annualized metrics (ROE, growth) are computed only from Q2 closes unless the user explicitly opts into a trailing-12-month construction.

**Default view:** sidebar selects a single SSN quarter (default = most recent Q2 close, which is the most comparable). Each KPI shows value + Δ vs prior fiscal-year same-position quarter. A dedicated **Trends** tab shows full multi-quarter history with FY-aware spacing.

---

## Tab Layout

```
┌─ Sidebar ─────────────────────────────────────────────────┐
│  Period:           [dropdown — fiscal labels, desc]       │
│  Focus company:    [dropdown — used by Peer & Side-by-Side]│
│  Peer set:         [auto / top-N / by-subramo / manual]   │
│  Side-by-side picks: [multi-select, 2–5 companies]        │
└────────────────────────────────────────────────────────────┘

┌─ Header KPI strip ────────────────────────────────────────┐
│  Sector totals: Premium · Net Result · # Companies · Δ YoY │
└────────────────────────────────────────────────────────────┘

┌─ Tabs ─────────────────────────────────────────────────────┐
│  [Ranking] [Side-by-side] [Peer Benchmark] [Quadrant] [Trends] │
└────────────────────────────────────────────────────────────┘
```

### Tab 1 — Ranking
- Sortable table: company × {Premium 5.01, Net Result, ROE, Combined Ratio, Solvency, Market Share}.
- Column header click → re-rank.
- Top-20 horizontal bar chart for the active sort column.
- Δ rank vs prior year shown as ↑/↓ arrows.

### Tab 2 — Side-by-side
- 2–5 companies selected in sidebar.
- Grouped bar charts per metric family (revenue mix, cost mix, balance composition).
- Radar chart on normalized ratios (solvency, leverage, combined ratio, ROE, growth).
- Comparison table with conditional formatting (best green, worst red).

### Tab 3 — Peer Benchmark
- Focus company highlighted; peer set defined by sidebar (sector, top-N, same dominant subramo, or manual).
- Distribution charts (box / violin) per metric, with focus company marked.
- Percentile rank table: "ROE — 78th percentile of peer set".
- "Closest peers" suggestion: 5 companies with smallest Euclidean distance on normalized ratios.

### Tab 4 — Quadrant
- Configurable scatter: pick X and Y from the metric library.
- Bubble size = total assets (or premium); colour = dominant subramo.
- Quadrant lines at sector medians.
- Hover shows full mini-card; click pins a company for highlight.

### Tab 5 — Trends
- Multi-line chart for selected metric across all loaded quarters.
- Lines = focus company + side-by-side picks + sector median.
- FY-aware X axis (uses `fiscal.short_label`).
- **Display mode toggle** for flow metrics: cumulative (default, raw SSN values) or standalone-quarter (decumulated via `fiscal.decumulate_pnl`). Snapshot/ratio metrics ignore this toggle.
- Visual cue: vertical bands shade each fiscal year so the "reset to zero in July" pattern is obvious in cumulative mode.

---

## Metric Library

Defined once in `src/metrics.py`, consumed by all tabs.

**The metric library targets SSN's own published indicators** (see `Input/ssn_202512_indicadores_mercado1.xlsx` — the official "Indicadores del Mercado Asegurador" report). This makes our numbers directly cross-checkable against SSN's quarterly publications and uses definitions the user audience already recognizes.

### SSN-official indicators (replicate these exactly)

**Patrimoniales / Solvencia (sheet 1):**

| Code | Name | Formula |
|---|---|---|
| A | % Producción Total | Primas emitidas / total mercado |
| B | Cantidad de Juicios | (count, separate source) |
| C | % Créditos / Activos | Créditos / Activos totales |
| D | Liquidez vs Deudas Aseg. | (Disponibilidades + Inversiones) / Deudas con Asegurados |
| D' | Liquidez ampliada | (Disp. + Inv. + Inmuebles) / Deudas con Asegurados |
| E | Cobertura Técnica | (Disp. + Inv. + Inmueb.) / (Deudas c/Aseg. + Compromisos Técnicos) |
| F | % Inversiones | (Inversiones + Inmuebles) / Activos |
| G | % Superávit Regulatorio | Superávit / Capital Requerido |
| H | Liquidez Inmediata | (Disp. + Inv.) / Compromisos Exigibles |

**Gestión / P&L (sheet 2):**

| Code | Name | Formula |
|---|---|---|
| I | % Cesión | Primas Cedidas / Primas Emitidas |
| J | Siniestralidad (loss ratio) | Siniestros Netos Devengados / Primas Netas Devengadas |
| K | % Gastos Producción | Gastos Producción / Primas Emitidas |
| L | % Gastos Explotación | Gastos Explotación / Primas Emitidas |
| M | % Gastos Totales | Gastos Totales / Primas Emitidas |
| N | % Resultado Ejercicio | Resultado Ejercicio / Primas Emitidas |

> **Validation gate:** reconcile computed values for 2025-Q4 (Dec 2025 cumulative, matching the Excel header "Balances al 31 de diciembre de 2025") against the Excel file. Any cell within ±0.3pp confirms the account-code mapping. Larger gaps signal aggregation errors. Reconciliation already performed for ALLIANZ — see [`docs/account_mapping.md`](docs/account_mapping.md) for indicator-by-indicator results.

### Additional metrics (beyond SSN's official list)

| Metric | Type | Formula | Source rows |
|---|---|---|---|
| Premium volume | flow (cum.) | Σ `5.01` (level 2) | `hierarchy.pnl_summary` |
| Net result | flow (cum.) | Σ `5.0x` − Σ `4.0x` | `hierarchy.pnl_summary` |
| Technical result | flow (cum.) | `5.01` − `4.01` | level 2 |
| Financial result | flow (cum.) | `5.02` − `4.02` | level 2 |
| Solvency (PN/Activo) | snapshot | `3.xx` / `1.xx` | balance roots |
| Leverage (Pas/PN) | snapshot | `2.xx` / `3.xx` | balance roots |
| ROE | mixed | net result (cum.) / `3.xx` (snapshot) | level 2 + balance |
| Δ YoY | derived | (current − prior FY same-position) / prior | via `fiscal.same_position_prior_year` |

**Type column meanings:**
- **flow (cum.)** — cumulative within the FY; only comparable across companies *at the same SSN quarter*
- **snapshot** — point-in-time balance figure; no decumulation needed
- **ratio** — same-period ratio of two flows (or two snapshots); inflation-invariant
- **mixed** — combines a cumulative flow with a snapshot; document the convention (here: cum. net result over latest equity)

All metrics returned as a long-format DataFrame: `(cod_cia, quarter, metric, value, type)`. Easy to pivot for any chart type, and the `type` column lets downstream code reject invalid cross-quarter comparisons (e.g. preventing a flow metric from being plotted across mixed accumulation lengths).

---

## Module Structure

```
Tablero_SSN/
├── Input/                       # empty; MDB ingestion stays in PnL_SSN
├── data/
│   └── balance_cache.parquet    # 16 MB, copied from PnL_SSN
├── src/
│   ├── __init__.py
│   ├── extractor.py             # ✓ reused as-is
│   ├── hierarchy.py             # ✓ reused as-is
│   ├── fiscal.py                # ✓ reused as-is
│   ├── metrics.py               # NEW — central metric library, returns long-format DF
│   ├── peer_groups.py           # NEW — peer-set definitions (sector / top-N / by-subramo / manual)
│   ├── ranking.py               # NEW — ranking tab data prep
│   ├── benchmark.py             # NEW — peer-benchmark distributions, percentile rank, nearest-peer
│   ├── quadrant.py              # NEW — scatter data + quadrant medians
│   └── trends.py                # NEW — multi-quarter time series (different from PnL_SSN/trends.py)
├── pages/                       # optional, if we use Streamlit multipage
├── app.py                       # Streamlit entry point with tabs
├── requirements.txt
├── requirements_windows.txt
└── DEVELOPMENT_PLAN.md
```

`metrics.py` is the keystone — every tab pulls from it, so all comparisons stay consistent.

---

## Build Order

| Phase | Deliverable | Est. effort |
|---|---|---|
| 0 | ✅ **Done.** Account-code mapping documented in [`docs/account_mapping.md`](docs/account_mapping.md). 11 of 15 indicators reconcile to ≤0.3pp vs Excel for Allianz 2025-Q4. | — |
| 1 | ✅ **Done.** `src/metrics.py` — long-format indicator table with `compute_indicators(df, quarter)` and `compute_with_yoy(df, quarter)`. Self-validates via `python -m src.metrics` (all 11 indicators pass status-tiered tolerances). | — |
| 1b | **New.** Small-company filter / winsorization helper. Tiny insurers (≈ premium volume near zero) produce ratios in the ±10,000%+ range and would dominate distribution charts. Sidebar slider already in place; needs application logic in chart code (Phase 6+). | 1h |
| 2 | ✅ **Done.** `app.py` — sidebar (period, focus company, side-by-side picks, min-primas filter, peer-set mode), sector KPI strip (5 metrics with YoY deltas), 5 placeholder tabs. End-to-end AppTest passes; sector M/N reconcile to ±0.05pp vs Excel "Total de Mercado". | — |
| 3 | ✅ **Done.** Ranking tab: indicator selector + asc/desc toggle + opt-in min-primas filter. Top-20 horizontal bar chart with focus-company highlight, sortable full-ranking table with Δrank arrows. `src/ranking.py` provides `build_ranking()` with FY-aware Δrank vs prior period. | — |
| 5 | ✅ **Done.** Side-by-side tab: comparison table with direction-aware best/worst highlighting (🟢/🔴), normalized 7-axis radar chart (best=1 with M/K/L flipped), stacked balance composition with absolute/% toggle. Handles <2 selection with prompt. | — |
| 6 | ✅ **Done.** Peer Benchmark tab: 2×3 box-plot grid (A, D, E, F, M, N) with focus company as red diamond, percentile-rank table with progress bars and quartile labels, nearest-peers via z-score Euclidean distance. `src/benchmark.py` provides `percentile_rank()`, `quartile_label()`, `nearest_peers()`. Wires sidebar `peer_mode` (Todo / Top-10 / Top-20 / Manual). | — |
| 7 | ✅ **Done.** Quadrant tab: configurable X/Y indicator selectors (default M vs N), bubble size by Primas / Activo / PN, sector-median quadrant lines, color encoding (red=focus, orange=side-by-side, blue=rest). Optional min-primas filter. | — |
| 8 | ✅ **Done.** Trends tab: multi-line chart across all loaded quarters, FY-aware X axis (`fiscal.short_label`), alternating FY shading bands, optional sector-median dashed line, focus company in red bold + side-by-side picks as additional lines, mini-table with values per period. | — |
| 9 | ✅ **Done.** Polish pass: hoisted `INDICATOR_OPTIONS`/`CODE_TO_LABEL` to top-level (deduped 3 copies), added `_get_indicators_all()` cache for cross-quarter lookups, applied min-primas filter to Peer Benchmark and Trends sector-median, gated debug expander on `?debug=1`, added "Acerca del tablero" sidebar info expander, helper `_resolve_cods()` and `_min_primas_keep()`, verified the no-prior-FY path (2023-Q3). | — |
| 2 | `app.py` skeleton: sidebar (period, focus company, peer set, side-by-side picks) + sector KPI strip | 1h |
| 3 | **Ranking tab** — sortable table + top-20 bar chart | 2h |
| 4 | `src/peer_groups.py` — peer-set definitions & helpers | 1h |
| 5 | **Side-by-side tab** — grouped bars + radar + comparison table | 2h |
| 6 | **Peer Benchmark tab** — distributions + percentile rank + nearest-peer | 2–3h |
| 7 | **Quadrant tab** — configurable scatter, quadrant medians, hover cards | 2h |
| 8 | **Trends tab** — multi-quarter line chart with focus + peers + median | 1–2h |
| 9 | Polish: ARS formatting, colour palette per subramo, responsive layout, st.cache_data tuning | 1–2h |

**Total estimate: ~14–17 hours**

---

## Open Questions for Later

- **Subramo as a primary filter dimension?** Some comparisons only make sense within a line of business (e.g. combined ratio for an auto insurer ≠ for a life insurer). Likely yes; defer until Phase 4 (peer groups) when subramo-based peer sets are designed.
- **Inflation adjustment?** All ARS values are nominal; in a 100%+ inflation environment, YoY deltas are misleading. Could add a sidebar toggle later (CPI deflator from INDEC), but ratios (combined, ROE, solvency) are inflation-invariant so most of the dashboard is safe by default.
- **Export?** Likely not needed v1, but the long-format metric DF makes CSV export trivial if asked.

---

## Notes

- All visualizations use Plotly (already a dep, consistent with PnL_SSN).
- Cache aggressively with `@st.cache_data` keyed on `(quarter, peer_set_id)` since the metric table is computed once and re-pivoted per tab.
- Encoding fix from PnL_SSN's extractor already applied during ingestion — no need to re-handle Latin-1 mojibake here.
- `id_padre` is unreliable as a foreign key; always use `cod_cuenta` prefix matching (per the upstream extractor notes).

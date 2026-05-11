# Account-Code Mapping for SSN Official Indicators

Maps each indicator from `Input/ssn_202512_indicadores_mercado1.xlsx` to the parquet account codes that compute it.

**Validation reference:** ALLIANZ (`cod_cia=0036`), period `2025-Q4` (Dec 2025 close, 6m of FY2026). Computed values reconciled against the Excel snapshot.

**Conventions used throughout:**
- All sums are over rows where `desc_subramo` is null/empty (the company-level totals; subramo rows are the same numbers redistributed by line of business).
- `L2(prefix)` = sum of `importe` for rows with `cod_cuenta` starting with `prefix` AND `nivel == 2`.
- `L3(prefix)` = same at `nivel == 3`.
- "Primas Emitidas" used throughout = `L3('5.01.01.')` − `L3('4.01.04.')` (premiums and surcharges, net of cancellations).

---

## Patrimoniales (Sheet 1)

### A — % Producción Total
**Formula:** company Primas Emitidas / Σ Primas Emitidas (all market) × 100
**Numerator:** `L3('5.01.01.') − L3('4.01.04.')`
**Denominator:** Σ over all companies of the same expression
**Type:** ratio (cumulative flow / cumulative flow, same period)
**Validation (Allianz 2025-Q4):** computed 2.612%, Excel 2.595% — gap 0.017pp.
**Note:** Tiny gap likely because SSN excludes specific company classes (e.g. reaseguradoras puras) from the market-total denominator. Investigate by comparing the company list in the Excel vs the parquet `cod_cia` set.
**Status:** ✅ derivable, with minor denominator tuning for exact match.

---

### B — Cantidad de Juicios
**Formula:** Count of pending lawsuits.
**Source in parquet:** none — this is a count, not a balance amount.
**Status:** ✅ **served from Excel** (`Input/ssn_<YYYYMM>_indicadores_mercado*.xlsx`) for the matching quarter. For periods without an Excel report, the value is NaN.
**Loaded by:** `src/external_indicators.py` with token-based name matching against parquet (~185/188 match rate for 2025-Q4).

---

### C — % Créditos / Activos
**Formula:** Créditos / Activo × 100
**Numerator:** `L2('1.03.')`
**Denominator:** `L2('1.')` (sum of all level-2 within ACTIVO)
**Type:** snapshot ratio
**Validation (Allianz 2025-Q4):** computed 29.2196%, Excel 29.2196% — **exact match.**
**Status:** ✅ exact.

---

### D — (Disponibilidades + Inversiones) / Deudas con Asegurados
**Formula:** (Disp. + Inv.) / Deudas c/Aseg. × 100
**Numerator:** `L2('1.01.') + L2('1.02.')`
**Denominator:** `L3('2.01.01.')`
**Type:** snapshot ratio
**Validation (Allianz 2025-Q4):** computed 231.3383%, Excel 231.3383% — **exact match.**
**Status:** ✅ exact.

---

### D' — (Disp. + Inv. + Inmuebles) / Deudas con Asegurados
**Formula:** (Disp. + Inv. + Inmuebles) / Deudas c/Aseg. × 100
**Numerator:** `L2('1.01.') + L2('1.02.') + L2('1.04.')`
**Denominator:** `L3('2.01.01.')`
**Type:** snapshot ratio
**Validation (Allianz 2025-Q4):** computed 237.0484%, Excel 237.0484% — **exact match.**
**Status:** ✅ exact.

---

### E — Cobertura Técnica
**Formula:** (Disp. + Inv. + Inmuebles) / (Deudas c/Aseg. + Compromisos Técnicos) × 100
**Numerator:** `L2('1.01.') + L2('1.02.') + L2('1.04.')` (verified by D')
**Denominator (raw guess):** `L3('2.01.01.') + L2('2.02.')`
**Type:** snapshot ratio
**Validation (Allianz 2025-Q4):** computed 161.6832%, Excel 173.3547% — **gap of ~11.7pp (~6.7% relative).**
**Diagnosis:** The numerator matches D' so it's correct. Back-solving from the Excel value, SSN's denominator is ~297.7B vs our ~319.2B — about 21B less. This is too large to be explained by the small reinsurance credits in `1.03.02` (only ~7.9B for Allianz).
**Hypothesis:** SSN likely uses **Compromisos Técnicos NETO de Reaseguros** — i.e. `2.02` minus the reinsurer-recoverable portion of technical reserves. The reinsurance offset may live in a 1.03 sub-account or be a separate calculation outside this parquet.
**Status:** ⚠️ **approximate.** Document the known gap; v1 ships with the raw formula and a footnote. Investigate the exact net-of-reinsurance convention before claiming SSN-equivalence on this metric.

---

### F — % (Inversiones + Inmuebles) / Activos
**Formula:** (Inv. + Inmuebles) / Activo × 100
**Numerator:** `L2('1.02.') + L2('1.04.')`
**Denominator:** `L2('1.')`
**Type:** snapshot ratio
**Validation (Allianz 2025-Q4):** computed 61.2341%, Excel 61.2341% — **exact match.**
**Status:** ✅ exact.

---

### G — % Superávit / Capital Requerido
**Formula:** Superávit (free regulatory capital) / Capital Mínimo Requerido × 100
**Source in parquet:** none — regulatory calc under Res. 38.708 with risk weights.
**Status:** ✅ **served from Excel** for the matching quarter (same loader as B). NaN for other periods.

---

### H — (Disp. + Inv.) / Compromisos Exigibles
**Formula:** (Disp. + Inv.) / Compromisos Exigibles × 100
**Source in parquet:** none — "Compromisos Exigibles" is a regulatory aggregate whose exact composition we don't have authoritative documentation for. (Allianz's published value implies a denominator ~3.6× total Pasivo, suggesting it includes multi-period cumulative obligations or stock-of-reservas-matemáticas type quantities.)
**Status:** ✅ **served from Excel** for the matching quarter (same loader as B/G). NaN for other periods.

---

## Gestión (Sheet 2)

### I — % Cesión (Primas Cedidas / Primas Emitidas)
**Formula:** Primas Cedidas a Reaseguradores / Primas Emitidas × 100
**Numerator:** `L3('4.01.03.')`
**Denominator:** `L3('5.01.01.') − L3('4.01.04.')`
**Type:** ratio (cumulative flow / cumulative flow)
**Validation (Allianz 2025-Q4):** computed 21.9053%, Excel 22.0756% — gap 0.17pp.
**Status:** ✅ matches within 0.2pp. Likely rounding or a slightly different "Primas Emitidas" definition (maybe SSN uses 5.01.01 directly without subtracting anulaciones for the denominator of I specifically). Tunable.

---

### J — Siniestralidad (Siniestros Netos Devengados / Primas Netas Devengadas)
**Formula:** Net incurred losses / Net earned premiums × 100
**Source in parquet:** Conceptually derivable but the exact SSN devengado treatment is non-trivial — `4.01.01` and `5.01.04` move nearly in lockstep for many companies (Allianz: 528.59B vs 528.18B), suggesting the canonical SSN formula uses a specific combination of subtotal rows plus reserve-change adjustments from `4.01.05` that we'd need authoritative documentation to reproduce.

**Status:** ✅ **served from Excel** for the matching quarter (same loader as B/G/H). NaN for other periods. Future work: derive an approximation from parquet to extend coverage to all quarters.

---

### K — % Gastos Producción / Primas Emitidas
**Formula:** Gastos de Producción / Primas Emitidas × 100
**Numerator:** `L3('4.01.06.')`
**Denominator:** `L3('5.01.01.') − L3('4.01.04.')`
**Type:** ratio
**Validation (Allianz 2025-Q4):** computed 19.6234%, Excel 19.7422% — gap 0.12pp.
**Status:** ✅ matches within 0.2pp.

---

### L — % Gastos Explotación / Primas Emitidas
**Formula:** Gastos de Explotación / Primas Emitidas × 100
**Numerator:** `L3('4.01.07.')`
**Denominator:** `L3('5.01.01.') − L3('4.01.04.')`
**Type:** ratio
**Validation (Allianz 2025-Q4):** computed 16.3824%, Excel 16.5097% — gap 0.13pp.
**Status:** ✅ matches within 0.2pp.

---

### M — % Gastos Totales / Primas Emitidas
**Formula:** **(Gastos Producción + Gastos Explotación − Gastos a Cargo de Reaseguradores) / Primas Emitidas × 100**
**Numerator:** `L3('4.01.06.') + L3('4.01.07.') − L3('5.01.03.')`
**Denominator:** `L3('5.01.01.') − L3('4.01.04.')`
**Type:** ratio
**Validation (Allianz 2025-Q4):** computed 31.7930%, Excel 32.0064% — gap 0.21pp.
**Note:** **Critical insight — M is not simply K+L.** `5.01.03` ("Gastos de Gestión a cargo de Reaseguradores") is a recovery on the income side that nets out part of acquisition/operating expense. Without this adjustment, our M was 36.01% — 4pp too high.
**Status:** ✅ matches within 0.3pp.

---

### N — % Resultado / Primas Emitidas
**Formula:** Resultado del Ejercicio / Primas Emitidas × 100
**Numerator:** `L2('5.') − L2('4.')` (Σ all gains − Σ all losses, all level-2 under root 5 and 4)
**Denominator:** `L3('5.01.01.') − L3('4.01.04.')`
**Type:** mixed (cumulative net result over cumulative premium, same period — both flow)
**Validation (Allianz 2025-Q4):** computed 10.0751%, Excel 10.1534% — gap 0.08pp.
**Status:** ✅ matches within 0.1pp.

---

## Summary

| Indicator | Source | Status | Gap (Allianz Q4) |
|---|---|---|---|
| A | parquet | ✅ tunable | 0.02pp |
| B | excel | ✅ external | exact (source value) |
| C | parquet | ✅ exact | 0.000pp |
| D | parquet | ✅ exact | 0.000pp |
| D' | parquet | ✅ exact | 0.000pp |
| E | parquet | ⚠️ approximate | 11.7pp (needs net-of-reinsurance) |
| F | parquet | ✅ exact | 0.000pp |
| G | excel | ✅ external | exact (source value) |
| H | excel | ✅ external | exact (source value) |
| I | parquet | ✅ close | 0.17pp |
| J | excel | ✅ external | exact (source value) |
| K | parquet | ✅ close | 0.12pp |
| L | parquet | ✅ close | 0.13pp |
| M | parquet | ✅ close | 0.21pp |
| N | parquet | ✅ close | 0.08pp |

**Coverage:** 15 of 15 SSN-official indicators when an Excel report exists for the selected quarter. For quarters without an Excel report (currently all except 2025-Q4), only the 11 parquet-derived indicators are populated.

**External indicators are loaded from `Input/ssn_<YYYYMM>_indicadores_mercado*.xlsx` by `src/external_indicators.py`. Name matching uses token-set scoring with abbreviation expansion — current match rate for 2025-Q4: 185/188 (98.4%). Unmatched: AURORA, COFACE, NSA (not present in the parquet for that quarter).

---

## Cross-quarter applicability

All formulas above use only parquet account codes that exist in every quarter from 2023-Q3 onward — verified by the level-2/3 chart of accounts being stable across periods. The same mapping applies to any selected quarter; only the period filter changes.

For the **Δ YoY** column in the dashboard, use `fiscal.same_position_prior_year` to find the matching prior-FY quarter (e.g. 2025-Q4 → 2024-Q4; both are 6m cumulative within their respective fiscal years, so the comparison is apples-to-apples).

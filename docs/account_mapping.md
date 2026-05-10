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
**Status:** ❌ **not derivable from the balance parquet.** Requires a separate SSN data source (the regulator publishes lawsuit counts in supplementary files).
**Decision for v1:** skip. Display an "n/a" badge in the dashboard and document the gap.

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
**Source in parquet:** none.
**Status:** ❌ **not derivable.** "Capital Requerido" is computed by SSN under regulatory rules (Resolución 38.708 et seq.) using risk weights, not a single chart-of-accounts line. SSN publishes this separately.
**Decision for v1:** skip. If it becomes critical, source it from SSN's "Estados Contables" supplementary tables and join externally.

---

### H — (Disp. + Inv.) / Compromisos Exigibles
**Formula:** (Disp. + Inv.) / Compromisos Exigibles × 100
**Source in parquet:** "Compromisos Exigibles" is not a line item in the chart of accounts. It's a regulatory aggregate (immediately-callable commitments).
**Working hypothesis:** Compromisos Exigibles ≈ Deudas c/Aseg. en juicio + Siniestros Pendientes liquidados — pieces of `2.01.01` plus specific provision lines, but the exact composition needs SSN's regulatory definition.
**Status:** ⚠️ **needs investigation.** v1 fallback: skip, or surface the closest proxy (`L2('1.01.') + L2('1.02.')` / `L3('2.01.01.')` — i.e. ratio D) with a clear label.

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
**Source in parquet:** Both numerator and denominator require **adjustments for changes in technical reserves**, which sit in:
- `4.01.05` (COMPROMISOS TECNICOS — change in reserves on the loss side)
- Reinsurance offsets in `4.01.03`
- Recoveries in `5.01.04` (CREDITOS POR RECUPEROS)

**Working formula (to be validated):**
```
Siniestros Netos Devengados   = L3('4.01.01.') − L3('5.01.04.')        # gross losses minus recoveries
Primas Netas Devengadas       = L3('5.01.01.') − L3('4.01.04.') − L3('4.01.03.') ± Δ Reservas
```
**Status:** ⚠️ **needs validation against Excel.** The "devengado" (earned) adjustment requires `4.01.05`-derived reserve changes, which need careful sign treatment. Defer detailed reconciliation to Phase 1 implementation.

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

| Indicator | Status | Gap (Allianz Q4) | Action for Phase 1 |
|---|---|---|---|
| A | ✅ tunable | 0.02pp | Tune denominator: exclude non-mercado company classes |
| B | ❌ | n/a | Skip in v1 |
| C | ✅ exact | 0.000pp | Implement as-is |
| D | ✅ exact | 0.000pp | Implement as-is |
| D' | ✅ exact | 0.000pp | Implement as-is |
| E | ⚠️ approximate | 11.7pp | Investigate net-of-reinsurance convention; ship raw + footnote |
| F | ✅ exact | 0.000pp | Implement as-is |
| G | ❌ | n/a | Skip in v1 |
| H | ⚠️ unclear | n/a | Skip in v1 or use D as proxy with clear label |
| I | ✅ close | 0.17pp | Implement; investigate denominator nuance |
| J | ⚠️ complex | n/a | Implement carefully with reserve-change adjustments; validate vs Excel |
| K | ✅ close | 0.12pp | Implement as-is |
| L | ✅ close | 0.13pp | Implement as-is |
| M | ✅ close | 0.21pp | Implement with reinsurance-credit netting |
| N | ✅ close | 0.08pp | Implement as-is |

**Coverage for v1:** 11 of 15 indicators (A, C, D, D', F, I, K, L, M, N exact-or-close + E approximate). Three deferred (B, G, H), one needing implementation care (J).

---

## Cross-quarter applicability

All formulas above use only parquet account codes that exist in every quarter from 2023-Q3 onward — verified by the level-2/3 chart of accounts being stable across periods. The same mapping applies to any selected quarter; only the period filter changes.

For the **Δ YoY** column in the dashboard, use `fiscal.same_position_prior_year` to find the matching prior-FY quarter (e.g. 2025-Q4 → 2024-Q4; both are 6m cumulative within their respective fiscal years, so the comparison is apples-to-apples).

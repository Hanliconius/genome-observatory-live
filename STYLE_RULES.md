# Genome Observatory Live — Visual Style Rules

This file is the visual contract for charts and quantitative panels in Genome Observatory Live. It should be treated as the default reference when adding or revising visualizations. New plots should follow these rules unless a scientific reason requires an exception.

## General
- Prefer a compact, information-dense scientific-dashboard aesthetic over decorative graphics.
- Reuse the site's CSS variables, typography, panel structure, spacing, borders, and accent colours. Do not introduce one-off palettes when an existing semantic colour applies.
- Every chart should remain legible on desktop and mobile, use responsive SVG where practical, and work in the site's existing light/dark presentation.
- Keep titles short and descriptive. Use the panel kicker for context and a short summary sentence for interpretation.
- State the denominator or data scope immediately below plots when ambiguity is possible.
- Tooltips should give the exact category/date and value. Hover should emphasize the selected mark without changing the underlying encoding.
- Use accessible, colour-blind-safe distinctions. Never rely on colour alone where labels, position, line style, or direct annotation can carry the distinction.
- Avoid unnecessary legends when marks can be directly labelled.

## Bar charts
- Use bars for ranked categorical comparisons and discrete totals.
- Sort ranked bars from largest to smallest.
- Use horizontal bars when category labels are long or there are many categories.
- Use the standard site accent and hover treatment for a single-series chart.
- Start quantitative bar axes at zero.
- Show exact values by tooltip; direct value labels are encouraged when they remain uncluttered.
- For top-N plots, state N and the population being ranked.

## Line charts
- Use lines for genuinely ordered time series.
- Use consistent site line weights, point/hover behavior, grid treatment, and tooltip structure.
- Do not plot days that are still within the reporting-lag window as zero. Short-term activity charts and pace statistics exclude the newest 3 calendar days because NCBI indexing can fill those dates retrospectively.
- Annual/historical plots and lifetime totals are not shifted by the reporting lag.
- Make partial periods explicit (for example, current year = year to date).

## Histograms
- Use the standard Genometrics histogram bar style.
- Bins must be explicit, stable, and scientifically interpretable.
- Do not silently change bin definitions between refreshes.

## Donuts / composition
- Use donuts only for small part-to-whole compositions.
- Keep category order stable and use existing semantic colours where available.
- Show total N in or beside the chart and exact counts/percentages on hover.

## Scientific semantics
- Distinguish assemblies/deposits from species counts.
- “Chromosome-scale” site scope means qualifying GenBank assemblies at Chromosome or Complete Genome level.
- Missing metadata is not biological absence; wording and legends should make that distinction explicit.
- Visual aggregation must not alter underlying counts. If multiple assemblies are collapsed for display, retain access to the constituent records.
- Prefer transparent operational definitions over implied biological interpretation.

## Maintenance
When a new plot establishes a reusable convention, update this document and, where possible, implement the convention through shared CSS or JavaScript rather than copying bespoke styling.

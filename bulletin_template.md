<!--
TWO-PAGE BUDGET
Page 1: header, BLUF, key judgments, trend chart, trend section
Page 2: hot spot map, where/when sections, outlook, limitations, recommendations, sources
Roughly 700 to 850 words plus two or three figures. Cut words before cutting figures.

Label it clearly as a portfolio sample. Do not use an agency seal or imply
it came from SFPD.
-->

**UNCLASSIFIED // PUBLIC DATA // PORTFOLIO SAMPLE, NOT AN OFFICIAL SFPD PRODUCT**

# [Headline that states the finding, e.g. "Vehicle Break-Ins Concentrate in Three Downtown Clusters as Citywide Volume Levels Off"]

**Crime Analysis Bulletin [No. 2026-01]** | [Date] | Prepared by: Travis [Last name]
**Data current through:** [last complete month] | **Source:** SFPD Incident Reports via DataSF

---

## Bottom Line Up Front

[Three or four sentences. What is happening, where, and what the reader should do
about it. Lead with the single most important number. A reader who stops here
should have the whole story.]

## Key Judgments

- [Judgment about the trend, with estimative language and confidence.
  e.g. "Vehicle break-ins have very likely declined since 2022 (high confidence)."]
- [Judgment about where incidents concentrate.]
- [Judgment about when they occur, or what to expect next.]

<!--
Estimative language: almost certainly > very likely > likely > roughly even chance
> unlikely > very unlikely. Confidence (high / moderate / low) is about the
quality of the evidence, and is separate from likelihood.
-->

## 1. Trend

![Monthly trend](output/fig_monthly_trend.png)

[Citywide count for the last 12 months vs. prior 12 (`last_12_vs_prior_pct`).
Direction and steepness from the Mann-Kendall test and Sen's slope, written in
plain words: "about N fewer incidents per month, statistically significant."
Name the seasonal peak. Mention the partial-month exclusion in one clause.]

## 2. Where: Hot Spots

![Hot spot map](output/hotspot_map.png)

[How many significant hot spot areas, and where (neighborhood names). The share
of incidents falling in a small share of the city. Which clusters persisted from
the prior period and which are new. Which districts rose or fell
(`district_change.csv`). One or two top intersections if they tell a story.]

## 3. When

[Peak days and hours from the heat map. Keep it to what a patrol or
prevention planner could use. Include the small heat map only if space allows.]

## 4. Outlook

[What you expect over the next three to six months, based on the seasonal
pattern and the trend. State it as a judgment with a likelihood.]

## Analytic Considerations

[Three or four sentences: underreporting, location generalization, record
revisions, the share of records without coordinates, cell-size sensitivity.
Say how each affects confidence.]

## Recommendations and Intelligence Gaps

- [One or two concrete, data-grounded actions, e.g. targeted signage or
  directed patrol windows in the persistent hot spots during peak hours.]
- [What you could not answer with this data and what would fill the gap,
  e.g. parking occupancy, tourist counts, arrest data.]

---

<small>**Sources and Methods.** SFPD Incident Reports, 2018 to Present (DataSF),
subcategory "Larceny - From Vehicle," [start date] to [end date], deduplicated to
[N] unique incidents. Hot spots: Getis-Ord Gi* on [1,000]-ft hexagons, [QGIS /
ArcGIS Pro], 90/95/99% confidence. Trend: STL decomposition, Mann-Kendall test,
Sen's slope (Python). Code: [GitHub link].</small>

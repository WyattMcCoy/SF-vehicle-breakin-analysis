-- SQL version of the trend analysis, for DuckDB (pip install duckdb).
-- Run:  duckdb sfpd.duckdb < queries.sql
-- Point the path below at your DataSF CSV export.

CREATE OR REPLACE TABLE raw AS
SELECT * FROM read_csv_auto('Police_Department_Incident_Reports.csv',
                            normalize_names = true, all_varchar = true);

-- One row per incident: drop supplemental reports (they carry their own
-- incident_id), then keep one row per incident_id (multiple offense codes). Timestamps in portal exports look
-- like '2024/03/13 11:41:00 PM'.
CREATE OR REPLACE TABLE vbi AS
SELECT * EXCLUDE (rn) FROM (
    SELECT incident_id,
           strptime(incident_datetime, '%Y/%m/%d %I:%M:%S %p') AS occurred,
           strptime(report_datetime,   '%Y/%m/%d %I:%M:%S %p') AS reported,
           police_district, analysis_neighborhood, intersection,
           TRY_CAST(latitude AS DOUBLE)  AS lat,
           TRY_CAST(longitude AS DOUBLE) AS lon,
           row_number() OVER (PARTITION BY incident_id ORDER BY report_datetime) AS rn
    FROM raw
    WHERE incident_subcategory = 'Larceny - From Vehicle'
      AND NOT upper(report_type_code) LIKE '%S'   -- drop supplemental reports
) WHERE rn = 1
  AND occurred >= DATE '2019-01-01'
  -- drop the current, incomplete month
  AND date_trunc('month', occurred) < (SELECT date_trunc('month', max(strptime(incident_datetime, '%Y/%m/%d %I:%M:%S %p'))) FROM raw);

-- 1. Monthly counts with 3-month moving average and year-over-year change
SELECT month, n,
       round(avg(n) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS avg_3mo,
       round(100.0 * (n - lag(n, 12) OVER (ORDER BY month)) / lag(n, 12) OVER (ORDER BY month), 1) AS yoy_pct
FROM (SELECT date_trunc('month', occurred) AS month, count(*) AS n FROM vbi GROUP BY 1)
ORDER BY month;

-- 2. Last 12 complete months vs the 12 before, by police district
WITH bounds AS (SELECT max(date_trunc('month', occurred)) AS last_m FROM vbi),
tagged AS (
    SELECT v.police_district,
           CASE WHEN occurred >= last_m - INTERVAL 11 MONTH THEN 'last_12'
                WHEN occurred >= last_m - INTERVAL 23 MONTH THEN 'prior_12' END AS period
    FROM vbi v, bounds
)
SELECT police_district,
       count(*) FILTER (WHERE period = 'prior_12') AS prior_12,
       count(*) FILTER (WHERE period = 'last_12')  AS last_12,
       round(100.0 * (count(*) FILTER (WHERE period = 'last_12')
                    - count(*) FILTER (WHERE period = 'prior_12'))
             / nullif(count(*) FILTER (WHERE period = 'prior_12'), 0), 1) AS pct_change
FROM tagged WHERE period IS NOT NULL
GROUP BY 1 ORDER BY last_12 DESC;

-- 3. Hour-of-day by weekday, last 12 months
SELECT dayname(occurred) AS weekday, hour(occurred) AS hr, count(*) AS n
FROM vbi
WHERE occurred >= (SELECT max(date_trunc('month', occurred)) - INTERVAL 11 MONTH FROM vbi)
GROUP BY 1, 2 ORDER BY n DESC LIMIT 15;

-- 4. Top intersections, last 12 months
SELECT intersection, count(*) AS n
FROM vbi
WHERE occurred >= (SELECT max(date_trunc('month', occurred)) - INTERVAL 11 MONTH FROM vbi)
  AND intersection IS NOT NULL
GROUP BY 1 ORDER BY n DESC LIMIT 15;

-- 5. Reporting lag (days from occurrence to report): context for how
--    reliable the most recent months are
SELECT round(median(date_diff('hour', occurred, reported)) / 24.0, 1) AS median_lag_days,
       round(quantile_cont(date_diff('hour', occurred, reported), 0.9) / 24.0, 1) AS p90_lag_days
FROM vbi;

"""
SFPD incident trend analysis (DataSF: Police Department Incident Reports, 2018 to Present).

Pulls one incident subcategory, cleans it, runs a trend analysis, and writes
charts, tables, summary numbers, and a point file for QGIS/ArcGIS.

Usage
  # Pull straight from the DataSF API (free app token optional but recommended)
  python sfpd_analysis.py --start 2019-01-01 --subcategory "Larceny - From Vehicle"

  # Or use a CSV you exported manually from data.sfgov.org
  python sfpd_analysis.py --csv Police_Department_Incident_Reports.csv

  # See which subcategory labels exist in your file before choosing one
  python sfpd_analysis.py --csv export.csv --list-subcategories
"""
import argparse
import json
import os
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from scipy import stats
from statsmodels.tsa.seasonal import STL

API = "https://data.sf.gov/resource/wg3w-h783.json"
COLS = [
    "incident_id", "incident_number", "incident_datetime", "report_datetime",
    "report_type_code", "report_type_description", "incident_category", "incident_subcategory",
    "incident_description", "police_district", "analysis_neighborhood",
    "intersection", "latitude", "longitude",
]
# Rough SF bounding box, used to drop bad geocodes
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 37.70, 37.84, -122.52, -122.35


# ---------------------------------------------------------------- load
def fetch_api(start, subcategory, token=None, page=50000):
    where = (f"incident_subcategory = '{subcategory}' "
             f"AND incident_datetime >= '{start}T00:00:00'")
    headers = {"X-App-Token": token} if token else {}
    rows, offset = [], 0
    while True:
        params = {"$select": ",".join(COLS), "$where": where,
                  "$order": "row_id", "$limit": page, "$offset": offset}
        r = requests.get(API, params=params, headers=headers, timeout=180)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        print(f"  fetched {len(rows):,} rows")
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.5)
    return pd.DataFrame(rows)


def load_csv(path):
    df = pd.read_csv(path, low_memory=False)
    # Portal exports use "Incident Datetime"; the API uses incident_datetime
    df.columns = (df.columns.str.strip().str.lower()
                  .str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_"))
    return df


# ---------------------------------------------------------------- clean
def clean(df, start, subcategory):
    log = {"rows_raw": len(df)}
    df = df[df["incident_subcategory"] == subcategory].copy()
    df["incident_datetime"] = pd.to_datetime(df["incident_datetime"], errors="coerce")
    df["report_datetime"] = pd.to_datetime(df["report_datetime"], errors="coerce")
    df = df[df["incident_datetime"] >= pd.Timestamp(start)]

    # Supplemental reports are follow-ups to an incident that already has an
    # initial report, and they get their own incident_id. DataSF's docs say to
    # filter them out or incidents get double counted. Report type codes that
    # end in "S" are supplements (IS, VS, CS).
    before = len(df)
    df = df[~df["report_type_code"].astype(str).str.upper().str.endswith("S")]
    log["supplement_rows_removed"] = before - len(df)

    # One report can list several offense codes, one row each, sharing an
    # incident_id. Keep one row per report.
    before = len(df)
    df = df.sort_values("report_datetime").drop_duplicates("incident_id", keep="first")
    log["multi_code_rows_removed"] = before - len(df)

    # Drop the most recent month: it is incomplete and still filling in
    # because of reporting lag.
    last_month = df["incident_datetime"].dt.to_period("M").max()
    df = df[df["incident_datetime"].dt.to_period("M") < last_month]
    log["partial_month_dropped"] = str(last_month)

    for c in ("latitude", "longitude"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    ok = (df["latitude"].between(LAT_MIN, LAT_MAX)
          & df["longitude"].between(LON_MIN, LON_MAX))
    log["pct_missing_or_bad_location"] = round(100 * (1 - ok.mean()), 2)
    df["has_location"] = ok
    log["incidents_clean"] = len(df)
    return df, log


# ---------------------------------------------------------------- analysis
def period_windows(df):
    """Last 12 complete months vs the 12 before that."""
    end = df["incident_datetime"].dt.to_period("M").max()
    last12 = pd.period_range(end - 11, end, freq="M")
    prior12 = pd.period_range(end - 23, end - 12, freq="M")
    p = df["incident_datetime"].dt.to_period("M")
    df["period"] = np.select([p.isin(last12), p.isin(prior12)],
                             ["last_12", "prior_12"], default="earlier")
    return df, f"{last12[0]} to {last12[-1]}", f"{prior12[0]} to {prior12[-1]}"


def pct(a, b):
    return round(100 * (a - b) / b, 1) if b else None


def trend_tests(monthly):
    out = {}
    if len(monthly) >= 24:
        stl = STL(monthly, period=12, robust=True).fit()
        deseason = monthly - stl.seasonal
        out["stl"] = stl
    else:
        deseason = monthly
    x = np.arange(len(deseason))
    tau, p = stats.kendalltau(x, deseason.values)          # Mann-Kendall style test
    slope, _, lo, hi = stats.theilslopes(deseason.values, x)  # Sen's slope
    out.update({
        "kendall_tau": round(float(tau), 3),
        "kendall_p_value": round(float(p), 4),
        "sen_slope_per_month": round(float(slope), 2),
        "sen_slope_95ci": [round(float(lo), 2), round(float(hi), 2)],
    })
    return out


def analyze(df, out):
    df, last_lbl, prior_lbl = period_windows(df)
    monthly = df.set_index("incident_datetime").resample("MS").size()
    monthly.rename("incidents").to_csv(out / "monthly_counts.csv")
    tests = trend_tests(monthly)

    n_last = int((df["period"] == "last_12").sum())
    n_prior = int((df["period"] == "prior_12").sum())

    # District comparison
    dist = (df[df["period"] != "earlier"]
            .pivot_table(index="police_district", columns="period",
                         values="incident_id", aggfunc="count", fill_value=0))
    dist = dist.reindex(columns=["prior_12", "last_12"], fill_value=0)
    dist["change"] = dist["last_12"] - dist["prior_12"]
    dist["pct_change"] = [pct(a, b) for a, b in zip(dist["last_12"], dist["prior_12"])]
    dist["share_of_city_last_12"] = (100 * dist["last_12"] / max(n_last, 1)).round(1)
    dist = dist.sort_values("last_12", ascending=False)
    dist.to_csv(out / "district_change.csv")

    # Top intersections, last 12 months
    top_int = (df[df["period"] == "last_12"]["intersection"]
               .value_counts().head(15).rename("incidents"))
    top_int.to_csv(out / "top_intersections_last12.csv")

    # Hour x weekday, last 12 months
    recent = df[df["period"] == "last_12"]
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hw = (recent.assign(hour=recent["incident_datetime"].dt.hour,
                        dow=recent["incident_datetime"].dt.day_name())
          .pivot_table(index="dow", columns="hour", values="incident_id",
                       aggfunc="count", fill_value=0)
          .reindex(index=order, columns=range(24), fill_value=0))
    hw.to_csv(out / "hour_weekday_last12.csv")

    summary = {
        "last_12_window": last_lbl, "prior_12_window": prior_lbl,
        "last_12_count": n_last, "prior_12_count": n_prior,
        "last_12_vs_prior_pct": pct(n_last, n_prior),
        "monthly_avg_last_12": round(n_last / 12, 1),
        "peak_month_overall": str(monthly.idxmax().date()),
        "peak_month_count": int(monthly.max()),
        "busiest_hour_last_12": int(hw.sum().idxmax()),
        "busiest_weekday_last_12": hw.sum(axis=1).idxmax(),
        "top_district_last_12": dist.index[0],
        "top_district_share_pct": float(dist["share_of_city_last_12"].iloc[0]),
        **{k: v for k, v in tests.items() if k != "stl"},
    }
    return df, monthly, tests.get("stl"), dist, hw, summary


# ---------------------------------------------------------------- charts
def charts(monthly, stl, dist, hw, label, out):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False})

    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.plot(monthly.index, monthly.values, color="#9aa5b1", lw=1, label="Monthly count")
    ax.plot(monthly.index, monthly.rolling(3, center=True).mean(),
            color="#1f4e79", lw=2, label="3-month average")
    if stl is not None:
        ax.plot(monthly.index, stl.trend, color="#c0392b", lw=1.5, ls="--",
                label="Trend (seasonality removed)")
    ax.set_title(f"{label}: monthly incidents, San Francisco")
    ax.set_ylabel("Incidents")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(out / "fig_monthly_trend.png", dpi=300); plt.close(fig)

    if stl is not None:
        fig = stl.plot(); fig.set_size_inches(8, 6)
        fig.tight_layout(); fig.savefig(out / "fig_stl_decomposition.png", dpi=200); plt.close(fig)

    d = dist.sort_values("pct_change")
    fig, ax = plt.subplots(figsize=(6, 3.5))
    colors = ["#c0392b" if v > 0 else "#1f4e79" for v in d["pct_change"].fillna(0)]
    ax.barh(d.index, d["pct_change"].fillna(0), color=colors)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("% change, last 12 vs prior 12 months")
    ax.set_title("Change by police district")
    fig.tight_layout(); fig.savefig(out / "fig_district_change.png", dpi=300); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 2.8))
    im = ax.imshow(hw.values, aspect="auto", cmap="Blues")
    ax.set_yticks(range(7), [d[:3] for d in hw.index])
    ax.set_xticks(range(0, 24, 2), [f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour of day (time of occurrence)")
    ax.set_title("When incidents occur, last 12 months")
    fig.colorbar(im, ax=ax, label="Incidents")
    fig.tight_layout(); fig.savefig(out / "fig_hour_weekday.png", dpi=300); plt.close(fig)


# ---------------------------------------------------------------- GIS export
def export_points(df, out):
    pts = df[df["has_location"]].copy()
    pts["date"] = pts["incident_datetime"].dt.strftime("%Y-%m-%d")
    pts["year"] = pts["incident_datetime"].dt.year
    pts["hour"] = pts["incident_datetime"].dt.hour
    keep = ["incident_id", "date", "year", "hour", "period", "police_district",
            "analysis_neighborhood", "intersection", "latitude", "longitude"]
    pts[keep].to_csv(out / "points_for_gis.csv", index=False)
    try:
        import geopandas as gpd
        g = gpd.GeoDataFrame(pts[keep], crs="EPSG:4326",
                             geometry=gpd.points_from_xy(pts["longitude"], pts["latitude"]))
        g.to_file(out / "points_for_gis.gpkg", layer="incidents", driver="GPKG")
    except ImportError:
        pass
    return len(pts)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Path to a manual DataSF export (skips the API)")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--subcategory", default="Larceny - From Vehicle")
    ap.add_argument("--label", default="Vehicle break-ins")
    ap.add_argument("--out", default="output")
    ap.add_argument("--list-subcategories", action="store_true")
    a = ap.parse_args()

    out = Path(a.out); out.mkdir(exist_ok=True)
    if a.csv:
        raw = load_csv(a.csv)
        if a.list_subcategories:
            print(raw["incident_subcategory"].value_counts().to_string()); return
    else:
        print("Downloading from DataSF...")
        raw = fetch_api(a.start, a.subcategory, os.getenv("SODA_APP_TOKEN"))

    df, log = clean(raw, a.start, a.subcategory)
    df, monthly, stl, dist, hw, summary = analyze(df, out)
    charts(monthly, stl, dist, hw, a.label, out)
    summary["mapped_points"] = export_points(df, out)
    summary["data_cleaning"] = log
    summary["subcategory"] = a.subcategory
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nOutputs written to {out.resolve()}")


if __name__ == "__main__":
    main()

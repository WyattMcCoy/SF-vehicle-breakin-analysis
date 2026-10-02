"""
Getis-Ord Gi* hot spot analysis in Python (fallback if the QGIS
Hotspot Analysis plugin won't install). Output opens directly in QGIS.

  python hotspot_gi.py --points output/points_for_gis.csv --cell 1000 --period last_12

Writes output/hotspots_gi.gpkg: a hexagon grid (EPSG:2227, US feet) with
counts, Gi* z-scores, p-values, and a confidence class for styling.
"""
import argparse
import math

import geopandas as gpd
import numpy as np
import pandas as pd
from esda.getisord import G_Local
from libpysal.weights import Queen
from shapely.geometry import Polygon

CRS = "EPSG:2227"  # NAD83 / California zone 3 (US feet)


def hex_grid(bounds, size):
    """Flat-topped hexagons; size = distance between opposite flat sides."""
    xmin, ymin, xmax, ymax = bounds
    r = size / math.sqrt(3)              # circumradius
    dx, dy = 1.5 * r, size
    cells, col, x = [], 0, xmin
    while x < xmax + dx:
        y = ymin - (size / 2 if col % 2 else 0)
        while y < ymax + dy:
            cells.append(Polygon([(x + r * math.cos(math.radians(a)),
                                   y + r * math.sin(math.radians(a)))
                                  for a in range(0, 360, 60)]))
            y += dy
        x += dx; col += 1
    return gpd.GeoDataFrame(geometry=cells, crs=CRS)


def classify(z, p):
    if p <= 0.01: c = "99%"
    elif p <= 0.05: c = "95%"
    elif p <= 0.10: c = "90%"
    else: return "Not significant"
    return f"Hot spot ({c})" if z > 0 else f"Cold spot ({c})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", default="output/points_for_gis.csv")
    ap.add_argument("--cell", type=float, default=1000, help="hex size in feet")
    ap.add_argument("--period", default="last_12", help="last_12, prior_12, or all")
    ap.add_argument("--out", default="output/hotspots_gi.gpkg")
    a = ap.parse_args()

    df = pd.read_csv(a.points)
    if a.period != "all":
        df = df[df["period"] == a.period]
    pts = gpd.GeoDataFrame(df, crs="EPSG:4326",
                           geometry=gpd.points_from_xy(df.longitude, df.latitude)).to_crs(CRS)

    grid = hex_grid(pts.total_bounds, a.cell)
    # Keep only cells that touch the area where incidents occur (buffered
    # convex hull). Swap in the DataSF city boundary for a cleaner edge.
    study = pts.union_all().convex_hull.buffer(a.cell)
    grid = grid[grid.intersects(study)].reset_index(drop=True)

    joined = gpd.sjoin(pts, grid, how="inner", predicate="within")
    grid["count"] = joined.groupby("index_right").size().reindex(grid.index, fill_value=0)

    w = Queen.from_dataframe(grid, use_index=False, silence_warnings=True)
    g = G_Local(grid["count"].astype(float).values, w, transform="B", star=True,
                permutations=999, seed=42)
    grid["gi_z"] = np.round(g.Zs, 3)
    grid["p_sim"] = g.p_sim
    grid["class"] = [classify(z, p) for z, p in zip(grid["gi_z"], grid["p_sim"])]
    grid.to_file(a.out, layer="hotspots", driver="GPKG")

    print(f"{len(grid):,} cells, {int(grid['count'].sum()):,} incidents")
    print(grid["class"].value_counts().to_string())
    hot = grid[grid["class"].str.startswith("Hot")]
    if len(hot):
        share = 100 * hot["count"].sum() / grid["count"].sum()
        area = 100 * len(hot) / len(grid)
        print(f"\nHot spot cells: {area:.1f}% of cells hold {share:.1f}% of incidents")
    print(f"Wrote {a.out}")


if __name__ == "__main__":
    main()

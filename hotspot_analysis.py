"""
Hot spot analysis for the bulletin: Getis-Ord Gi* on hexagons clipped to the
San Francisco land boundary, for the last 12 and prior 12 months, plus a
cell-size sensitivity check and the bulletin map.

  python hotspot_analysis.py --points output/points_for_gis.csv \
      --boundary output/Analysis_Neighborhoods.geojson

Outputs (in output/):
  hotspots.gpkg            layers hex_1000 (both periods), hex_500, hex_1500, zones
  hotspot_zones.csv        each contiguous hot spot zone, named by neighborhood
  hotspot_summary.json     headline numbers for the bulletin
  fig_hotspot_map.png      two-panel map: current hot spots, and change
"""
import argparse
import json
import math

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from esda.getisord import G_Local
from libpysal.weights import Queen
from matplotlib.patches import Patch
from scipy.stats import false_discovery_control
from shapely.geometry import Polygon

CRS = "EPSG:2227"  # NAD83 / California zone 3, US feet


def hex_grid(bounds, size):
    xmin, ymin, xmax, ymax = bounds
    r = size / math.sqrt(3)
    cells, col, x = [], 0, xmin
    while x < xmax + 1.5 * r:
        y = ymin - (size / 2 if col % 2 else 0)
        while y < ymax + size:
            cells.append(Polygon([(x + r * math.cos(math.radians(a)),
                                   y + r * math.sin(math.radians(a)))
                                  for a in range(0, 360, 60)]))
            y += size
        x += 1.5 * r
        col += 1
    return gpd.GeoDataFrame(geometry=cells, crs=CRS)


def city_grid(city, size):
    g = hex_grid(city.total_bounds, size)
    g = g[g.intersects(city.geometry.iloc[0])].reset_index(drop=True)
    g["hex_id"] = g.index
    return g


def count(grid, pts):
    j = gpd.sjoin(pts, grid[["hex_id", "geometry"]], how="inner", predicate="within")
    return j.groupby("hex_id").size().reindex(grid["hex_id"], fill_value=0).values


def gi_star(grid, counts):
    w = Queen.from_dataframe(grid, use_index=False, silence_warnings=True)
    g = G_Local(counts.astype(float), w, transform="B", star=True,
                permutations=0)
    z = g.Zs
    p = 2 * (1 - __import__("scipy").stats.norm.cdf(np.abs(z)))  # two-tailed
    return z, p


def classify(z):
    out = np.full(len(z), "Not significant", dtype=object)
    for thr, lab in [(1.645, "90%"), (1.960, "95%"), (2.576, "99%")]:
        out[z >= thr] = f"Hot spot ({lab})"
        out[z <= -thr] = f"Cold spot ({lab})"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", default="output/points_for_gis.csv")
    ap.add_argument("--boundary", required=True)
    ap.add_argument("--out", default="output")
    a = ap.parse_args()

    nb = gpd.read_file(a.boundary).to_crs(CRS)
    nb = nb.rename(columns={"nhood": "neighborhood"})[["neighborhood", "geometry"]]
    city = nb.dissolve()

    df = pd.read_csv(a.points)
    pts = gpd.GeoDataFrame(df, crs="EPSG:4326",
                           geometry=gpd.points_from_xy(df.longitude, df.latitude)).to_crs(CRS)
    last, prior = pts[pts.period == "last_12"], pts[pts.period == "prior_12"]

    summary = {}

    # ---- main analysis: 1,000 ft hexagons, both periods
    g = city_grid(city, 1000)
    for label, sub in [("last", last), ("prior", prior)]:
        g[f"n_{label}"] = count(g, sub)
        z, p = gi_star(g, g[f"n_{label}"].values)
        g[f"z_{label}"] = z.round(3)
        g[f"p_{label}"] = p
        g[f"class_{label}"] = classify(z)
        # Benjamini-Hochberg false discovery rate check on the hot side
        g[f"fdr_hot_{label}"] = (false_discovery_control(p) <= 0.05) & (z > 0)

    hot_l = g["z_last"] >= 1.96
    hot_p = g["z_prior"] >= 1.96
    g["change"] = np.select(
        [hot_l & hot_p, hot_l & ~hot_p, ~hot_l & hot_p],
        ["Persistent", "New", "No longer hot"], default="")

    # Name each hexagon by the neighborhood holding its center
    cent = g.copy()
    cent["geometry"] = g.centroid
    g["neighborhood"] = gpd.sjoin(cent, nb, how="left", predicate="within")["neighborhood"].values

    # ---- zones: contiguous groups of 95%+ hot hexagons (last 12 months)
    hot = g[hot_l].copy()
    zones = (hot.dissolve().explode(index_parts=False).reset_index(drop=True)
             [["geometry"]])
    rows = []
    for i, zg in zones.iterrows():
        members = hot[hot.intersects(zg.geometry.buffer(-1))]
        top = members.groupby("neighborhood")["n_last"].sum().sort_values(ascending=False)
        rows.append({
            "zone": i, "hexes": len(members), "incidents": int(members.n_last.sum()),
            "neighborhoods": ", ".join(top.index[:3]),
            "persistent_hexes": int((members.change == "Persistent").sum()),
            "new_hexes": int((members.change == "New").sum()),
            "sq_mi": round(zg.geometry.area / 27_878_400, 2),
        })
    zt = pd.DataFrame(rows).sort_values("incidents", ascending=False)
    zt["zone"] = range(1, len(zt) + 1)
    zones = zones.loc[zt.index].reset_index(drop=True)
    zones["zone"] = zt["zone"].values
    zt.to_csv(f"{a.out}/hotspot_zones.csv", index=False)

    n_city = int(g.n_last.sum())
    summary.update({
        "cell_size_ft": 1000,
        "hexagons": len(g),
        "incidents_last_12_mapped": n_city,
        "hot_hexes_95_last": int(hot_l.sum()),
        "hot_hexes_95_prior": int(hot_p.sum()),
        "hot_hexes_fdr_last": int(g.fdr_hot_last.sum()),
        "hot_share_of_city_area_pct": round(100 * hot_l.mean(), 1),
        "hot_share_of_incidents_pct": round(100 * g.loc[hot_l, "n_last"].sum() / n_city, 1),
        "persistent": int((g.change == "Persistent").sum()),
        "new": int((g.change == "New").sum()),
        "no_longer_hot": int((g.change == "No longer hot").sum()),
        "zones": len(zt),
        "cold_hexes_95_last": int((g.z_last <= -1.96).sum()),
    })

    # ---- sensitivity: do hot areas hold at 500 and 1,500 ft?
    hot_area = g[hot_l].union_all()
    sens = {}
    layers = {}
    for size in (500, 1500):
        gs = city_grid(city, size)
        gs["n_last"] = count(gs, last)
        z, _ = gi_star(gs, gs["n_last"].values)
        gs["z_last"], gs["class_last"] = z.round(3), classify(z)
        h = gs[gs.z_last >= 1.96].union_all()
        overlap = hot_area.intersection(h).area / hot_area.area if not h.is_empty else 0
        sens[f"{size}ft_pct_of_1000ft_hot_area_also_hot"] = round(100 * overlap, 1)
        sens[f"{size}ft_hot_hexes"] = int((gs.z_last >= 1.96).sum())
        layers[size] = gs
    summary["sensitivity"] = sens
    json.dump(summary, open(f"{a.out}/hotspot_summary.json", "w"), indent=2)

    # ---- save for QGIS
    gp = f"{a.out}/hotspots.gpkg"
    g.drop(columns=[c for c in g.columns if c.startswith("fdr")]).to_file(gp, layer="hex_1000", driver="GPKG")
    layers[500].to_file(gp, layer="hex_500", driver="GPKG")
    layers[1500].to_file(gp, layer="hex_1500", driver="GPKG")
    zones.to_file(gp, layer="zones", driver="GPKG")

    # ---- map
    colors = {"Hot spot (99%)": "#b2182b", "Hot spot (95%)": "#ef8a62",
              "Hot spot (90%)": "#fddbc7", "Not significant": "#eeeeee",
              "Cold spot (90%)": "#d1e5f0", "Cold spot (95%)": "#67a9cf",
              "Cold spot (99%)": "#2166ac"}
    present = [k for k in colors if (g.class_last == k).any()]
    chg = {"Persistent": "#b2182b", "New": "#f4a300", "No longer hot": "#8fa8bf"}

    fig, axes = plt.subplots(1, 2, figsize=(10, 5.2))
    for ax in axes:
        g.plot(ax=ax, color="#f4f4f4", edgecolor="white", linewidth=0.3)
        ax.set_axis_off()
    g.plot(ax=axes[0], color=g.class_last.map(colors), edgecolor="white", linewidth=0.3)
    nb.boundary.plot(ax=axes[0], color="#555", linewidth=0.35)
    for _, r in zones.iterrows():
        pt = r.geometry.representative_point()
        axes[0].annotate(str(r.zone), (pt.x + 1800, pt.y + 1800), ha="center", va="center",
                         fontsize=7, fontweight="bold", color="white", zorder=6,
                         bbox=dict(boxstyle="circle,pad=0.2", fc="#222", ec="none"))
    axes[0].set_title("A. Hot spots, Sep 2025 to Aug 2026", fontsize=10, loc="left")
    axes[0].legend(handles=[Patch(color=colors[k], label=k) for k in present],
                   loc="lower left", fontsize=6.5, frameon=False)

    import matplotlib.patheffects as pe
    for name, lab in [("South of Market", "SoMa"), ("Mission", "Mission"),
                      ("Tenderloin", "Tenderloin"), ("Western Addition", "Western\nAddition"),
                      ("North Beach", "North\nBeach"), ("Marina", "Marina"),
                      ("Potrero Hill", "Potrero\nHill"), ("Bayview Hunters Point", "Bayview")]:
        pt = nb[nb.neighborhood == name].geometry.iloc[0].representative_point()
        for ax in axes:
            ax.text(pt.x, pt.y, lab, fontsize=5.8, ha="center", va="center", color="#111",
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")], zorder=5)
    xmin, ymin, xmax, ymax = city.total_bounds
    for ax in axes:
        ax.set_xlim(xmin - 500, xmax + 500)
        ax.set_ylim(ymin - 500, ymax + 500)
    ch = g[g.change != ""]
    ch.plot(ax=axes[1], color=ch.change.map(chg), edgecolor="white", linewidth=0.3)
    nb.boundary.plot(ax=axes[1], color="#555", linewidth=0.35)
    axes[1].set_title("B. Change vs. prior 12 months (95% hot spots)", fontsize=10, loc="left")
    axes[1].legend(handles=[Patch(color=v, label=k) for k, v in chg.items()],
                   loc="lower left", fontsize=7, frameon=False)
    # scale bar: 1 mile
    x0, y0 = g.total_bounds[2] - 9000, g.total_bounds[1] + 1500
    for ax in axes:
        ax.plot([x0, x0 + 5280], [y0, y0], color="black", lw=2)
        ax.text(x0 + 2640, y0 + 500, "1 mile", ha="center", fontsize=7)
        ax.annotate("N", xy=(x0 + 7600, y0 + 3200), xytext=(x0 + 7600, y0 + 800),
                    ha="center", fontsize=8, arrowprops=dict(arrowstyle="-|>", lw=1))
    fig.text(0.01, 0.01, "Getis-Ord Gi* on 1,000-ft hexagons (queen contiguity). "
             "Neighborhood outlines: DataSF Analysis Neighborhoods. "
             "Source: SFPD Incident Reports via DataSF.", fontsize=6.5, color="#444")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.93, bottom=0.05, wspace=0.03)
    fig.savefig(f"{a.out}/fig_hotspot_map.png", dpi=300)
    print(json.dumps(summary, indent=2))
    print(zt.to_string(index=False))


if __name__ == "__main__":
    main()

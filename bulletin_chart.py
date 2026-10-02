"""Annotated trend chart for the bulletin (Figure 1). Run after sfpd_analysis.py."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.tsa.seasonal import STL

m = pd.read_csv("output/monthly_counts.csv", index_col=0, parse_dates=True).iloc[:, 0]
stl = STL(m, period=12, robust=True).fit()
plt.rcParams.update({"font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(figsize=(7.3, 2.55))
ax.fill_between(m.index, m.values, color="#c9d6e3", lw=0)
ax.plot(m.index, m.values, color="#1f4e79", lw=1.2, label="Monthly reports")
ax.plot(m.index, stl.trend, color="#b2182b", lw=1.4, ls="--", label="Trend, seasonality removed")


def note(date, y, tdate, ty, txt):
    ax.annotate(txt, (pd.Timestamp(date), y), (pd.Timestamp(tdate), ty), fontsize=7,
                ha="center", va="center", color="#222",
                arrowprops=dict(arrowstyle="-", lw=0.6, color="#444"))


note("2019-10-01", 2628, "2019-04-01", 2850, "Peak: 2,628 (Oct 2019)")
note("2020-04-01", 760, "2020-09-01", 350, "Pandemic lockdown")
note("2023-08-01", 2150, "2023-08-01", 2650, "Enforcement campaign\nannounced (Aug 2023)")
note("2026-03-01", 249, "2026-03-01", 1050, "Low: 249\n(Mar 2026)")
ax.set_ylabel("Reports per month")
ax.set_ylim(0, 3000)
ax.margins(x=0.01)
ax.legend(frameon=False, fontsize=7, loc="upper right", bbox_to_anchor=(1, 1.02))
ax.grid(axis="y", color="#e5e5e5", lw=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig("output/fig_bulletin_trend.png", dpi=300)

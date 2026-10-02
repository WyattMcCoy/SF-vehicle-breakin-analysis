# Vehicle Break-Ins in San Francisco: Hot Spot and Trend Analysis

A crime analysis portfolio project using public SFPD incident data. It produces a
Getis-Ord Gi* hot spot map, a statistical trend analysis, and a two-page
intelligence bulletin.

**Data:** [Police Department Incident Reports: 2018 to Present](https://data.sf.gov/Public-Safety/Police-Department-Incident-Reports-2018-to-Present/wg3w-h783), DataSF
**Focus:** Larceny from vehicles (car break-ins). Change `--subcategory` to study something else.
**Tools:** Python (pandas, statsmodels, scipy), DuckDB SQL, QGIS or ArcGIS Pro

## Files

| File | What it does |
|---|---|
| `sfpd_analysis.py` | Downloads, cleans, and analyzes the data; writes charts, tables, `summary.json`, and a point layer for GIS |
| `queries.sql` | The same analysis in SQL (DuckDB) |
| `hotspot_gi.py` | Gi* hot spot analysis in Python, if the QGIS plugin gives you trouble |
| `hotspot_analysis.py` | Full hot spot workflow used for the bulletin: Gi* for both periods, change classes, sensitivity check, map |
| `bulletin_chart.py` | Annotated trend chart used in the bulletin |
| `explore.py` | First look at a data sample (rows vs. incidents) |
| `bulletin_template.md` | Two-page bulletin structure with writing guidance |

## Step 1: Get the data and run the trend analysis

```bash
pip install -r requirements.txt
python sfpd_analysis.py --start 2019-01-01
```

The API works without a key but is throttled. A free app token from DataSF speeds it
up: `export SODA_APP_TOKEN=yourtoken`. If the API gives you trouble, export the full
dataset as CSV from the DataSF page and run `python sfpd_analysis.py --csv yourfile.csv`.
Run with `--list-subcategories` first to confirm the exact label.

What the script does to the data, and why:

- **Drops supplemental reports, then deduplicates on `incident_id`.** Supplements are
  follow-up reports with their own ID, and a report with several offense codes gets
  one row per code. Either one inflates counts if you just count rows.
- **Drops the current month.** It is incomplete, and including it creates a fake decline.
- **Flags bad or missing coordinates.** Some records are withheld or ungeocoded;
  the share is reported in `summary.json` and belongs in your limitations section.

Analysis outputs:

- Monthly counts, 3-month average, and STL seasonal decomposition
- Mann-Kendall trend test (Kendall's tau on the deseasonalized series) and Sen's slope
  with a 95% confidence interval: "is the trend real, and how steep is it?"
- Last 12 months vs. prior 12, citywide and by police district
- Hour-by-weekday heat map and top intersections

## Step 2: Hot spot map in QGIS

1. **Load points.** Layer > Add Layer > Add Delimited Text Layer >
   `output/points_for_gis.csv`. X = `longitude`, Y = `latitude`, CRS = EPSG:4326.
   (Or drag in `points_for_gis.gpkg`.)
2. **Filter to the analysis window.** Right-click > Filter: `"period" = 'last_12'`.
3. **Reproject.** Processing Toolbox > Reproject Layer > EPSG:2227
   (California State Plane zone 3, US feet). Distance-based tools need projected units.
4. **Get a boundary.** Download the Analysis Neighborhoods layer from DataSF and
   dissolve it into a city outline (Vector > Geoprocessing > Dissolve).
5. **Build a hex grid.** Vector > Research Tools > Create Grid. Type: Hexagon,
   extent: the city boundary, spacing: 1,000 ft. Then Extract by Location to keep
   hexes that intersect the boundary. Hexagons beat squares here because every
   neighbor is equidistant.
6. **Count incidents per hex.** Vector > Analysis Tools > Count Points in Polygon.
7. **Run Gi\*.** Plugins > Manage and Install > "Hotspot Analysis." Run it on
   `NUMPOINTS` with a distance band or contiguity weights. If the plugin fails to
   load (it depends on PySAL), run `python hotspot_gi.py` instead and open
   `output/hotspots_gi.gpkg`.
8. **Symbolize.** Categorized on `class`: dark to light red for 99/95/90% hot spots,
   blues for cold spots, light gray or transparent for not significant.
9. **Lay it out.** Add a light basemap (XYZ Tiles, e.g. CartoDB Positron), police
   district boundaries as a thin outline, then Project > New Print Layout with
   title, legend, scale bar, north arrow, and a source line. Export at 300 dpi.

**Test your cell size.** Rerun at 500 and 1,500 ft. If the same areas stay hot,
say so in the bulletin; it strengthens the finding. If they move, that is a
limitation to disclose.

**Compare periods.** Run the analysis for `prior_12` too. Hot spots that persist,
emerge, or fade are more useful to a reader than a single snapshot.

### ArcGIS Pro alternative

- **Optimized Hot Spot Analysis** on the points, aggregating into hexagons. It picks
  the scale of analysis and corrects for multiple testing (FDR).
- For a stronger portfolio piece: **Create Space Time Cube By Aggregating Points**
  (1-month time step, 1,000 ft hexes), then **Emerging Hot Spot Analysis**. It labels
  each location as new, intensifying, persistent, diminishing, and so on, which
  combines the map and the trend analysis in one product.

## Step 3: Write the bulletin

Use `bulletin_template.md`. Every number you need is in `output/summary.json` and the
CSV tables; every figure is in `output/`.

## Limitations to acknowledge

- These are **reported** incidents. Car break-ins are widely underreported, and
  reporting rates can shift over time (for example, when online reporting changes).
- Locations are generalized to the nearest intersection or block for privacy, which
  can create artificial point clusters at intersections.
- Records are revised after initial publication, so recent months may change.
- Hot spots show where reported incidents concentrate, not why. Parking density,
  tourist traffic, and patrol presence all shape the pattern.

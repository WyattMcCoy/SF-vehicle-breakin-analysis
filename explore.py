"""
Step 2: explore a sample of the SFPD data before analyzing it.

  python explore.py              # downloads the 5,000 most recent rows
  python explore.py myfile.csv   # or explore a CSV you already have
"""
import io
import sys

import pandas as pd
import requests

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)

if len(sys.argv) > 1:
    df = pd.read_csv(sys.argv[1], low_memory=False)
else:
    print("Downloading a sample from DataSF...")
    r = requests.get("https://data.sf.gov/resource/wg3w-h783.csv",
                     params={"$limit": 5000, "$order": "incident_datetime DESC"},
                     timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), low_memory=False)
    df.to_csv("sample_5000.csv", index=False)

# Portal exports say "Incident ID"; the API says incident_id. Make them match.
df.columns = (df.columns.str.strip().str.lower()
              .str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_"))

print("\n=== 1. Size and columns ===")
print(f"{len(df):,} rows, {len(df.columns)} columns")
print(", ".join(df.columns))

print("\n=== 2. One row, shown top to bottom ===")
print(df.iloc[0].to_string())

print("\n=== 3. Rows vs. incidents ===")
n_ids = df["incident_id"].nunique()
print(f"Rows: {len(df):,}   Unique incident IDs: {n_ids:,}   "
      f"Extra rows: {len(df) - n_ids:,}")

print("\n=== 4. The incident with the most rows ===")
worst = df["incident_id"].value_counts().idxmax()
cols = ["incident_id", "incident_datetime", "report_datetime", "report_type_code",
        "incident_category", "incident_subcategory", "incident_description"]
print(df[df["incident_id"] == worst][cols].to_string(index=False))

print("\n=== 5. Report types ===")
print(df["report_type_description"].value_counts().to_string()
      if "report_type_description" in df else df["report_type_code"].value_counts().to_string())

print("\n=== 6. Top 10 incident categories (by row) ===")
print(df["incident_category"].value_counts().head(10).to_string())

print("\n=== 7. Missing locations ===")
missing = df["latitude"].isna().mean() * 100
print(f"{missing:.1f}% of rows have no latitude/longitude")

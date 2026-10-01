import pandas as pd, re
from config import METADATA_CSV

df = pd.read_csv(METADATA_CSV)
bad = df[~df["date"].astype(str).str.match(r"^[\d০-৯]{1,2}-[\d০-৯]{1,2}-[\d০-৯]{4}$")]
print(f"{len(bad)} of {len(df)} dates are not dd-mm-yyyy\n")
print(bad[["date", "division", "source_page"]].head(20).to_string())
print("\ndistinct bad values:", bad["date"].astype(str).unique()[:20])
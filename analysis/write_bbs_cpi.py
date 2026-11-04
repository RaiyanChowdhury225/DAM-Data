"""
write_bbs_cpi.py - writes the verified BBS CPI months into data/external/bbs_cpi.csv.
Run from the analysis folder:  python write_bbs_cpi.py
(Overwrites the empty template. Source: BBS monthly CPI releases, base 2021-22 = 100.
 Only months actually read from BBS reports are included; add more rows below as you collect them.)
"""
import io
import pandas as pd
from dam_common import EXT

DATA = """month,general_cpi,food_cpi,nonfood_cpi,base,source
2023-07,112.89,112.74,113.02,2021-22=100,BBS CPI release Sep 2023 (Table 1.1/1.3)
2023-08,117.06,120.08,114.61,2021-22=100,BBS CPI release Sep 2023 (Table 1.1/1.3)
2023-09,118.83,122.47,115.87,2021-22=100,BBS CPI release Sep 2023 (Table 1.1/1.3)
2023-10,120.24,123.90,117.27,2021-22=100,BBS CPI release Dec 2024 (Table 1.1/1.3)
2023-11,119.10,120.04,118.33,2021-22=100,BBS CPI release Dec 2024 (Table 1.1/1.3)
2023-12,118.40,117.48,119.16,2021-22=100,BBS CPI release Dec 2024 (Table 1.1/1.3)
2024-01,119.60,118.30,120.66,2021-22=100,BBS CPI release Mar 2024 (Table 1.1/1.3)
2024-02,120.09,119.07,120.92,2021-22=100,BBS CPI release Mar 2024 (Table 1.1/1.3)
2024-03,121.60,121.50,121.69,2021-22=100,BBS CPI release Mar 2024 (Table 1.1/1.3)
2024-10,133.32,139.58,128.22,2021-22=100,BBS CPI release Dec 2024 (Table 1.1/1.3)
2024-11,132.66,136.61,129.44,2021-22=100,BBS CPI release Dec 2024 (Table 1.1/1.3)
2024-12,131.30,132.65,130.19,2021-22=100,BBS CPI release Dec 2024 (Table 1.1/1.3)
2025-02,131.29,130.08,132.26,2021-22=100,BBS CPI release Apr 2026 (Table 1.3)
2025-03,132.98,132.35,133.49,2021-22=100,BBS CPI release Apr 2026 (Table 1.3)
2025-04,133.50,133.21,133.74,2021-22=100,BBS CPI release Apr 2026 (Table 1.3)
2026-02,143.28,142.18,144.18,2021-22=100,BBS CPI release Apr 2026 (Table 1.3)
2026-03,144.56,143.25,145.62,2021-22=100,BBS CPI release Apr 2026 (Table 1.3)
2026-04,145.57,144.39,146.54,2021-22=100,BBS CPI release Apr 2026 (Table 1.3)
"""

df = pd.read_csv(io.StringIO(DATA.strip()))
f = EXT / "bbs_cpi.csv"
df.to_csv(f, index=False)
print(f"Wrote {len(df)} rows to {f}")
print(df[["month", "general_cpi", "food_cpi"]].to_string(index=False))

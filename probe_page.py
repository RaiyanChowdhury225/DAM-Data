"""
probe_page.py — print the first rows of a DAM report page so the column layout
can be read off before scraping.

    python probe_page.py <url>
"""
import sys

import requests
from bs4 import BeautifulSoup

from config import TIMEOUT, CA_BUNDLE

url = sys.argv[1]
html = requests.get(url, timeout=TIMEOUT, verify=CA_BUNDLE).text
tables = BeautifulSoup(html, "html.parser").find_all("table")

print(f"{len(tables)} table(s) on the page; showing the first one\n")

rows = tables[0].find_all("tr")
for r, row in enumerate(rows[:4]):
    cells = row.find_all(["td", "th"])
    print(f"row {r}  ({len(cells)} cells)")
    for i, cell in enumerate(cells):
        text = " ".join(cell.get_text(strip=True).split())[:24]
        link = "  <-- has PDF link" if cell.find("a") else ""
        print(f"    [{i}] {text!r}{link}")
    print()
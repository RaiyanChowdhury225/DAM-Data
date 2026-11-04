"""
fix_filenames.py — rename PDFs that were downloaded before the dates were repaired.

A PDF's name is  DATE_DIVISION_HASH.pdf, and the date becomes the dataset's
`date` column. Files saved under a mangled date (26-01-20, 20222-11-06) or a
typo'd one would otherwise keep that date forever, because the manifest already
records them as downloaded. The hash is derived from the URL, so it identifies
each file reliably: we look up the correct name for that hash and rename.

Run after scraper.py (which writes date_iso) whenever date_repairs.csv changes.

    python fix_filenames.py            # show what would change
    python fix_filenames.py --apply    # do it
"""
import sys

import pandas as pd

from config import METADATA_CSV, PDF_DIR, DOWNLOAD_MANIFEST
from downloader import generate_filename, url_hash

apply = "--apply" in sys.argv

meta = pd.read_csv(METADATA_CSV).drop_duplicates(subset="pdf_url")   # first record wins, as in downloader.py
meta = meta[meta["date_iso"].fillna("").astype(str).str.strip() != ""]

expected = {}            # url hash -> (correct filename, date_iso, url)
for _, r in meta.iterrows():
    name = generate_filename(r["date_iso"], r["division"], r["pdf_url"])
    if name:
        expected[url_hash(r["pdf_url"])] = (name, r["date_iso"], r["pdf_url"])

renames, orphans, clashes = [], [], []
for f in sorted(PDF_DIR.glob("*.pdf")):
    hit = expected.get(f.stem[-12:])
    if hit is None:
        orphans.append(f.name)               # not in the metadata at all
    elif hit[0] != f.name:
        (clashes if (PDF_DIR / hit[0]).exists() else renames).append((f.name, hit[0]))

print(f"{len(list(PDF_DIR.glob('*.pdf')))} PDFs on disk")
print(f"{len(renames)} to rename, {len(clashes)} clash with an existing file, {len(orphans)} unrecognised\n")
for old, new in renames:
    print(f"  {old}  ->  {new}")
for old, new in clashes:
    print(f"  CLASH {old} and {new} both exist - keep one by hand")
for name in orphans[:10]:
    print(f"  UNRECOGNISED {name}")

if apply:
    for old, new in renames:
        (PDF_DIR / old).rename(PDF_DIR / new)
    if DOWNLOAD_MANIFEST.exists():
        man = pd.read_csv(DOWNLOAD_MANIFEST)
        fixed = 0
        for i, row in man.iterrows():
            hit = expected.get(url_hash(row["pdf_url"]))
            if hit and (row["filename"] != hit[0] or row["date"] != hit[1]):
                man.at[i, "filename"], man.at[i, "date"] = hit[0], hit[1]
                fixed += 1
        man.to_csv(DOWNLOAD_MANIFEST, index=False, encoding="utf-8-sig")
        print(f"\nrenamed {len(renames)} files, corrected {fixed} manifest rows")
else:
    print("\n(dry run - nothing changed; add --apply)")
# DAM-Data
# DAM Agricultural Market Data Pipeline

A reproducible Data Wrangling pipeline for collecting and transforming historical agricultural market reports published by the **Bangladesh Department of Agricultural Marketing (DAM)**.

The long-term goal of this project is to create a research-ready historical dataset containing agricultural commodity prices from markets across Bangladesh.

---

## Project Goal

DAM publishes daily agricultural market reports as PDF documents. These reports contain structured tabular information about commodities, prices, and divisions, but the information is distributed across thousands of PDF files and is not provided as a convenient machine-readable dataset.

This project aims to:

1. Collect historical DAM report metadata.
2. Download the corresponding PDF reports.
3. Extract structured data from the Bangla PDF tables.
4. Clean and standardize the extracted data.
5. Produce a reproducible machine-readable dataset suitable for research and analysis.

---

## Current Pipeline

```text
DAM Website
    │
    ▼
Metadata Scraper              scraper.py        → data/report_metadata.csv
    │
    ▼
PDF Downloader                downloader.py     → data/pdfs/ + data/download_manifest.csv
    │
    ▼
PDF Extraction                extractor.py      → data/extracted/prices_raw.csv
    │
    ▼
Cleaning & Standardization    clean.py          → data/final/prices.csv
    │
    ▼
Modelling Table (optional)    add_target.py     → data/final/prices_modeling.csv
```

All stages can be run in order with a single command:

```bash
python main.py
```

### Current Status

* [x] Phase 1 — Metadata scraping
* [x] Phase 2 — PDF downloading
* [x] Phase 3 — PDF table extraction
* [x] Phase 4 — Data cleaning and normalization
* [ ] Phase 5 — Full-corpus run, accuracy validation, Excel-format reports

---

# Phase 1 — Metadata Scraping

The metadata scraper collects information about each available report:

```text
serial
date
division
pdf_url
source_page
```

The scraper currently handles two DAM report page layouts:

### Current Reports

```text
Serial | Date | Dhaka | Chittagong | Khulna | ...
```

### Historical Archive

```text
(empty) | (empty) | Date | Dhaka | Chittagong | Khulna | ...
```

Instead of creating separate parsers, the scraper uses layout configuration to support both structures. This makes the scraper easier to maintain if DAM changes the table layout.

---

## Why Selenium Is Not Used

During investigation of the DAM website, it was found that the PDF "Download" buttons are regular HTML `<a>` elements containing the direct PDF URL.

Therefore, browser automation is unnecessary. The scraper uses `requests` and `BeautifulSoup`, which is simpler, faster, and more reproducible than using Selenium.

---

# Metadata Dataset

The scraper produces:

```text
data/report_metadata.csv
```

Duplicate PDF URLs are removed from the **download queue**, but the original metadata is preserved, because duplicate metadata relationships may still be meaningful.

| Metric | Count |
|---|---|
| Metadata records | 7,893 |
| Archive records | 4,988 |
| Current records | 2,905 |
| Unique PDF URLs | 7,705 |
| Duplicate PDF URLs | 188 |

---

# Phase 2 — PDF Downloader

The downloader reads `data/report_metadata.csv` and downloads the associated PDFs into `data/pdfs/`.

The PDFs are intentionally **not stored in GitHub** because the corpus contains thousands of files and would make the repository unnecessarily large.

## Downloader Features

### Deterministic filenames

Each PDF receives a filename based on `date + division + URL hash`:

```text
2026-08-04_Dhaka_a81f3c92e1ab.pdf
```

The URL hash ensures that filenames remain unique and deterministic. Later stages read the date and division back out of the filename.

### Division normalization

Bangla division names are converted to English:

```text
ঢাকা        → Dhaka
চট্টগ্রাম   → Chittagong
খুলনা       → Khulna
রাজশাহী     → Rajshahi
বরিশাল      → Barisal
রংপুর       → Rangpur
সিলেট       → Sylhet
ময়মনসিংহ    → Mymensingh
```

### Other features

* Duplicate URL removal before downloading
* Existing-file detection (already downloaded PDFs are skipped)
* Automatic retries with exponential backoff
* PDF signature validation (`%PDF`), so HTML error pages are not saved as PDFs
* Download manifest at `data/download_manifest.csv`
* Checkpointing, logging, and progress tracking
* `TEST_MODE`, `TEST_LIMIT`, and `DRY_RUN` settings for safe testing

---

# Phase 3 — PDF Extraction

```bash
python extractor.py --build-glyph-map     # run once, before the first extraction
python extractor.py                       # extract all PDFs in data/pdfs/
python extractor.py --file <path.pdf>     # extract one PDF and print the rows
python extractor.py --survey              # list the font combinations used by the corpus
```

Output: `data/extracted/prices_raw.csv` — the raw layer, with Bangla text preserved and no cleaning applied.

```text
source_file, source_url, page_number, date_raw, division_raw,
serial_raw, commodity_type_raw, commodity_name_raw, unit_raw,
price_raw, min_price_raw, max_price_raw
```

Only the **current** min/max price is extracted. The previous-month, previous-year, and percentage-change columns in the reports are deliberately ignored: they can be recalculated from the dataset's own historical observations if needed.

## The Bangla text problem

The reports are text-based PDFs, not scans, but the text extracted by standard tools is corrupted:

| Extracted with a standard tool | Actual text |
|---|---|
| `র্োংিোরদশ` | `বাংলাদেশ` |
| `প্রনি কেনি` | `প্রতি কেজি` |

The cause is the PDF's ToUnicode map, written by Excel, which maps several different glyphs to the same character. The information is destroyed at that layer, so no translation dictionary can recover it.

**The solution does not use OCR.** The embedded Nikosh/NikoshBAN font subsets are intact, so the glyph-to-character map is rebuilt from the font itself:

1. The font's own character map gives the plain letters.
2. Characters dropped by the font subsetter (e.g. hasanta ্, chandrabindu ঁ) are filled in using the fact that Bengali glyphs are stored in Unicode order.
3. The font's GSUB rules are read backwards to decode conjuncts (ম্ন, ক্ষ), half forms, ra-phala, and reph.
4. The rebuilt map is given to pdfminer, so table extraction then works normally.

Glyphs are stored in the order they are drawn, so the text is then reordered into logical order: pre-base vowel signs (ি, ে, ৈ) are moved after their consonant cluster, reph (র্) is moved in front of its cluster, ে + cluster + া is combined into ো, Bangla digits are unified with ASCII digits, and the result is NFC-normalized.

### Re-distilled PDFs

A small number of reports have been re-saved through Ghostscript (e.g. "PDF24 Creator"), which strips the font rules but keeps the original glyph IDs. For these, the extractor reuses a glyph map learned from the normal PDFs:

```bash
python extractor.py --build-glyph-map     # writes data/nikosh_glyph_map.json
```

Rebuild this file whenever new PDFs are added.

## Table extraction

Column positions differ between divisions — some have a commodity-type column, some have a "fair price" column, some use ditto marks — so columns are located by content rather than by fixed index:

* The **unit column** is the column containing the most unit words (কেজি, লিটার, টি).
* The **current price column** is the first mostly-numeric column to its right, which skips the fair-price column.
* The **name** is built from the text cells between the serial number and the unit column.

Source irregularities handled:

| Irregularity | Handling |
|---|---|
| Table continues onto the next page, losing a border | A border is added at the edge of the vertical rules |
| Missing rule between two rows merges their price cells | The price is read from each row's own vertical band |
| Text overflowing from a neighbouring row (hidden on the page, present in the file) | Overlapping text lines are removed, keeping the line drawn last |
| Ditto marks (`,,`, `"`) or a blank unit | The unit is carried down from the row above |
| Merged commodity-type cells | The type is carried down to the rows below |
| Missing prices written as `*`, `-`, or an empty cell | Stored as null, never as zero |

The serial number is stored as source information only. It repeats and is inconsistent across reports, so it is **not** a primary key.

---

# Phase 4 — Cleaning and Standardization

```bash
python clean.py
```

Input: `data/extracted/prices_raw.csv` and `data/commodity_map.csv`
Output: `data/final/prices.csv`

**One row = one commodity observation for one division on one date.**

```text
date, division, commodity_type, commodity_name, unit,
min_price, max_price, source_file, source_url, page_number
```

## Commodity mapping

Divisions write the same commodity differently (মসুর ডাল (উন্নত), মসুর (উন্নত), মশুর ডাল সরু (উন্নত)), so a hand-checked crosswalk maps each distinct raw name to one standard commodity:

```text
data/commodity_map.csv
```

This file is a research artifact in its own right and is version-controlled. Any raw name missing from it is **reported and skipped, never silently dropped**, so new wordings in older reports are caught.

## Unit standardization

| Raw unit | Standard |
|---|---|
| প্রতি কেজি, 1 কেজি, 1.50-2 কেজি, (blank) | `kg` |
| 1 লিটার, 01লিটার, 1 লিটার (925 গ্রাম) | `litre` |
| 5 লিটার | `5_litre` |
| প্রতিটি | `piece` |
| 4টি, 04 টি | `4_pieces` |

Unit **labels** are standardized, but **prices are never rescaled**. A 5-litre can and a hali of 4 eggs are priced as they are sold, so every value remains traceable to the source report.

## Null handling

The reports write `0.00 - 0.00` when no price was collected. These become null in the clean dataset. Missing prices are never converted to zero.

---

# Phase 5 — Modelling Table (optional)

```bash
python add_target.py                       # target = next average price
python add_target.py --target direction    # target = up / down / same
```

Output: `data/final/prices_modeling.csv`

The published dataset deliberately contains **no target column and no derived variables**. Seasons, price changes, and prediction targets can all be derived from the dataset itself, so storing them would only add assumptions. This script builds such a table separately for modelling work, by shifting each division + commodity series to its next observation and recording the gap in days between reports.

---

# Project Structure

```text
DAM-Data/
│
├── main.py                 # runs the whole pipeline
├── scraper.py
├── downloader.py
├── extractor.py
├── clean.py
├── add_target.py
├── validate_metadata.py
├── check_raw.py
├── config.py
├── logger_config.py
│
├── data/
│   ├── report_metadata.csv
│   ├── download_manifest.csv
│   ├── commodity_map.csv
│   ├── nikosh_glyph_map.json
│   ├── pdfs/
│   ├── extracted/
│   │   └── prices_raw.csv
│   └── final/
│       ├── prices.csv
│       └── prices_modeling.csv
│
├── logs/
└── README.md
```

Excluded from Git (see `.gitignore`):

```text
data/pdfs/
data/download_manifest.csv
logs/
```

---

# Requirements

Python 3.x

```bash
pip install requests beautifulsoup4 pandas pdfplumber fonttools
```

---

# Running the Pipeline

```bash
git clone <REPOSITORY_URL>
cd DAM-Data

python main.py                          # everything, in order
python main.py --from extract           # extract, clean, target
python main.py --only clean             # a single stage
python main.py --skip scrape download   # everything else
```

Each stage is the same script that can be run by hand; `main.py` only decides the order and stops when a stage fails.

Use `TEST_MODE` in `config.py` before running a full download.

---

# Data Quality Checks

```bash
python validate_metadata.py   # metadata: record counts, missing values, duplicates
python check_raw.py           # raw layer: name/unit variants, min > max, empty units
```

`clean.py` additionally reports unmapped commodity names, unknown units, swapped min/max values, rows without a price, and duplicate observations (the same commodity twice on one date, which happens when the mapping merges two varieties).

---

# Research Reproducibility

Each stage produces an explicit artifact that can be validated independently:

```text
Scraper    → report_metadata.csv
Downloader → PDF corpus + download_manifest.csv
Extractor  → prices_raw.csv          (raw layer, Bangla preserved)
Cleaner    → prices.csv              (final dataset)
```

The raw layer is kept so that every cleaned value can be traced back to the file, page, and original text it came from. The repository stores the code and the commodity mapping rather than thousands of PDFs, so the corpus can be regenerated from the metadata.

---

# Known Limitations

* Reports published as Excel files (around 2022) are not yet handled; only PDFs are extracted.
* A small number of names are garbled where two text lines overlap inside a single cell in the source file. These are handled through the commodity mapping.
* Some Rangpur reports have no unit on their first rows, so the unit defaults to `kg` per the report header.
* Extraction accuracy has not yet been measured against a manually verified sample.
* Prices are retail quotes from a small number of named markets per division, not a statistical sample of all markets.

---

# Future Work

* Run the pipeline over the full corpus of ~7,705 reports.
* Measure extraction accuracy on a stratified manual sample and publish per-field accuracy.
* Add support for the Excel-format reports, reusing the same cleaned schema.
* Document coverage gaps by division and date.

---

# Disclaimer

This project is an academic Data Wrangling and research project using publicly available agricultural market reports published by the Bangladesh Department of Agricultural Marketing.

The project does not claim ownership of the original government reports. The downloaded PDFs are kept locally and are not included in this repository.

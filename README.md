# DAM-Data

A reproducible ETL pipeline that turns the daily agricultural market-price reports of Bangladesh's
**Department of Agricultural Marketing (DAM)** into a structured, provenance-tracked dataset.

DAM publishes retail prices for about 75 commodities in all eight divisions every working day, but only as
PDF files whose Bangla text cannot be extracted with standard tools. DAM-Data recovers that text from the
fonts embedded in the PDFs, without OCR, rebuilds the tables, standardises commodity names and units, and
records for every observation the report, URL and page it came from.

| | |
|---|---|
| Observations | 194,568 (one commodity, one division, one date) |
| Reports | 4,590 PDFs, 4,369 with curated rows |
| Coverage | 10 June 2020 – 28 September 2026, with gaps (see [Limitations](#limitations)) |
| Commodities | 75 in 14 categories: cereals, pulses, oils, spices, vegetables, fish, meat, poultry, eggs, fruit, salt, milk… |
| Prices | Reported minimum **and** maximum retail price, BDT |
| Provenance | Source file, source URL and page number on every row |

---

## Quick start

```bash
git clone https://github.com/RaiyanChowdhury225/DAM-Data.git
cd DAM-Data
pip install -r requirements.txt        # Python 3.14; versions are pinned

# use the released dataset directly
python -c "import pandas as pd; print(pd.read_csv('data/final/prices.csv').head())"

# or rebuild everything from the DAM website
python main.py                         # scrape -> download -> extract -> clean -> analyses
python -m pytest                       # checks on the crosswalk, date repairs and filenames
```

The PDFs are not stored in the repository. `python main.py` downloads them into `data/pdfs/` (about 4,600 files).
To try the pipeline on a few files first, set `TEST_MODE = True` in [config.py](config.py).

---

## The dataset

`data/final/prices.csv`: UTF-8 (with BOM, so Excel shows Bangla correctly), one row per observation.

| Column | Description |
|---|---|
| `date` | Report date, `YYYY-MM-DD` |
| `division` | Barisal, Chittagong, Dhaka, Khulna, Mymensingh, Rajshahi, Rangpur, Sylhet |
| `commodity_type` | Standardised category (e.g. `Rice`, `Pulse`, `Vegetable`) |
| `commodity_name` | Standardised commodity (e.g. `Rice (coarse/hybrid)`, `Lentil (fine)`) |
| `unit` | `kg`, `litre`, `5_litre`, `piece`, `4_pieces` |
| `min_price`, `max_price` | Reported retail range in BDT; empty where the report gives no price |
| `source_file` | PDF filename, `YYYY-MM-DD_Division_hash.pdf` |
| `source_url` | URL of the PDF on the DAM website |
| `page_number` | Page of the PDF the row was read from |

Design decisions:

* **The price range is kept.** Reducing min and max to a mid-price would discard dispersion within a division that cannot be recovered later.
* **No derived columns.** Previous-month and previous-year prices, percentage changes, seasons and prediction targets can all be recomputed, and a stored derived value can silently contradict its source. They live in the separate analysis layer (`prices_features.csv`, built by `features.py`).
* **The source condition is preserved.** Absent prices are null, never zero. Unit labels are standardised but prices are never rescaled: a five-litre can of oil and four eggs are priced as sold.
* **Series are commodity × unit × division.** Never pool different units.

---

## Pipeline

```text
DAM website
   │  scraper.py        report_metadata.csv      date, division, URL of every listed report (+ repaired ISO date)
   ▼
   │  downloader.py     data/pdfs/ + download_manifest.csv
   ▼
   │  extractor.py      data/extracted/prices_raw.csv     raw layer: original Bangla text, unparsed prices
   ▼
   │  clean.py          data/final/prices.csv             curated dataset
   ▼
   │  features.py       data/final/prices_features.csv    analysis layer (derived variables)
   ▼
   │  analysis/rq*.py   data/final/analysis/              fitness-for-use analyses and figures
```

```bash
python main.py                          # every stage, in order
python main.py --from extract           # extraction and everything after it
python main.py --only clean             # one stage
python main.py --skip scrape download   # everything except these
```

Each stage is an ordinary script that can also be run by hand; `main.py` only fixes the order and stops at the
first stage that fails. Every stage writes a named file that can be inspected on its own, and all stages are
idempotent: filenames are deterministic, downloaded files are not fetched again, and an interrupted download
resumes from the manifest.

### 1. Metadata: `scraper.py`

The DAM website lists reports in tables, one per page (current reports plus yearly archives). The pages and their
column layout are configured in [config.py](config.py) (`REPORT_PAGES`, `LAYOUT`), so a changed layout needs a
config change, not a new parser. `probe_page.py <url>` prints a page's first rows to read the layout off.

The site contains date typos (`২৪-০৩-৩০৩২`, `২০-০১-২৬`, `১৯-.৭-২০২১`). Each was checked against the header of the
report itself and recorded in [data/date_repairs.csv](data/date_repairs.csv), keyed by report URL. The scraper adds
`date_iso` and `date_status` (`ok`, `corrected`, `invalid`), and reports any new invalid date instead of guessing it.

Last scrape: 7,976 records, 7,792 unique URLs (4,607 PDF, 3,083 Excel, 102 other).

### 2. Download: `downloader.py`

* Files are named `YYYY-MM-DD_Division_hash.pdf`, where `hash` is the first 12 hex digits of the URL's SHA-256. The hash identifies a report even if its date is later repaired; `fix_filenames.py` renames files when `date_repairs.csv` changes.
* Duplicate URLs are removed from the download queue (the first listing wins) but kept in the metadata.
* Retries with exponential backoff; responses that are not PDFs (`%PDF` signature) are rejected, so HTML error pages are never stored as reports.
* Every outcome is written to `data/download_manifest.csv`.
* `dam.gov.bd` does not send its intermediate certificate. `data/dam_chain.pem` adds it to the certifi bundle; rebuild it with `python fetch_chain.py` if the site's certificate changes.

### 3. Extraction: `extractor.py`

```bash
python extractor.py                       # all PDFs in data/pdfs/ (4 worker processes; --jobs N to change)
python extractor.py --file <path.pdf>     # one PDF, rows printed
python extractor.py --survey              # font combinations used across the corpus
python extractor.py --build-glyph-map     # rebuild data/nikosh_glyph_map.json (see below)
```

**The Bangla text problem.** The reports are text PDFs, not scans, but standard tools return corrupted text:

| Standard extraction | Actual text |
|---|---|
| `র্োংিোরদশ` | `বাংলাদেশ` |
| `প্রনি কেনি` | `প্রতি কেজি` |

A PDF stores glyph IDs and a separate ToUnicode table that says which character each glyph is. In these files the
table, written by a spreadsheet application, maps several different glyphs to the same character, so the
information is lost at that layer and no dictionary or post-correction can recover it.

The embedded Nikosh/NikoshBAN font programs are intact, so the mapping is rebuilt from the font itself:

1. The font's character map gives the plain letters.
2. Characters dropped by font subsetting (e.g. hasanta ্) are restored by interpolation. This is done only when the number of missing glyphs equals the number of missing code points.
3. The font's GSUB substitution rules, read in reverse and resolved recursively, give each conjunct, half-form, ra-phala and reph glyph as the characters that produce it.
4. Glyphs are stored in drawing order, so the text is reordered into logical order: pre-base vowel signs move after their consonant cluster, and reph moves in front of its cluster. The result is then NFC-normalised.

Some reports were re-saved through Ghostscript, which strips the substitution rules but keeps the glyph IDs. For
these, a reference map learned from the rest of the corpus is used (`data/nikosh_glyph_map.json`). Rebuild it with
`--build-glyph-map` after adding many new PDFs.

Compared with alternatives on the same 1,517 table rows, the PDF's own ToUnicode map recovers 2.2% of commodity
names exactly, Tesseract's best Bengali model 82.3%, and this method 99.8% (on the manually checked sample). See
[evaluation/](evaluation/).

**Tables.** Columns are located by content, because layouts differ between divisional offices:

* the **unit column** is the one containing the most unit expressions (কেজি, লিটার, টি);
* the **current-price column** is the first column to its right that holds `min - max` pairs, never the column headed as the fair price (যৌক্তিক মূল্য).

| Source irregularity | Handling |
|---|---|
| Table continues across a page, losing a border | Closing rule synthesised |
| Missing rule between rows merges their price cells | Price read within each row's own band |
| Text overflowing invisibly from a neighbouring row | Overlapping lines resolved by drawing order |
| Ditto marks (`,,`, `"`) and merged cells | Value carried down from the row above, but never past a row that could not be read |
| Glyphs drawn twice for a bold effect | De-duplicated |
| Fonts renamed to generic names (`CIDFont+F1`) | Identified by the name stored inside the font program |
| Absent prices written as `*`, `-`, `0.00` or blank | Null, never zero |

The output `prices_raw.csv` keeps the original Bangla names and price strings.

### 4. Standardisation: `clean.py`

* **Commodity names** go through the hand-checked crosswalk [data/commodity_map.csv](data/commodity_map.csv) (raw Bangla type + name → standard type + name), not string matching, because similar spellings can be the same commodity or different products. Rice is the hardest case: reports name varieties that differ by division, so varieties are mapped onto a small set of grades. This is a standardisation decision, not a translation, and is published so it can be contested.
* **Units** map to `kg`, `litre`, `5_litre`, `piece`, `4_pieces`.
* Names or units missing from the crosswalk are **reported and left out**, never guessed. The rows stay in the raw layer. `python list_names.py` lists every raw name and unit to extend the crosswalk.
* The crosswalk is validated on load: a row without a standard name, or a raw name mapped two different ways, stops the run.

---

## Validation

Every stage checks its own output:

| Stage | Checks |
|---|---|
| Metadata | Missing or duplicate URLs, invalid dates (`python validate_metadata.py`) |
| Download | Request outcome and PDF signature per file, in the manifest |
| Extraction | Rows and rows without a price per report; failed files; duplicate reports skipped |
| Cleaning | Unmapped names, unknown units, non-ISO dates, swapped min/max, missing prices, duplicate observations |
| Tests | `python -m pytest`: crosswalk completeness, URL-keyed date repair, reproducibility of the stored metadata dates, filename format |

Structural checks cannot show that a value matches its source, so extraction accuracy was measured by hand.

### Accuracy

A stratified random sample of 554 observations from 111 reports (seed 42) was compared field by field against
images of the source table rows ([evaluation/verification_results.csv](evaluation/verification_results.csv)).

* **First extractor (v1):** 89.7% of rows fully correct (95% CI 86.9–92.0%), and 99.8% of commodity names correct. The errors were concentrated in Khulna, Sylhet and Dhaka, and traced to three parser rules: the fair-price column read as the current price, a minimum discarded as overflow, and a unit carried past a new one.
* **Current extractor (v2):** fixes 56 of those 57 errors without changing any correct row. On 165 observations from 33 reports not used to design the fixes ([evaluation/holdout_results.csv](evaluation/holdout_results.csv)), it made no errors (95% CI lower bound 97.7%).

The released dataset is the v2 extraction. A fresh random sample of it has **not** yet been checked, so v2's
complete-row accuracy on the whole corpus is not measured; the figures above are what has been measured.

---

## Analysis

`analysis/` holds five exploratory fitness-for-use analyses used in the accompanying paper. They read
`prices.csv` without modifying it and write to `data/final/analysis/`.

| Script | Question |
|---|---|
| `rq1_seasonality.py` | Which commodities show a seasonal profile that repeats across years? |
| `rq2_holiday_effects.py` | Do prices move around Ramadan and the two Eids? (event windows, with placebo dates) |
| `rq3_price_change_2023_2025.py` | Fixed-basket nominal price change over matched calendar months |
| `rq4_cpi_comparison.py` | DAM price change against the BBS consumer price index |
| `rq5_shocks_and_anomalies.py` | Price shocks against a trailing 12-month baseline |
| `paper_figures.py` | Figures for the paper |

Hand-collected inputs are in `data/external/`: BBS CPI levels transcribed from the monthly releases
(`bbs_cpi.csv`, written by `write_bbs_cpi.py`) and festival dates (Umm al-Qura calendar). All results are
preliminary because of the coverage gaps below.

---

## Repository layout

```text
DAM-Data/
├── main.py                 run the pipeline
├── config.py               URLs, page layouts, paths, download settings
├── scraper.py              1. metadata
├── downloader.py           2. PDFs
├── extractor.py            3. text and table recovery
├── clean.py                4. standardisation
├── features.py             analysis layer
├── fix_filenames.py        rename PDFs after a date repair
├── list_names.py           list raw names/units for the crosswalk
├── validate_metadata.py    metadata summary checks
├── probe_page.py           print a DAM page's table layout
├── fetch_chain.py          rebuild the TLS certificate bundle
├── make_figure.py          before/after text-recovery figure
├── logger_config.py
├── analysis/               fitness-for-use analyses (rq1–rq5) and paper figures
├── evaluation/             manual verification, hold-out check, text-method comparison
├── tests/
└── data/
    ├── report_metadata.csv     scraped report list
    ├── date_repairs.csv        checked date corrections
    ├── commodity_map.csv       name crosswalk
    ├── nikosh_glyph_map.json   reference glyph map
    ├── dam_chain.pem           CA bundle for dam.gov.bd
    ├── external/               CPI and festival dates
    ├── extracted/prices_raw.csv
    └── final/prices.csv
```

Not in git (rebuilt by the pipeline): `data/pdfs/`, `data/download_manifest.csv`, `data/final/prices_features.csv`,
`data/final/analysis/`, `logs/`.

---

## Limitations

* **Coverage is uneven.** There are no usable rows for 2022, 2020 and 2021 are sparse, 2023 covers July–October and 2024 June–December. Only 2025 is a complete year. About 3,000 reports from 2020–2023 were published as Excel files, which are not yet ingested; this is the main reason those years are thin.
* **Unmapped names.** About 38,000 raw rows, mostly rice, potato and pulse varieties, use spellings not yet in the crosswalk and are not in `prices.csv`.
* **Uncertain attribution.** 15 PDFs are linked from more than one date or division on the DAM site; each is attributed to its first listing.
* **Units.** Some egg series mix per-piece and per-four prices, and some Rangpur rows have no unit, so `kg` is taken from the report header. Check units before pooling.
* **What the prices are.** They are quotations compiled by DAM officers from selected markets, not a probability sample, and the reports contain no quantities.

---

## Licence and citation

Code: [MIT](LICENSE). Dataset (`data/`): CC BY 4.0, with attribution to the source as well as this project. The
source reports are published by the Department of Agricultural Marketing, Government of the People's Republic of
Bangladesh; this project claims no ownership of them and does not redistribute the PDFs.

If you use the data or code, please cite:

> R. Chowdhury, T. H. Chowdhury, T. N. Pusspa, and T. H. Liuza, "DAM-Data: A Reproducible ETL Pipeline for
> Bangladesh Agricultural Market Price Data," United International University, 2026 (manuscript in preparation).

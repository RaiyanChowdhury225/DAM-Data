# DAM-Data
# DAM Agricultural Market Data Pipeline

A reproducible Data Wrangling pipeline for collecting and transforming historical agricultural market reports published by the **Bangladesh Department of Agricultural Marketing (DAM)**.

The long-term goal of this project is to create a research-ready historical dataset containing agricultural commodity prices from markets across Bangladesh.

---

## Project Goal

DAM publishes daily agricultural market reports as PDF documents. These reports contain structured tabular information about commodities, markets, prices, and locations, but the information is distributed across many PDF files and is not provided as a convenient machine-readable dataset.

This project aims to:

1. Collect historical DAM report metadata.
2. Download the corresponding PDF reports.
3. Extract structured data from the Bangla PDF tables.
4. Clean and standardize the extracted data.
5. Produce a reproducible machine-readable dataset suitable for research and analysis.

---

## Current Pipeline

The project is being developed in multiple phases:

```text
DAM Website
    │
    ▼
Metadata Scraper
    │
    ▼
report_metadata.csv
    │
    ▼
PDF Downloader
    │
    ▼
PDF Corpus
    │
    ▼
PDF Extraction
    │
    ▼
Cleaning & Standardization
    │
    ▼
Final Research Dataset
```

### Current Status

* [x] Phase 1 — Metadata scraping
* [x] Phase 2 — PDF downloading
* [ ] Phase 3 — PDF table extraction
* [ ] Phase 4 — Data cleaning and normalization
* [ ] Phase 5 — Final dataset generation and validation

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

The current reports page contains:

```text
Serial | Date | Dhaka | Chittagong | Khulna | ...
```

### Historical Archive

The archive page has a slightly different structure:

```text
(empty) | (empty) | Date | Dhaka | Chittagong | Khulna | ...
```

Instead of creating separate parsers, the scraper uses layout configuration to support both structures.

This makes the scraper easier to maintain if DAM changes the table layout.

---

## Why Selenium Is Not Used

During investigation of the DAM website, it was found that the PDF "Download" buttons are regular HTML `<a>` elements containing the direct PDF URL.

Therefore, browser automation is unnecessary.

The scraper uses:

* `requests`
* `BeautifulSoup`

This is simpler, faster, and more reproducible than using Selenium.

---

# Metadata Dataset

The scraper produces:

```text
data/report_metadata.csv
```

The metadata dataset contains records linking report dates and divisions to their PDF files.

Duplicate PDF URLs are removed from the **download queue**, but the original metadata is preserved.

This distinction is important because duplicate metadata relationships may still be meaningful.

---

# Phase 2 — PDF Downloader

The downloader reads:

```text
data/report_metadata.csv
```

and downloads the associated PDFs.

Downloaded PDFs are stored locally under:

```text
data/pdfs/
```

The PDFs are intentionally **not stored in GitHub** because the corpus contains thousands of files and would make the repository unnecessarily large.

---

## Downloader Features

The downloader currently supports:

### Deterministic filenames

Each PDF receives a filename based on:

```text
date + division + URL hash
```

Example:

```text
2026-08-04_Dhaka_a81f3c92e1ab.pdf
```

The URL hash ensures that filenames remain unique and deterministic.

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
ময়মনসিংহ    → Mymensingh
```

### Duplicate URL removal

The metadata contains duplicate PDF URLs. These are removed before downloading so the same PDF is not requested multiple times.

### Existing-file detection

If a PDF already exists locally, the downloader skips it rather than downloading it again.

### Retry handling

Temporary request failures are retried automatically.

The downloader uses exponential backoff between attempts.

### PDF validation

Downloaded files are checked to ensure their content begins with the PDF file signature:

```text
%PDF
```

This prevents obvious HTML/error responses from being saved as valid PDFs.

### Download manifest

Download results are recorded in:

```text
data/download_manifest.csv
```

The manifest records information such as:

```text
date
division
pdf_url
filename
status
downloaded_at
error
```

---

# Project Structure

```text
DAM-Data/
│
├── scraper.py
├── downloader.py
├── validate_metadata.py
├── config.py
├── logger_config.py
│
├── data/
│   ├── report_metadata.csv
│   ├── download_manifest.csv
│   └── pdfs/
│
├── logs/
│   └── scraper.log
│
└── README.md
```

The following are excluded from Git:

```text
data/pdfs/
data/download_manifest.csv
logs/
```

See `.gitignore`.

---

# Requirements

Python 3.x

Install the required packages:

```bash
pip install requests beautifulsoup4 pandas
```

---

# Reproducing the Metadata Scraper

Clone the repository:

```bash
git clone <REPOSITORY_URL>
cd DAM-Data
```

Run the metadata scraper:

```bash
python scraper.py
```

The scraper will:

1. Request the configured DAM report pages.
2. Parse the report tables.
3. Extract dates, divisions, serial numbers, and PDF URLs.
4. Combine the results from the supported pages.
5. Save the metadata to:

```text
data/report_metadata.csv
```

---

# Reproducing the PDF Downloader

After generating the metadata:

```bash
python downloader.py
```

The downloader will:

1. Load `report_metadata.csv`.
2. Remove duplicate PDF URLs from the download queue.
3. Generate deterministic filenames.
4. Check whether each PDF already exists.
5. Download missing PDFs.
6. Retry temporary failures.
7. Validate downloaded files.
8. Record download results in the manifest.

The downloader supports a test mode so that a small number of PDFs can be tested before running the full download.

---

# Configuration

Important settings are stored in:

```text
config.py
```

For example:

```python
TEST_MODE = True
TEST_LIMIT = 20
DRY_RUN = True
```

During development, test mode should be used first.

For a full download, these settings can eventually be changed to:

```python
TEST_MODE = False
DRY_RUN = False
```

Do not enable full downloading until the test run has been verified.

---

# Data Quality Checks

The project includes validation scripts to check the metadata before downstream processing.

Example:

```bash
python validate_metadata.py
```

The validation process checks things such as:

* total number of records
* missing values
* division distribution
* duplicate PDF URLs
* source-page distribution

These checks help ensure that errors in the scraping stage are identified before downloading and PDF extraction.

---

# Research Reproducibility

A major design goal of this project is reproducibility.

The repository contains the code required to regenerate the metadata and download the PDF corpus rather than storing thousands of PDFs directly in GitHub.

The pipeline is designed so that each stage produces an explicit artifact:

```text
Scraper
    ↓
report_metadata.csv

Downloader
    ↓
PDF corpus + download_manifest.csv

Extractor
    ↓
raw extracted dataset

Cleaner
    ↓
final research dataset
```

Each stage can therefore be validated independently.

---

# Future Work

The next major stage is extracting the tables contained inside the Bangla PDF reports.

The extracted data is expected to contain information such as:

```text
date
division
district
market
commodity
category
unit
price
currency
```

Additional cleaning and standardization will be performed before creating the final research dataset.

The final dataset is expected to contain **80,000+ structured observations**, depending on the number of valid rows extracted from the historical PDF reports.

---

# Disclaimer

This project is an academic Data Wrangling and research project using publicly available agricultural market reports published by the Bangladesh Department of Agricultural Marketing.

The project does not claim ownership of the original government reports.

The downloaded PDFs are kept locally and are not included in this repository.

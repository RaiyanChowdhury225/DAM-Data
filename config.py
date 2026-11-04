from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
CA_BUNDLE = str(DATA_DIR / "dam_chain.pem")      # rebuild with fetch_chain.py if the site's certificate changes
PDF_DIR = DATA_DIR / "pdfs"

DATA_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)

METADATA_CSV = DATA_DIR / "report_metadata.csv"
DATE_REPAIRS_CSV = DATA_DIR / "date_repairs.csv"  # malformed report dates, each checked against its PDF

DOWNLOAD_MANIFEST = DATA_DIR / "download_manifest.csv"

TEST_MODE = False       # True: download only the first TEST_LIMIT PDFs
TEST_LIMIT = 20
MANIFEST_CHECKPOINT = 50


TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
# column positions in the report tables (all pages currently share one layout;
# give a page its own dict if the site changes one of them)
LAYOUT = {
    "serial_index": None,
    "date_index": 0,
    "division_start": 1
}

REPORT_PAGES = [
    {
        "name": "current",
        "url": "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21",
        "layout": LAYOUT
    },

    {
        "name": "archive",
        "url": "https://dam.gov.bd/pages/static-pages/6922e15c933eb65569e2bb7a",
        "layout": LAYOUT
    },

    {
        "name": "archive_2025",
        "url": "https://dam.gov.bd/pages/static-pages/6a815e6d0181787383827aca",
        "layout": LAYOUT
    },

    {
        "name": "archive_2024",
        "url": "https://dam.gov.bd/pages/static-pages/6a8168fa9b63d6f0462d1feb",
        "layout": LAYOUT
    },

    {
        "name": "archive_2023",
        "url": "https://dam.gov.bd/pages/static-pages/6a8169e681a3682d044ef628",
        "layout": LAYOUT
    }
]
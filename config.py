from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

CA_BUNDLE = str(Path(__file__).resolve().parent / "data" / "dam_chain.pem")

DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"

DATA_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)

METADATA_CSV = DATA_DIR / "report_metadata.csv"

DOWNLOAD_MANIFEST = DATA_DIR / "download_manifest.csv"

TEST_MODE=False
TEST_LIMIT=20
MANIFEST_CHECKPOINT = 50


TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
CURRENT_LAYOUT = {
    "serial_index": None,
    "date_index": 0,
    "division_start": 1
}


ARCHIVE_LAYOUT = {
    "serial_index": None,
    "date_index": 0,
    "division_start": 1
}

REPORT_PAGES = [
    {
        "name": "current",
        "url": "https://dam.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21",
        "layout": CURRENT_LAYOUT
    },

    {
        "name": "archive",
        "url": "https://dam.gov.bd/pages/static-pages/6922e15c933eb65569e2bb7a",
        "layout": ARCHIVE_LAYOUT
    },

    {
        "name": "archive_2025",
        "url": "https://dam.gov.bd/pages/static-pages/6a815e6d0181787383827aca",
        "layout": ARCHIVE_LAYOUT
    },

    {
        "name": "archive_2024",
        "url": "https://dam.gov.bd/pages/static-pages/6a8168fa9b63d6f0462d1feb",
        "layout": ARCHIVE_LAYOUT
    },

    {
        "name": "archive_2023",
        "url": "https://dam.gov.bd/pages/static-pages/6a8169e681a3682d044ef628",
        "layout": ARCHIVE_LAYOUT
            }
]
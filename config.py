from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"

DATA_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)

METADATA_CSV = DATA_DIR / "report_metadata.csv"


TIMEOUT = 30
CURRENT_LAYOUT = {
    "serial_index": 0,
    "date_index": 1,
    "division_start": 2
}


ARCHIVE_LAYOUT = {
    "serial_index": None,
    "date_index": 2,
    "division_start": 3
}

REPORT_PAGES = [
    {
        "name": "current",
        "url": "http://dam.portal.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21",
        "layout": CURRENT_LAYOUT
    },

    {
        "name": "archive",
        "url": "http://dam.portal.gov.bd/pages/static-pages/6922e15c933eb65569e2bb7a",
        "layout": ARCHIVE_LAYOUT
    }
]
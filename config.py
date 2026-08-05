from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"

DATA_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)

METADATA_CSV = DATA_DIR / "report_metadata.csv"

REPORT_PAGE = ("http://dam.portal.gov.bd/pages/static-pages/6922e0d1933eb65569e28b21")
TIMEOUT = 30
import requests
import logging
from bs4 import BeautifulSoup
from config import *
import logger_config   
import pandas as pd

logger = logging.getLogger(__name__)



def fetch_page() -> str: #Fetches The Page
    logger.info("Fetching DAM reports page...")

    try:
        response = requests.get(REPORT_PAGE, timeout=TIMEOUT)
        response.raise_for_status()

        logger.info("Successfully fetched reports page.")
        return response.text

    except requests.RequestException:
        logger.exception("Failed to fetch DAM reports page.")
        raise
  

###Get the Division names
def get_divisions(table):
    """
    Extract division names from the table header.

    Args:
        table (bs4.element.Tag): The report table.

    Returns:
        list[str]: List of division names.
    """
    divisions = []

    # Get all rows in the table
    rows = table.find_all("tr")

    # The first row is the header
    header_cells = rows[0].find_all("td")

    # Skip Serial and Date columns
    for cell in header_cells[2:]:
        division = cell.get_text(strip=True)
        divisions.append(division)

    return divisions

##Get The row datas
def parse_row(row, divisions):
    cells = row.find_all("td")

    serial = cells[0].get_text(strip=True)
    date = cells[1].get_text(strip=True)

    records = []

    for division, cell in zip(divisions, cells[2:]):
        link=cell.find('a')
        if link:
            pdf_url=link.get('href')
            record = {
                    "serial": serial,
                    "date": date,
                    "division": division,
                    "pdf_url": pdf_url,
                }
            records.append(record)

    return records

def parse_reports(table):
    logger.info("Parsing report metadata...")

    divisions = get_divisions(table)
    rows = table.find_all("tr")[1:]  # Skip header

    all_records = []
    missing_links = 0

    for row in rows:
        cells = row.find_all("td")

        for cell in cells[2:]:
            if cell.find("a") is None:
                missing_links += 1

        all_records.extend(parse_row(row, divisions))

    logger.info(f"Processed {len(rows)} report rows.")
    logger.info(f"Extracted {len(all_records)} metadata records.")
    logger.info(f"Missing PDF links: {missing_links}")

    return all_records



def save_metadata(records):
    logger.info("Saving metadata...")

    df = pd.DataFrame(records)

    df.to_csv(METADATA_CSV, index=False, encoding="utf-8-sig")

    logger.info(f"Saved {len(df)} records to {METADATA_CSV}")

def main():
    html = fetch_page()

    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")
    report_table = tables[0]

    records = parse_reports(report_table)

    save_metadata(records)

    logger.info("Metadata scraping completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Metadata pipeline failed.")
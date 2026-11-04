import requests
import logging
from bs4 import BeautifulSoup
from config import *
import logger_config
import pandas as pd



logger = logging.getLogger(__name__)


def fetch_page(url):

    logger.info(f"Fetching page: {url}")

    try:
        response = requests.get(
            url,
            timeout=TIMEOUT,
            verify=CA_BUNDLE
        )

        response.raise_for_status()

        logger.info("Page fetched successfully.")

        return response.text

    except requests.RequestException:
        logger.exception(
            f"Failed fetching {url}"
        )
        raise



def get_divisions(table, layout):
    """
    Extract division names from table header.
    """

    divisions = []

    rows = table.find_all("tr")

    header_cells = rows[0].find_all("td")

    start = layout["division_start"]

    for cell in header_cells[start:]:

        division = cell.get_text(strip=True)

        if division:
            divisions.append(division)

    return divisions



def parse_row(row, divisions, layout, source_name):

    cells = row.find_all("td")

    if not cells:
        return []


    serial = None

    if layout["serial_index"] is not None:
        serial = cells[
            layout["serial_index"]
        ].get_text(strip=True)


    date = cells[
        layout["date_index"]
    ].get_text(strip=True)


    records = []

    division_start = layout["division_start"]


    for division, cell in zip(
        divisions,
        cells[division_start:]
    ):

        link = cell.find("a")

        if link:

            pdf_url = link.get("href")

            records.append({

                "serial": serial,
                "date": date,
                "division": division,
                "pdf_url": pdf_url,
                "source_page": source_name

            })


    return records



def parse_reports(table, layout, source_name):

    logger.info(
        f"Parsing metadata from {source_name}..."
    )


    divisions = get_divisions(
        table,
        layout
    )


    rows = table.find_all("tr")[1:]


    all_records = []

    missing_links = 0


    for row in rows:

        cells = row.find_all("td")


        for cell in cells[layout["division_start"]:]:
            
            if cell.find("a") is None:
                missing_links += 1


        all_records.extend(
            parse_row(
                row,
                divisions,
                layout,
                source_name
            )
        )


    logger.info(
        f"{source_name}: Processed {len(rows)} rows."
    )

    logger.info(
        f"{source_name}: Extracted {len(all_records)} records."
    )

    logger.info(
        f"{source_name}: Missing PDF links {missing_links}"
    )


    return all_records



BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def add_date_iso(df):
    """
    Add date_iso (YYYY-MM-DD) and date_status (ok / corrected / invalid).

    Dates are read as Bangla dd-mm-yyyy. Malformed ones (typos on the DAM site,
    e.g. "২৪-০৩-৩০৩২") are taken from data/date_repairs.csv, where each repair
    was checked against the report's own header; a repair wins even over a
    date that parses, because some typos are valid dates.
    """
    fixes = pd.read_csv(DATE_REPAIRS_CSV, dtype=str, encoding="utf-8-sig")
    # keyed by URL, not by date text: one page lists "১৩-০৭-২০২৩" twice, once correctly
    # and once for the 13 August report
    fixes = dict(zip(zip(fixes["pdf_url"], fixes["raw_date"]), fixes["date_iso"]))

    raw = df["date"].astype(str).str.strip()
    parsed = pd.to_datetime(
        raw.str.translate(BANGLA_DIGITS),
        format="%d-%m-%Y",
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    repaired = pd.Series(
        [fixes.get(k) for k in zip(df["pdf_url"], raw)],
        index=df.index,
        dtype="object"
    )

    df["date_iso"] = repaired.fillna(parsed)
    df["date_status"] = "ok"
    df.loc[repaired.notna(), "date_status"] = "corrected"
    df.loc[df["date_iso"].isna(), "date_status"] = "invalid"

    invalid = df.loc[df["date_status"] == "invalid", ["source_page", "date"]]
    if len(invalid):
        logger.warning(
            f"{len(invalid)} records have a date that is neither valid nor in "
            f"{DATE_REPAIRS_CSV.name}; they will not be downloaded. "
            f"Distinct values: {invalid.drop_duplicates().values.tolist()[:20]}"
        )
    return df


def save_metadata(records):

    logger.info("Saving metadata...")

    df = add_date_iso(pd.DataFrame(records))

    df.to_csv(
        METADATA_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    logger.info(
        f"Saved {len(df)} records to {METADATA_CSV}"
    )



def main():

    all_records = []


    for page in REPORT_PAGES:

        html = fetch_page(
            page["url"]
        )


        soup = BeautifulSoup(
            html,
            "html.parser"
        )


        tables = soup.find_all("table")


        if not tables:
            logger.warning(
                f"No table found on {page['name']} page"
            )
            continue


        report_table = tables[0]


        records = parse_reports(
            report_table,
            page["layout"],
            page["name"]
        )


        all_records.extend(records)



    save_metadata(all_records)


    logger.info(
        "Metadata scraping completed successfully."
    )



if __name__ == "__main__":

    try:
        main()

    except Exception:
        logger.exception(
            "Metadata pipeline failed."
        )
        raise SystemExit(1)       # non-zero exit, so main.py stops here
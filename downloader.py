import requests
import pandas as pd
import hashlib
import logging
from datetime import datetime
import time

from config import METADATA_CSV,PDF_DIR,TIMEOUT,MAX_RETRIES,RETRY_DELAY,DOWNLOAD_MANIFEST,TEST_LIMIT,TEST_MODE,MANIFEST_CHECKPOINT,CA_BUNDLE

import logger_config
logger=logging.getLogger(__name__)












def save_manifest(records):
    """
    Save download status records, merged with any existing manifest.

    Each run only holds its own records in memory, so the manifest on disk is
    the accumulated history. Keeping it means an interrupted run resumes with a
    full picture rather than only what the current process happens to remember.
    """

    logger.info("Saving download manifest...")

    df = pd.DataFrame(records)

    existing = load_manifest()

    if not existing.empty:
        df = pd.concat([existing, df], ignore_index=True)

        # one row per URL: the newest attempt wins
        df = df.drop_duplicates(
            subset="pdf_url",
            keep="last"
        ).reset_index(drop=True)

    df.to_csv(
        DOWNLOAD_MANIFEST,
        index=False,
        encoding="utf-8-sig"
    )

    logger.info(
        f"Saved {len(df)} records to {DOWNLOAD_MANIFEST}"
    )





DIVISION_MAP = {
    "ঢাকা": "Dhaka",
    "চট্টগ্রাম": "Chittagong",
    "খুলনা": "Khulna",
    "রাজশাহী": "Rajshahi",
    "বরিশাল": "Barisal",
    "রংপুর": "Rangpur",
    "সিলেট": "Sylhet",
    "ময়মনসিংহ": "Mymensingh"
}

def normalize_data(bangla_date):
    # Convert bangla date digits to english

    bangla_to_english = str.maketrans(
        '০১২৩৪৫৬৭৮৯',
        '0123456789'
    )

    english_date = str(bangla_date).translate(
        bangla_to_english
    )
    
    english_date = english_date.strip()
    english_date = english_date.replace('*', '')

    parts = english_date.split('-')

    # If date does not have exactly 3 parts, skip it
    if len(parts) != 3:
        logger.warning(
            f"Invalid date format, skipping: {bangla_date}"
        )
        return None

    day, month, year = parts

    return f'{year}-{month}-{day}'







def load_metadata():
    #Load Report metadata CSV

    logger.info(f'Loading metadata from {METADATA_CSV}')

    try:
        df=pd.read_csv(METADATA_CSV)

        logger.info(
            f'Loaded {len(df)} metadata records'
        )

        return df

    except FileNotFoundError:
        logger.exception(
            f'Metadata File not found:{METADATA_CSV}'
        )
        raise


def generate_filename(date, division, pdf_url):

    # Stable Filename using hash of the pdf url

    normalized_date = normalize_data(date)

    # Invalid date → skip this PDF
    if normalized_date is None:
        return None

    english_division = DIVISION_MAP.get(
        division,
        division
    )

    url_hash = hashlib.sha256(
        pdf_url.encode('utf-8')
    ).hexdigest()[:12]

    filename = (
        f'{normalized_date}_'
        f'{english_division}_'
        f'{url_hash}.pdf'
    )

    return filename


def download_pdf(url, output_path):
    """
    Download a single PDF with retry handling.
    """

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            logger.info(
                f"Downloading {output_path.name} "
                f"(Attempt {attempt}/{MAX_RETRIES})"
            )

            response = requests.get(
                url,
                timeout=TIMEOUT,
                verify=CA_BUNDLE
            )

            response.raise_for_status()


            # Basic PDF validation
            if not response.content.startswith(b"%PDF"):

                error_message = "Downloaded file is not a valid PDF"

                logger.warning(
                    f"{error_message}: {output_path.name}"
                )

                return {
                    "status": "failed",
                    "error": error_message
                }


            with open(output_path, "wb") as file:
                file.write(response.content)


            logger.info(
                f"Downloaded successfully: {output_path.name}"
            )

            return {
                "status": "success",
                "error": None
            }


        except requests.RequestException as e:

            last_error = str(e)

            logger.warning(
                f"Attempt {attempt} failed for "
                f"{output_path.name}: {e}"
            )


            if attempt < MAX_RETRIES:

                delay = RETRY_DELAY * (
                    2 ** (attempt - 1)
                )

                logger.info(
                    f"Retrying in {delay} seconds..."
                )

                time.sleep(delay)


    logger.error(
        f"Failed after {MAX_RETRIES} attempts: "
        f"{output_path.name}"
    )

    return {
        "status": "failed",
        "error": last_error
    }




def log_summary(manifest_records):
    """
    Log a summary of the download results.
    """

    total = len(manifest_records)

    success = sum(
        1 for record in manifest_records
        if record["status"] == "success"
    )

    skipped = sum(
        1 for record in manifest_records
        if record["status"] == "skipped"
    )

    failed = sum(
        1 for record in manifest_records
        if record["status"] == "failed"
    )

    logger.info("Download Summary")
    logger.info("----------------")
    logger.info(f"Total:   {total}")
    logger.info(f"Success: {success}")
    logger.info(f"Skipped: {skipped}")
    logger.info(f"Failed:  {failed}")




def load_manifest():
    """
    Load the existing download manifest if it exists.
    """

    if not DOWNLOAD_MANIFEST.exists():

        logger.info(
            "No existing download manifest found."
        )

        return pd.DataFrame()

    logger.info(
        f"Loading existing manifest from "
        f"{DOWNLOAD_MANIFEST}"
    )

    manifest = pd.read_csv(
        DOWNLOAD_MANIFEST
    )

    logger.info(
        f"Loaded {len(manifest)} manifest records."
    )

    return manifest





def main():

    # Load metadata
    df = load_metadata()


    manifest = load_manifest()
    successful_urls = set(
    manifest.loc[
        manifest["status"] == "success",
        "pdf_url"
    ]
        ) if not manifest.empty else set()



    original_count = len(df)

    df = df.drop_duplicates(
        subset="pdf_url"
    ).reset_index(drop=True)

    unique_count = len(df)

    logger.info(
        f"Metadata records: {original_count}"
    )

    logger.info(
        f"Unique PDF URLs: {unique_count}"
    )

    logger.info(
        f"Duplicate PDF URLs removed from download queue: "
        f"{original_count - unique_count}"
    )

    # TEST MODE
    # Change/remove this later when downloading everything
    if TEST_MODE:
        test_records = df.head(TEST_LIMIT)

    else:
        test_records = df

    logger.info(
        f"Starting download of {len(test_records)} PDFs."
    )

    # Store download results for manifest
    manifest_records = []


    total = len(test_records)

    for index, (_, row) in enumerate(
        test_records.iterrows(),
        start=1
    ):

        logger.info(
            f"[{index}/{total}] Processing PDF"
        )

        pdf_url = row["pdf_url"]
        
        date = row["date"]
        division = row["division"]



        if pdf_url in successful_urls:

            logger.info(
                f"Already recorded as successful, skipping: {pdf_url}"
            )

            continue


        # Generate deterministic filename
        filename = generate_filename(
            date,
            division,
            pdf_url
        )
        if filename is None: 
            logger.warning( f"Skipping PDF due to invalid date: {date}" ) 
            continue

        output_path = PDF_DIR / filename


        # Skip files already downloaded
        if output_path.exists():

            logger.info(
                f"Already exists, skipping: {filename}"
            )

            manifest_records.append({
                "date": date,
                "division": division,
                "pdf_url": pdf_url,
                "filename": filename,
                "status": "skipped",
                "downloaded_at": None,
                "error": None
            })

        else:

            # Download PDF
            result = download_pdf(
                pdf_url,
                output_path
            )

            # Store download result
            manifest_records.append({
                "date": date,
                "division": division,
                "pdf_url": pdf_url,
                "filename": filename,
                "status": result["status"],
                "downloaded_at": (
                    datetime.now().isoformat()
                    if result["status"] == "success"
                    else None
                ),
                "error": result["error"]
            })


        # Save manifest periodically
        if index % MANIFEST_CHECKPOINT == 0:

            logger.info(
                f"Checkpoint reached at {index} PDFs."
            )

            save_manifest(manifest_records)


    # Final save
    save_manifest(manifest_records)

    log_summary(manifest_records)

    logger.info(
        "PDF download pipeline completed."
)
if __name__=='__main__':
    try:
        main()

    except Exception:

        logger.exception(
            'PDF Downloader pipeline failed'
        )
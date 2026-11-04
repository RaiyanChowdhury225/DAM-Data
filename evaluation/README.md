DAM-Data extractor v2 - fixes found by the manual verification sample (29 Oct 2026)

WHAT CHANGED (extractor.py; full diff in extractor_v2.diff)
 1. Current-price column: must hold "min - max" pairs; the column headed
    "যৌক্তিক মূল্য" (fair price) is never used. Fixes fair-price values / blank prices
    in Khulna, Sylhet, Dhaka reports.
 2. Clipped minimum: hidden-overflow removal now requires the two text lines to overlap
    horizontally, so a min and max printed side by side are no longer treated as overflow;
    plus a fallback to the table cell text when one number is lost. Fixes min = max rows.
 3. Unit carry-down: a row whose name could not be read (legacy Bijoy font) or whose unit
    is unreadable no longer lets the previous unit carry on; ", ," counts as a ditto mark.
    Fixes "5 litre" carried onto vegetables, fish and meat.
 4. Fonts renamed to "CIDFont+F1" whose embedded program is NikoshBAN are now decoded
    (recovers whole pages that were previously lost, e.g. Dhaka 2023 pages 3-4).
 5. Glyphs drawn twice for fake bold ("1133", "প্রপ্রতি") are de-duplicated.
dam_common.py: adds the date repair 2015-09-15 -> 2025-09-15 (all eight files say 15.09.2025).

TEST RESULT (145 sample PDFs)
 - 554 manually checked rows: all 497 correct rows unchanged; 56 of 57 wrong rows now match the PDF
   (the remaining one is a garbled rice name in Chittagong, unchanged).
 - 170 new rows from 34 PDFs not used to design the fix: 168 in the dataset, 0 errors.
 - About 10% of rows in the sample PDFs change value (almost all Khulna, Sylhet, Dhaka).

HOW TO RUN ON YOUR PC (PowerShell, from D:\DAM-data\DAM-Data)
 1. Back up:   copy extractor.py extractor_v1.py
               copy data\extracted\prices_raw.csv data\extracted\prices_raw_v1.csv
               copy data\final\prices.csv data\final\prices_v1.csv
 2. Install:   copy v2_fixes\extractor.py extractor.py
               copy v2_fixes\dam_common.py analysis\dam_common.py
 3. Crosswalk: open v2_fixes\commodity_map_additions_v2.csv, check each suggested mapping
               (and fix the commodity_type column if needed), then append the rows to
               data\commodity_map.csv. These are spellings that only appear now that more
               text is decoded. One row is still Bijoy-encoded text: leave it out.
 4. Re-run:    python main.py --from extract
               (clean.py will list any other unmapped names: add them to the crosswalk and
               run  python main.py --only clean  again)
 5. Analysis:  cd analysis ; then run rq3, rq1, rq5, rq2, rq4 and paper_figures.py again.
Then send me the new prices.csv (or let me stage it) and I will update every number in the paper.

"""Checks for the defects found while preparing the release.  Run:  python -m pytest"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import clean       # noqa: E402
import downloader  # noqa: E402
import scraper     # noqa: E402


def test_crosswalk_is_complete():
    mapping = clean.load_map()
    assert len(mapping) > 300
    assert all(t and n for t, n in mapping.values())


def test_crosswalk_rejects_rows_without_a_standard_name(tmp_path, monkeypatch):
    bad = tmp_path / "map.csv"
    bad.write_text("commodity_type_raw,commodity_name_raw,rows,commodity_type,commodity_name,needs_review\n"
                   ",আটা,2,Flour,,\n\n\n", encoding="utf-8-sig")
    monkeypatch.setattr(clean, "MAP_CSV", bad)
    with pytest.raises(SystemExit, match="1 invalid rows"):
        clean.load_map()


def test_date_repair_is_keyed_by_url(tmp_path, monkeypatch):
    repairs = tmp_path / "repairs.csv"
    repairs.write_text("source_page,raw_date,division,date_iso,pdf_url\n"
                       "p,১৩-০৭-২০২৩,x,2023-08-13,http://b\n", encoding="utf-8-sig")
    monkeypatch.setattr(scraper, "DATE_REPAIRS_CSV", repairs)
    df = pd.DataFrame({"source_page": ["p", "p", "p"],
                       "date": ["১৩-০৭-২০২৩", "১৩-০৭-২০২৩", "৩২-০১-২০২৫"],
                       "pdf_url": ["http://a", "http://b", "http://c"]})
    out = scraper.add_date_iso(df)
    # same date text, different reports: only the listed URL is repaired
    assert out["date_iso"].tolist()[:2] == ["2023-07-13", "2023-08-13"]
    assert out["date_status"].tolist() == ["ok", "corrected", "invalid"]


def test_metadata_dates_are_reproducible():
    meta = pd.read_csv(scraper.METADATA_CSV, dtype=str)
    rebuilt = scraper.add_date_iso(meta.drop(columns=["date_iso", "date_status"]))
    assert rebuilt["date_iso"].equals(meta["date_iso"])
    assert rebuilt["date_status"].equals(meta["date_status"])


def test_filenames_are_iso_and_hash_keyed():
    name = downloader.generate_filename("2025-09-15", "ঢাকা", "http://a")
    assert name == f"2025-09-15_Dhaka_{downloader.url_hash('http://a')}.pdf"
    assert downloader.generate_filename("15-09-2025", "ঢাকা", "http://a") is None
    assert clean.iso_date(name.split("_")[0]) == "2025-09-15"

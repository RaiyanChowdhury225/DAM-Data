"""
make_figure.py — produce the before/after text-recovery figure for the paper.

Extracts the same cells twice from one report: once with plain pdfplumber
(the corrupted text) and once with extractor.py's font fix applied, then prints
them side by side. Screenshot the terminal, or use --html if your terminal
cannot render Bangla.

    python make_figure.py
    python make_figure.py --file data/pdfs/<some>.pdf --rows 12 --html
"""
import argparse
import re
from pathlib import Path

import pdfplumber                      # imported BEFORE extractor, so this pass is unpatched

BASE = Path(__file__).resolve().parent
BANGLA = re.compile(r"[\u0980-\u09FF]")


def cells(pdf_path):
    """Every table cell of page 1, in a fixed order, as a flat list."""
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        v = [e for e in page.edges if e["orientation"] == "v"]
        settings = {"explicit_horizontal_lines": [min(e["top"] for e in v),
                                                  max(e["bottom"] for e in v)]} if v else {}
        for table in page.extract_tables(settings):
            for row in table:
                out.extend(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="report to use (default: first PDF in data/pdfs)")
    ap.add_argument("--rows", type=int, default=10, help="how many examples to show")
    ap.add_argument("--html", action="store_true", help="also write figure_text_recovery.html")
    args = ap.parse_args()

    pdf_path = Path(args.file) if args.file else sorted((BASE / "data" / "pdfs").glob("*.pdf"))[0]

    before = cells(pdf_path)           # pass 1: plain pdfplumber
    import extractor                   # patches pdfminer on import
    after_raw = cells(pdf_path)        # pass 2: characters recovered from the font
    after = [extractor.fix_bangla(c) for c in after_raw]   # plus logical reordering

    pairs = []
    for b, a in zip(before, after):
        if not b or not a or not BANGLA.search(b) or b.strip() == a.strip():
            continue
        b, a = " ".join(b.split()), " ".join(a.split())
        # prefer short cells without digits: those are commodity names and units,
        # which make a clearer figure than the long column headings
        if 3 < len(b) < 30 and not re.search(r"\d", b) and (b, a) not in pairs:
            pairs.append((b, a))
        if len(pairs) >= args.rows:
            break

    width = max(len(b) for b, _ in pairs) + 2
    print(f"\nSource: {pdf_path.name}\n")
    print(f"{'EXTRACTED AS-IS':<{width}}RECOVERED FROM FONT")
    print("-" * (width + 30))
    for b, a in pairs:
        print(f"{b:<{width}}{a}")
    print()

    if args.html:
        # a browser renders Bangla reliably even when a terminal does not
        rows = "\n".join(
            f"<tr><td class=bad>{b}</td><td class=good>{a}</td></tr>" for b, a in pairs)
        html = f"""<!doctype html><meta charset="utf-8">
<style>
 body {{ font-family: "Nikosh", "Noto Sans Bengali", sans-serif; padding: 24px; }}
 table {{ border-collapse: collapse; font-size: 18px; }}
 th, td {{ border: 1px solid #999; padding: 6px 14px; text-align: left; }}
 th {{ background: #eee; }}
 .bad {{ color: #b00; }}
 .good {{ color: #060; }}
</style>
<table>
<tr><th>Extracted as-is</th><th>Recovered from font</th></tr>
{rows}
</table>"""
        out = BASE / "figure_text_recovery.html"
        out.write_text(html, encoding="utf-8")
        print(f"Wrote {out} - open it in a browser and screenshot the table.")


if __name__ == "__main__":
    main()
"""
compare_extraction.py - how much does font-based text recovery matter?

Measurement 1 - row-level ablation. The SAME table cells are read with three
text decoders, so only the text handling differs:
  conventional : the PDF's own ToUnicode map (what pdfplumber/pdfminer give by default)
  font_map     : glyph map rebuilt from the embedded font, but no reordering
  full         : font map + logical reordering  (= extractor.py)

Measurement 2 - whole-page text from other tools. Does each reference name
appear in the page text (exact, and best fuzzy match)?
  pdfplumber (default), PyMuPDF (default), Tesseract OCR Bengali (fast, best models; page segmentation mode 11, 400 dpi)

Reference names: names produced by the full method whose exact spelling is in
the hand-checked crosswalk data/commodity_map.csv.

Run from the project folder:
    python evaluation/compare_extraction.py data/eval/sample_files.txt
(the text file lists one PDF filename per line, all inside data/pdfs/)
Outputs in data/eval/: extraction_comparison_rows.csv, extraction_comparison_summary.csv
Needs: pdfplumber fonttools pymupdf rapidfuzz, and for OCR tesseract + ben.traineddata
       (set TESSDATA_FAST / TESSDATA_BEST to folders containing ben.traineddata).
"""
import csv, inspect, json, os, re, subprocess, sys, unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent          # project root
sys.path.insert(0, str(BASE))                           # so the workers can import extractor
PDF_DIR = BASE / "data" / "pdfs"
OUT = BASE / "data" / "eval"


def norm(s):
    """Normalisation applied identically to every method."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s.replace("(cid:10)", " ").replace("\u200c", "").replace("\u200d", ""))
    s = s.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Worker (separate process, because importing extractor.py patches pdfminer)
# ---------------------------------------------------------------------------
def worker_cells(files):
    """Run the real extractor and record, for every row, its name-cell boxes."""
    import extractor as X
    src = inspect.getsource(X.extract_pdf)
    old = '"commodity_name_raw": name,'
    assert old in src
    src = src.replace(old, old + ' "cells": [(page.page_number, list(row.cells[i])) '
                      'for i in range(2 if has_type_col else 1, unit_col) '
                      'if i < len(row.cells) and row.cells[i]],')
    ns = {}
    exec(src, X.__dict__, ns)
    out = []
    for f in files:
        for r in ns["extract_pdf"](PDF_DIR / f):
            out.append({"file": f, "name": r["commodity_name_raw"], "cells": r["cells"]})
    return out


def worker_read(mode, rows):
    """Re-read the recorded cells with a given decoder."""
    import pdfplumber
    import extractor as X
    if mode == "conventional":
        X.PDFCIDFont.__init__ = X._original_cidfont_init
        X.PDFTrueTypeFont.__init__ = X._original_tt_init
    if mode in ("conventional", "font_map"):
        X.fix_bangla = lambda t: norm(t.replace(X.REPH, "র্")) if t else t   # no reordering
    res, cache = [], {}
    for r in rows:
        if r["file"] not in cache:
            cache.clear()
            cache[r["file"]] = pdfplumber.open(PDF_DIR / r["file"])
        pdf = cache[r["file"]]
        parts = [X.text_in_cell(pdf.pages[p - 1].chars, tuple(b)) for p, b in r["cells"]]
        res.append(norm(" ".join(t for t in parts if t)))
    return res


def worker_pages(tool, files):
    """Whole-page text per file from a default tool (no font patches)."""
    out = {}
    if tool == "pdfplumber":
        import pdfplumber
        for f in files:
            with pdfplumber.open(PDF_DIR / f) as pdf:
                out[f] = norm(" ".join(p.extract_text() or "" for p in pdf.pages))
    elif tool == "pymupdf":
        import pymupdf
        for f in files:
            with pymupdf.open(PDF_DIR / f) as doc:
                out[f] = norm(" ".join(p.get_text() for p in doc))
    elif tool.startswith("tesseract"):
        import pymupdf
        tess = os.environ["TESSDATA_FAST" if tool == "tesseract_fast" else "TESSDATA_BEST"]
        for f in files:
            texts = []
            with pymupdf.open(PDF_DIR / f) as doc:
                for i, p in enumerate(doc):
                    png = OUT / "_ocr_page.png"
                    p.get_pixmap(dpi=400).save(png)
                    t = subprocess.run(["tesseract", str(png), "-", "-l", "ben", "--tessdata-dir", tess,
                                        "--psm", "11"], capture_output=True, text=True).stdout
                    texts.append(t)
            out[f] = norm(" ".join(texts))
    return out


def run_worker(*args):
    p = subprocess.run([sys.executable, __file__, "--worker", *args], capture_output=True, text=True,
                       cwd=BASE)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return json.loads(p.stdout.strip().splitlines()[-1])


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--worker":
    kind, payload = sys.argv[2], json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    if kind == "cells":
        r = worker_cells(payload)
    elif kind == "read":
        r = worker_read(payload["mode"], payload["rows"])
    else:
        r = worker_pages(payload["tool"], payload["files"])
    print(json.dumps(r, ensure_ascii=False))
    sys.exit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def tmp(obj, name):
    p = OUT / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(p)


def main():
    from rapidfuzz.distance import Levenshtein
    from rapidfuzz import fuzz
    OUT.mkdir(parents=True, exist_ok=True)
    files = [l.strip() for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]

    with open(BASE / "data" / "commodity_map.csv", encoding="utf-8-sig") as fh:
        checked = {norm(r["commodity_name_raw"]) for r in csv.DictReader(fh)}

    print(f"{len(files)} PDFs. Recording table cells with the full extractor ...")
    rows = run_worker("cells", tmp(files, "_files.json"))
    print(f"  {len(rows)} commodity rows")

    reads = {}
    for mode in ["full", "font_map", "conventional"]:
        print("Reading cells with decoder:", mode)
        reads[mode] = run_worker("read", tmp({"mode": mode, "rows": rows}, "_rows.json"))

    pages = {}
    tools = ["pdfplumber", "pymupdf"]
    if os.environ.get("TESSDATA_FAST"):
        tools.append("tesseract_fast")
    if os.environ.get("TESSDATA_BEST"):
        tools.append("tesseract_best")
    for t in tools:
        print("Whole-page text:", t)
        pages[t] = run_worker("pages", tmp({"tool": t, "files": files}, "_pages.json"))

    out_rows = []
    for i, r in enumerate(rows):
        ref = norm(reads["full"][i])
        rec = {"file": r["file"], "reference": ref, "in_crosswalk": ref in checked,
               "extractor_name_matches_reread": norm(r["name"]) == ref}
        for mode in ["font_map", "conventional"]:
            got = reads[mode][i]
            rec[f"{mode}_text"] = got
            rec[f"{mode}_exact"] = got == ref
            rec[f"{mode}_cer"] = Levenshtein.distance(got, ref) / max(len(ref), 1)
        for t in tools:
            text = pages[t][r["file"]]
            rec[f"{t}_found"] = ref in text
            rec[f"{t}_fuzzy"] = fuzz.partial_ratio(ref, text) if text else 0.0
        out_rows.append(rec)

    with open(OUT / "extraction_comparison_rows.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
        w.writeheader(); w.writerows(out_rows)

    ref_rows = [r for r in out_rows if r["in_crosswalk"]]
    n = len(ref_rows)
    summ = [("rows_total", len(out_rows)), ("rows_with_checked_reference", n),
             ("distinct_reference_names", len({r["reference"] for r in ref_rows})),
             ("extractor_output_equals_reread", sum(r["extractor_name_matches_reread"] for r in out_rows))]
    for mode in ["font_map", "conventional"]:
        summ.append((f"{mode}_exact_share", sum(r[f"{mode}_exact"] for r in ref_rows) / n))
        summ.append((f"{mode}_mean_cer", sum(r[f"{mode}_cer"] for r in ref_rows) / n))
    for t in tools:
        summ.append((f"{t}_found_share", sum(r[f"{t}_found"] for r in ref_rows) / n))
        summ.append((f"{t}_mean_partial_ratio", sum(r[f"{t}_fuzzy"] for r in ref_rows) / n))
    with open(OUT / "extraction_comparison_summary.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([("measure", "value")] + summ)
    for k, v in summ:
        print(f"{k:40s} {v:.4f}" if isinstance(v, float) else f"{k:40s} {v}")


if __name__ == "__main__":
    main()

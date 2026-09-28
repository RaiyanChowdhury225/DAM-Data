"""
extractor.py — Stage 1 of DAM price extraction (PDF -> raw rows).

What this does:
  1. Recovers correct Bangla text from Nikosh/NikoshBAN PDFs.
     The PDFs' ToUnicode maps (written by Excel) are broken, but the embedded
     font subset still contains its cmap + GSUB tables. We rebuild a
     glyph-id -> Unicode map from the font itself and give it to pdfminer.
  2. Finds the main commodity table with pdfplumber.
  3. Writes one raw row per commodity: name, unit, current min/max price.

No translation or cleaning happens here. That is the next stage.

Usage:
  python extractor.py --file data/pdfs/2026-08-04_Sylhet_49c6085b2d97.pdf
  python extractor.py --limit 20
  python extractor.py --survey          # which fonts do the PDFs use?
"""
import argparse, csv, io, json, re, sys, unicodedata, warnings
from collections import Counter
from pathlib import Path

import pdfplumber
from pdfplumber.utils import extract_text
from fontTools.ttLib import TTFont
from pdfminer.cmapdb import FileUnicodeMap
from pdfminer.pdffont import PDFCIDFont, PDFTrueTypeFont
from pdfminer.pdftypes import resolve1

warnings.filterwarnings("ignore")

BASE = Path(__file__).resolve().parent          # works from any working directory
PDF_DIR = BASE / "data" / "pdfs"
MANIFEST = BASE / "data" / "download_manifest.csv"
OUT_CSV = BASE / "data" / "extracted" / "prices_raw.csv"
GLYPH_MAP_JSON = BASE / "data" / "nikosh_glyph_map.json"   # built with --build-glyph-map

RAW_FIELDS = ["source_file", "source_url", "page_number", "date_raw", "division_raw",
              "serial_raw", "commodity_type_raw", "commodity_name_raw", "unit_raw",
              "price_raw", "min_price_raw", "max_price_raw"]

# =============================================================================
# 1. Font recovery: glyph id -> Unicode, built from the embedded font
# =============================================================================
REPH = "\ue000"  # placeholder for the reph glyph (র্ written above the letter)

# Bengali block code points as of Unicode 4.0 (the Nikosh fonts predate ৎ U+09CE)
_UNASSIGNED = {0x0980, 0x0984, 0x098D, 0x098E, 0x0991, 0x0992, 0x09A9, 0x09B1, 0x09B3,
               0x09B4, 0x09B5, 0x09BA, 0x09BB, 0x09C5, 0x09C6, 0x09C9, 0x09CA, 0x09CE,
               0x09CF, 0x09D0, 0x09D1, 0x09D2, 0x09D3, 0x09D4, 0x09D5, 0x09D6, 0x09D8,
               0x09D9, 0x09DA, 0x09DB, 0x09DE, 0x09E4, 0x09E5, 0x09FC, 0x09FD, 0x09FE}
BN_CODEPOINTS = [cp for cp in range(0x0981, 0x0A00) if cp not in _UNASSIGNED]


def build_glyph_map(font_bytes):
    """Return {glyph_id: unicode_string} for one embedded TrueType font."""
    ttf = TTFont(io.BytesIO(font_bytes))
    order = ttf.getGlyphOrder()
    gid = {name: i for i, name in enumerate(order)}

    # (a) plain letters straight from the font's cmap
    base = {}
    for cp, name in ttf.getBestCmap().items():
        base.setdefault(gid[name], chr(cp))

    # (b) the subsetter drops cmap entries for chars never drawn alone
    #     (e.g. hasanta ্, chandrabindu ঁ). Bengali glyphs sit in Unicode order
    #     (। ॥ then U+0981...), so fill a gap only when the number of missing
    #     glyphs == number of missing code points.
    seq = {cp: i for i, cp in enumerate([0x0964, 0x0965] + BN_CODEPOINTS)}
    anchors = sorted((g, seq[ord(c)]) for g, c in base.items() if ord(c) in seq)
    for (g1, i1), (g2, i2) in zip(anchors, anchors[1:]):
        if g2 - g1 > 1 and i2 - i1 == g2 - g1:
            for k in range(1, g2 - g1):
                cp = ([0x0964, 0x0965] + BN_CODEPOINTS)[i1 + k]
                base.setdefault(g1 + k, chr(cp))

    # (c) conjuncts / half forms / reph come from GSUB rules: output <- inputs
    feature_of, rules = {}, {}
    if "GSUB" not in ttf:
        return {i: base[i] for i in base}
    for rec in ttf["GSUB"].table.FeatureList.FeatureRecord:
        for li in rec.Feature.LookupListIndex:
            feature_of.setdefault(li, rec.FeatureTag)
    for li, lookup in enumerate(ttf["GSUB"].table.LookupList.Lookup):
        feat = feature_of.get(li)
        for st in lookup.SubTable:
            if lookup.LookupType == 4:      # ligature: ক + ্ + ষ -> ক্ষ
                for first, ligs in st.ligatures.items():
                    for lig in ligs:
                        comps = [gid[first]] + [gid[c] for c in lig.Component]
                        rules.setdefault(gid[lig.LigGlyph], (feat, comps))
            elif lookup.LookupType == 1:    # single: glyph variant -> same char
                for a, b in st.mapping.items():
                    rules.setdefault(gid[b], (feat, [gid[a]]))

    memo = {}
    def resolve(g, depth=0):
        if g in base:
            return base[g]
        if g in memo:
            return memo[g]
        if depth > 12 or g not in rules:
            return None
        feat, comps = rules[g]
        if feat == "rphf":
            return REPH
        parts = [resolve(c, depth + 1) for c in comps]
        if None in parts:
            return None
        # below/post-base forms (ra-phala etc.) are stored as [র, ্]; logical order is ্র
        if feat in ("blwf", "pstf") and len(parts) == 2 and parts[1] == "্":
            parts = ["্", parts[0]]
        memo[g] = "".join(parts)
        return memo[g]

    gmap = {}
    for i, name in enumerate(order):
        s = resolve(i)
        if s is None and ttf["hmtx"][name][0] == 0:
            s = ""  # zero-width filler glyph Excel inserts after ligatures
        if s is not None:
            gmap[i] = s
    return gmap


def font_key(basefont):
    """'ABCDEE+NikoshBAN' -> 'NikoshBAN'"""
    return re.sub(r"^[A-Z]{6}\+", "", basefont).split(",")[0]


# glyph maps collected from normal PDFs (used by --build-glyph-map)
COLLECTED = {}

_original_cidfont_init = PDFCIDFont.__init__

def _patched_cidfont_init(self, rsrcmgr, spec, *args, **kwargs):
    """After pdfminer loads a Nikosh font, replace its broken ToUnicode map."""
    _original_cidfont_init(self, rsrcmgr, spec, *args, **kwargs)
    if "nikosh" not in self.basefont.lower() or not getattr(self, "fontfile", None):
        return
    try:
        gmap = build_glyph_map(self.fontfile.get_data())
        known = COLLECTED.setdefault(font_key(self.basefont), {})
        for g, text in gmap.items():
            if text or g not in known:      # never overwrite real text with an empty filler
                known[g] = text
        umap = FileUnicodeMap()
        # Identity-H + CIDToGIDMap /Identity  =>  cid == glyph id
        umap.cid2unichr = gmap
        self.unicode_map = umap
    except Exception as e:
        print(f"  [warn] could not rebuild map for {self.basefont}: {e}")

PDFCIDFont.__init__ = _patched_cidfont_init


# --- PDFs re-saved through Ghostscript (e.g. "PDF24 Creator") ------------------
# Ghostscript turns the Nikosh font into a 1-byte TrueType font and strips GSUB,
# so the font itself can no longer tell us the letters. But it keeps the
# original glyph ids, so we reuse the gid -> text map learned from normal PDFs.
_reference_map = None

def reference_map():
    global _reference_map
    if _reference_map is None:
        if GLYPH_MAP_JSON.exists():
            raw = json.loads(GLYPH_MAP_JSON.read_text(encoding="utf-8"))
            _reference_map = {k: {int(g): t for g, t in v.items()} for k, v in raw.items()}
        else:
            _reference_map = {}
    return _reference_map

_original_tt_init = PDFTrueTypeFont.__init__

def _patched_tt_init(self, rsrcmgr, spec, *args, **kwargs):
    _original_tt_init(self, rsrcmgr, spec, *args, **kwargs)
    if "nikosh" not in self.basefont.lower():
        return
    try:
        stream = resolve1(resolve1(spec.get("FontDescriptor", {})).get("FontFile2"))
        ttf = TTFont(io.BytesIO(stream.get_data()))
        symbol_cmap = ttf["cmap"].getcmap(3, 0)
        if "GSUB" in ttf or symbol_cmap is None:
            return                      # normal font, the standard decoding works
        ref = reference_map().get(font_key(self.basefont))
        if not ref:
            print(f"  [warn] {self.basefont}: Ghostscript font but no glyph map; "
                  f"run: python extractor.py --build-glyph-map")
            return
        gid = {name: i for i, name in enumerate(ttf.getGlyphOrder())}
        umap = FileUnicodeMap()
        # byte code -> glyph (symbol cmap uses 0xF000 + code) -> original gid -> text
        umap.cid2unichr = {cp & 0xFF: ref[gid[name]] for cp, name in symbol_cmap.cmap.items()
                           if gid[name] in ref}
        self.unicode_map = umap
    except Exception as e:
        print(f"  [warn] could not rebuild map for {self.basefont}: {e}")

PDFTrueTypeFont.__init__ = _patched_tt_init

# =============================================================================
# 2. Text fixes: visual glyph order -> logical Unicode order
# =============================================================================
CONS = "কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ\u09dc\u09dd\u09df\u09ce"
C = rf"[{CONS}]\u09bc?(?:\u09cd[{CONS}]\u09bc?)*"      # consonant cluster
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def fix_bangla(text):
    if not text:
        return text
    text = text.replace("(cid:10)", " ")      # line-feed glyph inside some cells
    # reph is drawn after its cluster -> move it in front
    text = re.sub(rf"({C})([াী]?)(\s*)([িেৈ]?){REPH}", lambda m: REPH + "".join(m.groups()), text)
    text = text.replace(REPH, "র্")
    C2 = rf"(?:র্)?{C}"
    # ে + cluster + া  ->  cluster + ো  (same for ৌ)
    text = re.sub(rf"ে({C2})া", r"\1ো", text)
    text = re.sub(rf"ে({C2})ৗ", r"\1ৌ", text)
    # ি ে ৈ are drawn before the cluster -> move after it
    text = re.sub(rf"([িেৈ])(ঁ?)({C2})", r"\3\1\2", text)
    # the font draws ASCII digits with Bangla shapes, so both appear -> unify
    text = text.translate(BN_DIGITS)
    # compose ড়/ঢ়/য় written as letter + nukta into single characters, so the
    # same name always has the same code points
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()

# =============================================================================
# 3. Table extraction
# =============================================================================
UNIT_RE = re.compile(r"কেজি|লিটার|টি|হালি|গ্রাম|ডজন")
DITTO_RE = re.compile(r'^\s*(,,|”|"|\'\')?\s*$')   # ",,"  ”  "  or blank = same as row above
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
BN_LETTER_RE = re.compile(r"[\u0985-\u09b9]")


def split_price(price_text):
    """'150.00 - 170.00' or '150.00 170.00' -> ('150.00', '170.00'); '*' / '-' / '' -> (None, None)."""
    nums = NUM_RE.findall(price_text or "")
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0]   # single price: min == max (flag in validation)
    return None, None


def find_columns(table):
    """Locate unit and current-price columns from the cell contents.

    Layouts differ between divisions (optional 'type' column, optional
    'fair price' column, ditto marks), so fixed indices don't work.
    """
    ncols = max(len(r) for r in table)
    unit_hits = [sum(1 for r in table if i < len(r) and r[i] and UNIT_RE.search(r[i]) and len(r[i]) < 25)
                 for i in range(ncols)]
    unit_col = max(range(ncols), key=unit_hits.__getitem__)
    if unit_hits[unit_col] < 3:
        return None                                   # not a price table
    data_rows = [r for r in table if unit_col < len(r) and r[unit_col]
                 and (UNIT_RE.search(r[unit_col]) or DITTO_RE.match(r[unit_col]))]
    # current price = first column right of the unit column that is mostly numbers
    for i in range(unit_col + 1, ncols):
        cells = [r[i] for r in data_rows if i < len(r)]
        if sum(1 for c in cells if c and NUM_RE.search(c)) >= 0.5 * max(len(cells), 1):
            return unit_col, i
    return None


def drop_overlapping_lines(indexed_chars, letters_only):
    """Remove text lines hidden underneath other text.

    Excel lets text overflow into a neighbouring row. It is clipped on the page
    but still in the text layer, so two lines end up on almost the same
    baseline and their characters interleave (e.g. '18000.0.000 -- 100.00').
    When two lines overlap, keep the one drawn LAST: the overflow comes from an
    earlier row, so it was drawn earlier. `indexed_chars` is [(draw_order, char)].
    Only "real" lines can clash: lines with Bangla letters for names
    (letters_only=True), lines with digits for prices. A lone '-' or a stacked
    fraction on a slightly different baseline is never dropped.
    """
    lines = []
    # glyphs of one line share the baseline (matrix[5]) even across fonts
    for i, c in sorted(indexed_chars, key=lambda ic: ic[1]["matrix"][5]):
        base = c["matrix"][5]
        if lines and abs(base - lines[-1]["base"]) < 0.3:
            lines[-1]["chars"].append((i, c))
        else:
            lines.append({"base": base, "size": c["size"], "chars": [(i, c)]})
    keep = []
    for line in lines:
        text = fix_bangla("".join(c["text"] for _, c in line["chars"])) or ""
        # names: only lines with Bangla letters can clash; prices: only lines with digits
        line["can_clash"] = bool(BN_LETTER_RE.search(text) if letters_only else re.search(r"\d", text))
        clash = None
        if line["can_clash"]:
            clash = next((k for k in keep if k["can_clash"]
                          and abs(k["base"] - line["base"]) < 0.5 * line["size"]), None)
        if clash is None:
            keep.append(line)
        elif min(i for i, _ in line["chars"]) > min(i for i, _ in clash["chars"]):
            keep[keep.index(clash)] = line     # later-drawn line wins
    return [c for line in keep for _, c in line["chars"]]


def text_in_band(chars, x0, x1, top, bottom):
    """Price text: chars whose centre lies inside the box, overlaps removed."""
    inside = [(i, c) for i, c in enumerate(chars)
              if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bottom]
    if not inside:
        return None
    return fix_bangla(extract_text(drop_overlapping_lines(inside, letters_only=False)))


def text_in_cell(chars, bbox, tol=1.0):
    """Name/type cell text: glyphs must fit inside the cell, overlaps removed."""
    x0, top, x1, bottom = bbox
    inside = [(i, c) for i, c in enumerate(chars)
              if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
              and c["top"] >= top - tol and c["bottom"] <= bottom + tol]
    if not inside:
        return None
    return fix_bangla(extract_text(drop_overlapping_lines(inside, letters_only=True)))


def extract_pdf(pdf_path):
    rows = []
    has_type_col = False       # set when a header row contains "প্রকার"
    current_type = last_unit = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # tables split across pages lose their top/bottom border; add both
            v_edges = [e for e in page.edges if e["orientation"] == "v"]
            settings = {"explicit_horizontal_lines": [min(e["top"] for e in v_edges),
                                                      max(e["bottom"] for e in v_edges)]} if v_edges else {}
            for tbl in page.find_tables(settings):
                table = [[fix_bangla(c) for c in r] for r in tbl.extract()]
                cols = find_columns(table)
                if cols is None:
                    continue                          # letter text, "reasons" table, etc.
                unit_col, price_col = cols
                # horizontal extent of the current-price cell (most common among rows)
                widths = Counter((round(row.cells[price_col][0]), round(row.cells[price_col][2]))
                                 for row in tbl.rows
                                 if price_col < len(row.cells) and row.cells[price_col])
                px0, px1 = widths.most_common(1)[0][0]
                for r, row in zip(table, tbl.rows):
                    r = r + [None] * (price_col + 3 - len(r))
                    joined = " ".join(c for c in r if c)
                    if "নাম" in joined and "পরিমাপ" in joined:
                        has_type_col = has_type_col or "প্রকার" in joined
                        continue                      # header row
                    # text cells between serial (col 0) and unit column,
                    # re-read so text spilling in from neighbouring rows is dropped
                    text_cells = [text_in_cell(page.chars, row.cells[i])
                                  if i < len(row.cells) and row.cells[i] else r[i]
                                  for i in range(1, unit_col)]
                    if has_type_col and text_cells:
                        if text_cells[0]:
                            current_type = text_cells[0]  # merged cell -> forward-fill
                        text_cells = text_cells[1:]
                    name = " ".join(c for c in text_cells if c)
                    if not BN_LETTER_RE.search(name):
                        continue                      # sub-header / blank rows
                    unit = r[unit_col]
                    if unit and UNIT_RE.search(unit):
                        last_unit = unit
                    elif DITTO_RE.match(unit or ""):
                        unit = last_unit              # ",," or blank means same unit as above
                    else:
                        continue
                    # Read the price from this row's vertical band only. Some reports
                    # miss the line between two rows, which merges their price cells.
                    band = row.cells[unit_col] if unit_col < len(row.cells) and row.cells[unit_col] else row.bbox
                    price = text_in_band(page.chars, px0, px1, band[1], band[3])
                    # min | - | max in three separate cells: widen to the third cell
                    if (len(NUM_RE.findall(price or "")) < 2 and r[price_col + 1] == "-"
                            and price_col + 2 < len(row.cells) and row.cells[price_col + 2]):
                        price = text_in_band(page.chars, px0, row.cells[price_col + 2][2], band[1], band[3])
                    mn, mx = split_price(price)
                    rows.append({"page_number": page.page_number, "serial_raw": r[0],
                                 "commodity_type_raw": current_type if has_type_col else None,
                                 "commodity_name_raw": name, "unit_raw": unit, "price_raw": price,
                                 "min_price_raw": mn, "max_price_raw": mx})
    return rows

# =============================================================================
# 4. Source metadata + CLI
# =============================================================================
def load_url_lookup():
    """filename -> pdf_url from the download manifest (column names auto-detected)."""
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        url_col = next((c for c in cols if "url" in c.lower()), None)
        file_col = next((c for c in cols if any(k in c.lower() for k in ("file", "path"))), None)
        if not url_col or not file_col:
            print(f"[warn] manifest columns not recognised: {cols}")
            return {}
        return {Path(r[file_col]).name: r[url_col] for r in reader if r.get(file_col)}


def source_info(pdf_path, urls):
    # filename format from downloader.py: YYYY-MM-DD_Division_hash.pdf
    parts = pdf_path.stem.split("_")
    return {"source_file": pdf_path.name, "source_url": urls.get(pdf_path.name, ""),
            "date_raw": parts[0] if parts else "",
            "division_raw": parts[1] if len(parts) > 1 else ""}


def survey_fonts(pdfs):
    counts = Counter()
    for p in pdfs:
        try:
            with pdfplumber.open(p) as pdf:
                fonts = {re.sub(r"^[A-Z]{6}\+", "", c["fontname"]) for pg in pdf.pages for c in pg.chars}
            counts[" | ".join(sorted(fonts)) or "(no text layer)"] += 1
        except Exception as e:
            counts[f"ERROR {type(e).__name__}"] += 1
    for combo, n in counts.most_common():
        print(f"{n:5d}  {combo}")


def build_reference_map(pdfs):
    """Open every PDF's fonts once and save the union of their gid -> text maps."""
    for p in pdfs:
        try:
            with pdfplumber.open(p) as pdf:
                for page in pdf.pages:
                    page.chars                     # forces pdfminer to load the fonts
        except Exception as e:
            print(f"skip {p.name}: {e}")
    GLYPH_MAP_JSON.write_text(json.dumps(COLLECTED, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {GLYPH_MAP_JSON}: " + ", ".join(f"{k}={len(v)} glyphs" for k, v in COLLECTED.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="extract one PDF and print rows")
    ap.add_argument("--limit", type=int, help="process the first N PDFs into the CSV")
    ap.add_argument("--survey", action="store_true", help="count font combinations")
    ap.add_argument("--build-glyph-map", action="store_true",
                    help="learn Nikosh glyph ids from normal PDFs (needed for Ghostscript PDFs)")
    args = ap.parse_args()

    pdfs = [Path(args.file)] if args.file else sorted(PDF_DIR.glob("*.pdf"))[: args.limit]
    if args.survey:
        return survey_fonts(pdfs)
    if args.build_glyph_map:
        return build_reference_map(pdfs)

    urls = load_url_lookup()
    all_rows = []
    for pdf_path in pdfs:
        try:
            rows = extract_pdf(pdf_path)
        except Exception as e:
            print(f"FAIL  {pdf_path.name}: {type(e).__name__}: {e}")
            continue
        meta = source_info(pdf_path, urls)
        rows = [{**meta, **r} for r in rows]
        missing = sum(r["min_price_raw"] is None for r in rows)
        print(f"OK    {pdf_path.name}: {len(rows)} rows, {missing} without price")
        all_rows.extend(rows)
        if args.file:
            for r in rows:
                print(f"  p{r['page_number']} | {r['commodity_type_raw']} | {r['commodity_name_raw']} | "
                      f"{r['unit_raw']} | {r['min_price_raw']} - {r['max_price_raw']}")

    if not args.file:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows Bangla
            w = csv.DictWriter(f, fieldnames=RAW_FIELDS)
            w.writeheader()
            w.writerows(all_rows)
        print(f"\nWrote {len(all_rows)} rows from {len(pdfs)} PDFs -> {OUT_CSV}")


if __name__ == "__main__":
    sys.exit(main())
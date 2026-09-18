"""
main.py — run the DAM-Data pipeline end to end.

Stages, in order:
    scrape     scraper.py            -> data/report_metadata.csv
    download   downloader.py         -> data/pdfs/ + data/download_manifest.csv
    glyphmap   extractor.py --build-glyph-map -> data/nikosh_glyph_map.json
    extract    extractor.py          -> data/extracted/prices_raw.csv
    clean      clean.py              -> data/final/prices.csv
    target     add_target.py         -> data/final/prices_modeling.csv

    python main.py                       # run everything
    python main.py --from extract        # extract, clean, target
    python main.py --only clean          # one stage
    python main.py --skip scrape download # everything else

Each stage is the same script you run by hand; this only decides the order and
stops when one fails. Anything a stage needs (flags, TEST_MODE) still lives in
that script.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent

# stage name -> (script + arguments, file it should produce)
STAGES = {
    "scrape":   (["scraper.py"], "data/report_metadata.csv"),
    "download": (["downloader.py"], "data/download_manifest.csv"),
    "glyphmap": (["extractor.py", "--build-glyph-map"], "data/nikosh_glyph_map.json"),
    "extract":  (["extractor.py"], "data/extracted/prices_raw.csv"),
    "clean":    (["clean.py"], "data/final/prices.csv"),
    "target":   (["add_target.py"], "data/final/prices_modeling.csv"),
}
ORDER = list(STAGES)


def run_stage(name):
    script, output = STAGES[name]
    path = BASE / script[0]
    if not path.exists():
        print(f"[{name}] SKIPPED - {script[0]} not found")
        return True
    print(f"\n=== {name}: python {' '.join(script)} " + "=" * 20)
    start = time.time()
    # run from the project folder so the scripts' relative paths work
    result = subprocess.run([sys.executable, *script], cwd=BASE)
    if result.returncode != 0:
        print(f"[{name}] FAILED (exit {result.returncode}) - stopping")
        return False
    produced = BASE / output
    size = f"{produced.stat().st_size / 1024:.0f} KB" if produced.exists() else "MISSING"
    print(f"[{name}] done in {time.time() - start:.0f}s -> {output} ({size})")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=ORDER, help="start at this stage")
    ap.add_argument("--only", choices=ORDER, help="run just this stage")
    ap.add_argument("--skip", nargs="*", default=[], choices=ORDER, help="stages to leave out")
    args = ap.parse_args()

    if args.only:
        stages = [args.only]
    else:
        start = ORDER.index(args.start) if args.start else 0
        stages = [s for s in ORDER[start:] if s not in args.skip]

    print("Pipeline:", " -> ".join(stages))
    for name in stages:
        if not run_stage(name):
            return 1
    print("\nAll stages finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
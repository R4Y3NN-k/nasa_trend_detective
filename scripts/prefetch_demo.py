# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Warm the cache for every preset and print each variable's verdict. Owner: A (data).

    python scripts/prefetch_demo.py                                  # every preset in td.config.REGIONS
    python scripts/prefetch_demo.py --regions tunisia nile_delta
    python scripts/prefetch_demo.py --box 7.5 30.2 11.6 37.5 --name Tunisia
    python scripts/prefetch_demo.py --out verdicts.md --zip
    python scripts/prefetch_demo.py --box 7.5 30.2 11.6 37.5 --name Tunisia --giovanni   # + AIRS, IMERG, quota

--out also writes the summary as Markdown (to post in the team chat).
--zip packs data/cache/*.json into data/cache.zip to share (both gitignored).
Until analyze() lands (step 2) it prints a data summary instead of verdicts.
"""
from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from td import analyze as stats  # noqa: E402
from td import cache  # noqa: E402
from td.config import FIRST_YEAR, LAST_YEAR, REGIONS, VARIABLES  # noqa: E402
from td.fetch import POWER_PARAMS, FetchError, fetch_box  # noqa: E402


def _progress(done: int, total: int) -> None:
    if done == total or done % 10 == 0:
        print(f"  fetched {done}/{total} points", flush=True)


def power_variables() -> list[str]:
    """Variable ids served by POWER (from config once D fills it; else the three POWER parameters)."""
    ids = [v for v, m in VARIABLES.items() if m.get("fetcher", "power") == "power"]
    return ids or list(POWER_PARAMS)


def summarise(name: str, box, start: int, end: int) -> list[str]:
    t0 = time.time()
    bd = fetch_box(box, start, end, progress=_progress)
    sea = [(la, lo) for la, lo, land in bd.points if not land]
    lines = [
        f"### {name}, box {tuple(box)}",
        f"- Points: {bd.points_used} land used of {bd.points_total} requested"
        + (f"; sea skipped: {sea}" if sea else "") + f" ({time.time() - t0:.0f} s)",
        "- Missing months: " + ", ".join(f"{c} {int(bd.data[c].isna().sum())}" for c in bd.data.columns),
    ]
    for var in power_variables():
        col = VARIABLES.get(var, {}).get("power_param", var)
        if col not in bd.data:
            continue
        series = bd.data[col].rename(var)
        try:
            res = stats.analyze(series, var)
            words = stats.verdict(res)
        except NotImplementedError:
            s = series.dropna()
            lines.append(f"- **{var}**: {len(s)} months {s.index[0]:%Y-%m} to {s.index[-1]:%Y-%m}, "
                         f"mean {s.mean():.3f} (analyze() not merged yet: no verdict)")
            continue
        lo, hi = res["ci_decade"]
        lines.append(f"- **{var}** [{res['tier']}] {words['headline']}  \n"
                     f"  slope {res['slope_decade']:+.4f}/decade (95% CI {lo:+.4f} to {hi:+.4f}), "
                     f"Sen {res['sen_decade']:+.4f}, p_t {res['p_ttest']:.3g}, p_MK {res['p_mk']:.3g}, "
                     f"{res['n_months']} months")
    return lines


def prefetch_giovanni(box, start: int, end: int) -> list[str]:
    """Warm the Giovanni cache (second sources, step 7) so the live demo never waits on a Giovanni job."""
    from td.giovanni import GIOVANNI_VARIABLES, GiovanniError, area_box, fetch_series_giovanni

    lines = [f"- Giovanni box (rounded out to whole degrees): {area_box(box)}"]
    for gid in GIOVANNI_VARIABLES:
        t0 = time.time()
        try:
            s = fetch_series_giovanni(gid, box, start, end)
        except GiovanniError as err:
            lines.append(f"- **{gid}**: not fetched: {err}")
            continue
        lines.append(f"- **{gid}**: {len(s)} months {s.index[0]:%Y-%m} to {s.index[-1]:%Y-%m}, "
                     f"mean {s.mean():.3f} {s.attrs.get('units', '')}, last {s.iloc[-1]:.3f} "
                     f"({time.time() - t0:.0f} s)")
    return lines


def zip_cache(dest: Path) -> int:
    files = sorted(cache.cache_dir().glob("*.json"))
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f"data/cache/{f.name}")
    return len(files)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", nargs="*", metavar="ID", help="preset ids from td.config.REGIONS (default: all)")
    ap.add_argument("--box", nargs=4, type=float, metavar=("W", "S", "E", "N"), help="any box instead of presets")
    ap.add_argument("--name", default="Custom box", help="label for --box")
    ap.add_argument("--start", type=int, default=FIRST_YEAR)
    ap.add_argument("--end", type=int, default=LAST_YEAR)
    ap.add_argument("--out", type=Path, help="also write the summary to this Markdown file")
    ap.add_argument("--zip", action="store_true", help="pack data/cache into data/cache.zip")
    ap.add_argument("--giovanni", action="store_true",
                    help="also fetch the second sources (AIRS, IMERG) via Giovanni; needs EARTHDATA_* in .env")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    jobs = []
    if args.box:
        jobs.append((args.name, tuple(args.box)))
    for rid in args.regions if args.regions is not None else ([] if args.box else list(REGIONS)):
        if rid not in REGIONS:
            ap.error(f"unknown region {rid!r}; known: {', '.join(REGIONS) or 'none yet (step 4)'}")
        jobs.append((REGIONS[rid]["name"], tuple(REGIONS[rid]["box"])))
    if not jobs:
        ap.error("no regions yet in td.config.REGIONS (step 4); use --box W S E N --name NAME")

    out, failures = [f"## Prefetch: NASA POWER monthly (MERRA-2), {args.start}-{args.end}", ""], 0
    for name, box in jobs:
        print(f"\n== {name} ==", flush=True)
        try:
            lines = summarise(name, box, args.start, args.end)
        except (FetchError, ValueError) as err:
            failures += 1
            lines = [f"### {name}, box {box}", f"- FAILED: {err}"]
        if args.giovanni:
            lines += prefetch_giovanni(box, args.start, args.end)
        print("\n".join(lines), flush=True)
        out += lines + [""]

    if args.giovanni:
        from td.giovanni import GiovanniError, quota

        try:
            print(f"\nGiovanni monthly quota (0 to 1): {quota()}")
        except GiovanniError as err:
            print(f"\nGiovanni quota not checked: {err}")
    if args.out:
        args.out.write_text("\n".join(out), encoding="utf-8")
        print(f"\nSummary written to {args.out}")
    if args.zip:
        dest = ROOT / "data" / "cache.zip"
        print(f"Packed {zip_cache(dest)} cache files into {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

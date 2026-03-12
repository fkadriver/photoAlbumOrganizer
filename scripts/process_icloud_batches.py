#!/usr/bin/env python3
"""
Process iCloud photos in time-window batches and run the organizer on each.

The library is split into N-month time windows (default: 6 months) with a
configurable overlap (default: 1 week) so burst shots straddling a boundary
are grouped correctly.

Photos are accessed directly from the Apple Photos library — iCloud downloads
are triggered on-demand by the organizer. No separate export directory is used.

Usage:
    # Dry-run: show batches without processing
    python scripts/process_icloud_batches.py --dry-run

    # Process all batches sequentially
    python scripts/process_icloud_batches.py

    # Process only batch 2 (resume a partial run)
    python scripts/process_icloud_batches.py --only-batch 2

Options:
    --months N           Time window per batch in months (default: 6)
    --overlap-days N     Overlap in days between adjacent batches (default: 7)
    --output-dir DIR     Root dir for organizer output
                         (default: ~/icloud-organized)
    --only-batch N       Process only batch N (1-indexed)
    --dry-run            Print batch plan without processing
    --threads N          Organizer threads (default: 4)
    --face-backend NAME  Face backend (default: mediapipe)
    --no-face-swap       Disable face swap
    --port PORT          Web viewer base port (batch 1=PORT, batch 2=PORT+1, ...)
                         default: 8891
    --cpu-limit N        CPU usage limit % passed to organizer (default: 90)
"""

import argparse
import calendar
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure src/ is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# Batch planning
# ---------------------------------------------------------------------------

def get_library_date_range():
    """Return (earliest_date, latest_date) from the Photos library."""
    import osxphotos
    print("Loading Photos library metadata (this may take a minute)...")
    db = osxphotos.PhotosDB()
    dates = [
        p.date for p in db.photos()
        if p.isphoto and p.date and p.date.year >= 2003
    ]
    if not dates:
        print("  No photos found in library.")
        sys.exit(1)
    earliest = min(dates)
    latest = max(dates)
    print(f"  Found {len(dates):,} photos spanning "
          f"{earliest.strftime('%Y-%m-%d')} → {latest.strftime('%Y-%m-%d')}")
    return earliest, latest


def add_months(dt, months):
    """Add N calendar months to a datetime, clamping to month-end if needed."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def build_time_batches(earliest, latest, months_per_batch=6, overlap_days=7):
    """
    Split the library date range into time-window batches.

    Each batch covers `months_per_batch` calendar months, with `overlap_days`
    added to each end (except the first/last batch) to avoid missing photos at
    boundaries.

    Returns list of dicts:
        {
            'index':      1-indexed batch number
            'start':      datetime (inclusive, with overlap pulled back)
            'end':        datetime (inclusive, with overlap extended forward)
            'core_start': datetime (no overlap, start of month)
            'core_end':   datetime (no overlap, end of month)
        }
    """
    overlap = timedelta(days=overlap_days)
    batches = []

    # Align to start of earliest month
    core_start = earliest.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    # Align latest to end of its month
    last_day = calendar.monthrange(latest.year, latest.month)[1]
    library_end = latest.replace(
        day=last_day, hour=23, minute=59, second=59, microsecond=0
    )

    index = 1
    while core_start <= library_end:
        core_end_dt = add_months(core_start, months_per_batch)
        # Go to last day of the final month in the window
        core_end_dt = core_end_dt - timedelta(days=1)
        last_day_of_window = calendar.monthrange(core_end_dt.year, core_end_dt.month)[1]
        core_end = core_end_dt.replace(
            day=last_day_of_window, hour=23, minute=59, second=59, microsecond=0
        )
        # Cap at library end
        if core_end > library_end:
            core_end = library_end

        start = core_start - overlap if index > 1 else core_start
        end = core_end + overlap if core_end < library_end else core_end

        batches.append({
            'index': index,
            'start': start,
            'end': end,
            'core_start': core_start,
            'core_end': core_end,
        })

        if core_end >= library_end:
            break

        # Next batch starts after this core window
        core_start = add_months(core_start, months_per_batch)
        index += 1

    return batches


def print_plan(batches, months_per_batch, overlap_days):
    print(f"\n=== Batch Plan ({months_per_batch}-month windows, {overlap_days}d overlap) ===")
    for b in batches:
        overlap_info = ""
        if b['index'] > 1:
            overlap_info += f" (← {(b['core_start'] - b['start']).days}d overlap)"
        if b['end'] > b['core_end']:
            overlap_info += f" (→ {(b['end'] - b['core_end']).days}d overlap)"
        print(f"  Batch {b['index']:2d}: {b['start'].strftime('%Y-%m-%d')} → "
              f"{b['end'].strftime('%Y-%m-%d')}{overlap_info}")
    print(f"  Total: {len(batches)} batches\n")


# ---------------------------------------------------------------------------
# Organize
# ---------------------------------------------------------------------------

def organize_batch(batch, output_dir: Path, port: int, threads: int,
                   face_backend: str, face_swap: bool, cpu_limit: int,
                   dry_run: bool):
    """
    Run photo_organizer on the batch date range using the Apple Photos source.
    Photos are accessed directly from the library; iCloud downloads happen
    on-demand. No separate export directory is needed.
    """
    out_dir = output_dir / f"batch_{batch['index']:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)

    start_str = batch['start'].strftime('%Y-%m-%d')
    end_str = batch['end'].strftime('%Y-%m-%d')

    organizer = REPO_ROOT / "photo_organizer.py"
    venv_python = REPO_ROOT / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [
        python, str(organizer),
        "--source-type", "apple",
        "--apple-start-date", start_str,
        "--apple-end-date", end_str,
        "--apple-include-icloud",          # download from iCloud on demand
        "-o", str(out_dir),
        "--threads", str(threads),
        "--face-backend", face_backend,
        "--report-dir", str(REPO_ROOT / "reports"),
        "--web-viewer",
        "--port", str(port),
        "--cpu-limit", str(cpu_limit),
    ]

    if face_swap:
        cmd.append("--enable-face-swap")

    print(f"\n{'='*60}")
    print(f"Batch {batch['index']:2d}: {start_str} → {end_str}")
    print(f"  Output: {out_dir}")
    print(f"  Web viewer: http://localhost:{port}")

    if dry_run:
        print(f"  [DRY RUN] Would run:\n  {' '.join(cmd)}")
        return True

    result = subprocess.run(cmd)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Process iCloud photos in time-window batches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--months", type=int, default=6, metavar="N",
                        help="Months per batch window (default: 6)")
    parser.add_argument("--overlap-days", type=int, default=7, metavar="N",
                        help="Overlap days between batches (default: 7)")
    parser.add_argument("--output-dir",
                        default=str(Path.home() / "icloud-organized"),
                        help="Root dir for organizer output "
                             "(default: ~/icloud-organized)")
    parser.add_argument("--only-batch", type=int, metavar="N",
                        help="Process only batch N (1-indexed)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without processing")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--face-backend", default="mediapipe")
    parser.add_argument("--no-face-swap", action="store_true")
    parser.add_argument("--port", type=int, default=8891,
                        help="Base web viewer port (default: 8891)")
    parser.add_argument("--cpu-limit", type=int, default=90,
                        help="CPU usage limit %% (default: 90)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s - %(levelname)s - %(message)s")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build time-window batch plan from library metadata
    earliest, latest = get_library_date_range()
    batches = build_time_batches(
        earliest, latest,
        months_per_batch=args.months,
        overlap_days=args.overlap_days,
    )
    print_plan(batches, args.months, args.overlap_days)

    # Filter to requested batch
    if args.only_batch:
        batches = [b for b in batches if b['index'] == args.only_batch]
        if not batches:
            print(f"Error: --only-batch {args.only_batch} is out of range")
            sys.exit(1)

    if args.dry_run:
        print("[DRY RUN] No files will be processed.\n")

    # Process each batch
    failed_batches = []
    for batch in batches:
        port = args.port + batch['index'] - 1
        ok = organize_batch(
            batch, output_dir,
            port=port,
            threads=args.threads,
            face_backend=args.face_backend,
            face_swap=not args.no_face_swap,
            cpu_limit=args.cpu_limit,
            dry_run=args.dry_run,
        )
        if not ok:
            print(f"Warning: organizer returned non-zero for batch {batch['index']}")
            failed_batches.append(batch['index'])

    # Summary
    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"[DRY RUN] Would process {len(batches)} batch(es).")
    else:
        print(f"All done. {len(batches) - len(failed_batches)}/{len(batches)} batches succeeded.")
        if failed_batches:
            print(f"  Failed batches: {failed_batches}")
            print(f"  Retry with: --only-batch N")
        print(f"\nResults in: {output_dir}")
        for b in batches:
            out = output_dir / f"batch_{b['index']:02d}"
            port = args.port + b['index'] - 1
            print(f"  Batch {b['index']:2d} ({b['start'].strftime('%Y-%m')}"
                  f"–{b['end'].strftime('%Y-%m')}): "
                  f"http://localhost:{port}  →  {out}")


if __name__ == "__main__":
    main()

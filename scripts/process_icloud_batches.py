#!/usr/bin/env python3
"""
Download iCloud photos in date-range batches and run the organizer on each.

The library is split into 3 equal-count batches (by photo count, not time),
with a configurable overlap at each boundary so burst shots straddling a
boundary are grouped correctly.

Usage:
    # Dry-run: show batches without downloading
    python scripts/process_icloud_batches.py --dry-run

    # Download all batches then process
    python scripts/process_icloud_batches.py

    # Only download batch 2 (resume a partial run)
    python scripts/process_icloud_batches.py --only-batch 2

    # Download only, skip organizing
    python scripts/process_icloud_batches.py --download-only

    # Skip download (already done), just re-run organizer
    python scripts/process_icloud_batches.py --skip-download

Options:
    --batches N          Number of batches (default: 3)
    --overlap-days N     Overlap in days between adjacent batches (default: 7)
    --export-dir DIR     Root dir for exported photos (default: /tmp/icloud-batches)
    --output-dir DIR     Root dir for organizer output (default: /tmp/icloud-organized)
    --only-batch N       Process only batch N (1-indexed)
    --download-only      Download photos but do not run organizer
    --skip-download      Skip download, run organizer on already-exported photos
    --dry-run            Print batch plan without downloading or organizing
    --threads N          Organizer threads (default: 4)
    --face-backend NAME  Face backend (default: mediapipe)
    --no-face-swap       Disable face swap
    --port PORT          Web viewer base port (batch 1=PORT, batch 2=PORT+1, ...) default: 8891
"""

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ensure src/ is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# Batch planning
# ---------------------------------------------------------------------------

def load_library():
    """Return sorted list of (date, PhotoInfo) for all real local photos."""
    import osxphotos
    print("Loading Photos library (this may take a minute)...")
    db = osxphotos.PhotosDB()
    photos = sorted(
        [p for p in db.photos() if p.isphoto and p.date and p.date.year >= 2003],
        key=lambda p: p.date,
    )
    print(f"  Found {len(photos):,} photos spanning "
          f"{photos[0].date.strftime('%Y-%m-%d')} → {photos[-1].date.strftime('%Y-%m-%d')}")
    return photos


def build_batches(photos, n_batches=3, overlap_days=7):
    """
    Split photos into n_batches by equal photo count.
    Each batch overlaps its neighbour by overlap_days on each side.

    Returns list of dicts:
        {
            'index':    1-indexed batch number
            'start':    datetime (inclusive, with overlap pulled back)
            'end':      datetime (inclusive, with overlap extended forward)
            'core_start': datetime (no overlap)
            'core_end':   datetime (no overlap)
            'count':    estimated photo count in the overlapping window
        }
    """
    total = len(photos)
    size = total // n_batches
    overlap = timedelta(days=overlap_days)

    batches = []
    for i in range(n_batches):
        core_start_idx = i * size
        core_end_idx = (i + 1) * size - 1 if i < n_batches - 1 else total - 1

        core_start = photos[core_start_idx].date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        core_end = photos[core_end_idx].date.replace(
            hour=23, minute=59, second=59, microsecond=0
        )

        start = core_start - overlap if i > 0 else core_start
        end = core_end + overlap if i < n_batches - 1 else core_end

        count = sum(1 for p in photos if start <= p.date <= end)

        batches.append({
            'index': i + 1,
            'start': start,
            'end': end,
            'core_start': core_start,
            'core_end': core_end,
            'count': count,
        })

    return batches


def print_plan(batches):
    print("\n=== Batch Plan ===")
    for b in batches:
        overlap_info = ""
        if b['index'] > 1:
            overlap_info += f" (← {(b['core_start'] - b['start']).days}d overlap)"
        if b['index'] < len(batches):
            overlap_info += f" (→ {(b['end'] - b['core_end']).days}d overlap)"
        print(f"  Batch {b['index']}: {b['start'].strftime('%Y-%m-%d')} → "
              f"{b['end'].strftime('%Y-%m-%d')}  ({b['count']:,} photos){overlap_info}")
    print()


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def export_batch(batch, export_dir: Path, dry_run=False):
    """
    Export all photos in the batch date range using osxphotos.
    Photos not on disk are exported via Photos.app (triggers iCloud download).
    Already-local photos are hard-linked (fast, no copy).

    Returns (exported, skipped, failed) counts.
    """
    import osxphotos
    from osxphotos import ExportOptions

    batch_dir = export_dir / f"batch_{batch['index']:02d}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    start, end = batch['start'], batch['end']
    print(f"\n{'='*60}")
    print(f"Batch {batch['index']}: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")
    print(f"Export dir: {batch_dir}")

    if dry_run:
        print(f"  [DRY RUN] Would export ~{batch['count']:,} photos")
        return 0, 0, 0

    print("  Querying library...")
    db = osxphotos.PhotosDB()
    candidates = [
        p for p in db.photos()
        if p.isphoto and p.date and start <= p.date <= end
    ]
    print(f"  Found {len(candidates):,} photos in range")

    exported = skipped = failed = 0
    local_count = sum(1 for p in candidates if p.path and Path(p.path).exists())
    icloud_count = len(candidates) - local_count
    print(f"  Local: {local_count:,}  |  iCloud (will download): {icloud_count:,}")

    t0 = time.time()
    for i, photo in enumerate(candidates):
        if i % 100 == 0 and i > 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            remaining = (len(candidates) - i) / rate if rate > 0 else 0
            print(f"  [{i:5d}/{len(candidates):5d}] "
                  f"{rate:.1f} photos/s  ETA: {remaining/60:.0f}m", end='\r')

        dest_file = batch_dir / photo.original_filename
        if dest_file.exists():
            skipped += 1
            continue

        try:
            if photo.path and Path(photo.path).exists():
                # Already local — hard-link (instant, no disk space used)
                dest_file.hardlink_to(photo.path)
                exported += 1
            else:
                # iCloud — export via Photos.app (downloads on demand)
                results = photo.export(
                    str(batch_dir),
                    use_photos_export=True,
                    timeout=120,
                    overwrite=False,
                )
                if results:
                    exported += 1
                else:
                    failed += 1
        except Exception as e:
            logging.warning(f"  Export failed for {photo.original_filename}: {e}")
            failed += 1

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed/60:.1f}m: "
          f"{exported:,} exported, {skipped:,} skipped, {failed:,} failed")
    return exported, skipped, failed


# ---------------------------------------------------------------------------
# Organize
# ---------------------------------------------------------------------------

def organize_batch(batch, export_dir: Path, output_dir: Path,
                   port: int, threads: int, face_backend: str,
                   face_swap: bool, dry_run: bool):
    """Run photo_organizer on the batch's export directory."""
    batch_dir = export_dir / f"batch_{batch['index']:02d}"
    out_dir = output_dir / f"batch_{batch['index']:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)

    organizer = REPO_ROOT / "photo_organizer.py"
    venv_python = REPO_ROOT / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [
        python, str(organizer),
        "--source-type", "local",
        "-s", str(batch_dir),
        "-o", str(out_dir),
        "--threads", str(threads),
        "--face-backend", face_backend,
        "--report-dir", str(REPO_ROOT / "reports"),
        "--web-viewer",
        "--port", str(port),
    ]

    if face_swap:
        cmd.append("--enable-face-swap")

    print(f"\n{'='*60}")
    print(f"Organizing batch {batch['index']} → {out_dir}")
    print(f"  Web viewer: http://localhost:{port}")
    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(cmd)}")
        return True

    result = subprocess.run(cmd)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download iCloud photos in batches and organize them",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--batches", type=int, default=3, metavar="N",
                        help="Number of batches (default: 3)")
    parser.add_argument("--overlap-days", type=int, default=7, metavar="N",
                        help="Overlap days between batches (default: 7)")
    parser.add_argument("--export-dir", default="/tmp/icloud-batches",
                        help="Root dir for exported photos (default: /tmp/icloud-batches)")
    parser.add_argument("--output-dir", default="/tmp/icloud-organized",
                        help="Root dir for organizer output (default: /tmp/icloud-organized)")
    parser.add_argument("--only-batch", type=int, metavar="N",
                        help="Process only batch N (1-indexed)")
    parser.add_argument("--download-only", action="store_true",
                        help="Download photos but do not run organizer")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip download, run organizer on already-exported photos")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without downloading or organizing")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--face-backend", default="mediapipe")
    parser.add_argument("--no-face-swap", action="store_true")
    parser.add_argument("--port", type=int, default=8891,
                        help="Base web viewer port (default: 8891)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s - %(levelname)s - %(message)s")

    export_dir = Path(args.export_dir)
    output_dir = Path(args.output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Plan batches
    photos = load_library()
    batches = build_batches(photos, n_batches=args.batches,
                            overlap_days=args.overlap_days)
    print_plan(batches)

    # Filter to requested batch
    if args.only_batch:
        batches = [b for b in batches if b['index'] == args.only_batch]
        if not batches:
            print(f"Error: --only-batch {args.only_batch} is out of range")
            sys.exit(1)

    if args.dry_run:
        print("[DRY RUN] No files will be downloaded or processed.\n")

    # Process each batch
    total_exported = total_failed = 0
    for batch in batches:
        # 1. Download
        if not args.skip_download:
            exp, skipped, failed = export_batch(
                batch, export_dir, dry_run=args.dry_run
            )
            total_exported += exp
            total_failed += failed
        else:
            batch_dir = export_dir / f"batch_{batch['index']:02d}"
            n = len(list(batch_dir.glob("*"))) if batch_dir.exists() else 0
            print(f"\nBatch {batch['index']}: skipping download, "
                  f"{n:,} files already in {batch_dir}")

        # 2. Organize
        if not args.download_only:
            port = args.port + batch['index'] - 1
            ok = organize_batch(
                batch, export_dir, output_dir,
                port=port,
                threads=args.threads,
                face_backend=args.face_backend,
                face_swap=not args.no_face_swap,
                dry_run=args.dry_run,
            )
            if not ok:
                print(f"Warning: organizer returned non-zero for batch {batch['index']}")

    # Summary
    if not args.dry_run and not args.skip_download:
        print(f"\n{'='*60}")
        print(f"All done. Exported: {total_exported:,}  Failed: {total_failed:,}")
        print(f"Results in: {output_dir}")
        for b in batches:
            out = output_dir / f"batch_{b['index']:02d}"
            port = args.port + b['index'] - 1
            print(f"  Batch {b['index']}: http://localhost:{port}  ({out})")


if __name__ == "__main__":
    main()

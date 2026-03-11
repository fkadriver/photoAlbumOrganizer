#!/usr/bin/env python3
"""
Feature comparison test runner for Photo Album Organizer.

Runs 6 configurations in hybrid mode with a small sample of Immich photos,
saves a report for each, then launches web viewers on separate ports so
you can compare the results side-by-side.

Usage:
    python tests/run_comparison_tests.py [--limit N] [--port-start PORT]

Defaults:
    --limit      30 photos per run
    --port-start 8891 (viewers on 8891-8896)

Settings are loaded from ~/.config/photo-organizer/immich.conf.
Override with IMMICH_URL / IMMICH_API_KEY env vars.
"""

import argparse
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SCRIPT = REPO_ROOT / "photo_organizer.py"
BASE_DIR = Path("/tmp/photo_tests")
IMMICH_LIBRARY = "/mnt/immich/library/library/"

CONFIGS = [
    {
        "name": "baseline",
        "label": "Baseline (no special features)",
        "flags": [],
    },
    {
        "name": "face_swap",
        "label": "Face Swap (swap closed eyes)",
        "flags": ["--enable-face-swap"],
    },
    {
        "name": "face_swap_no_closed",
        "label": "Face Swap (keep closed eyes)",
        "flags": ["--enable-face-swap", "--no-swap-closed-eyes"],
    },
    {
        "name": "hdr",
        "label": "HDR Merging",
        "flags": ["--enable-hdr"],
    },
    {
        "name": "server_faces",
        "label": "Immich Server Faces",
        "flags": ["--immich-use-server-faces"],
    },
    {
        "name": "group_by_person",
        "label": "Group by Person + Server Faces",
        "flags": ["--immich-group-by-person", "--immich-use-server-faces"],
    },
    {
        "name": "all_features",
        "label": "All Features Combined",
        "flags": [
            "--enable-face-swap",
            "--enable-hdr",
            "--immich-group-by-person",
            "--immich-use-server-faces",
        ],
    },
]


def load_immich_config():
    """Load URL and API key from ~/.config/photo-organizer/immich.conf."""
    conf_file = Path.home() / ".config" / "photo-organizer" / "immich.conf"
    config = {}
    if conf_file.exists():
        for line in conf_file.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip().strip('"').strip("'")
    url = os.environ.get("IMMICH_URL") or config.get("IMMICH_URL", "http://localhost:2283")
    api_key = os.environ.get("IMMICH_API_KEY") or config.get("IMMICH_API_KEY", "")
    return url, api_key


def run_config(cfg, url, api_key, limit, common_flags):
    """Run photo_organizer.py for a single configuration."""
    out_dir = BASE_DIR / cfg["name"]
    report_dir = out_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(SCRIPT),
        "--source-type", "hybrid",
        "--immich-url", url,
        "--immich-api-key", api_key,
        "--immich-library-path", IMMICH_LIBRARY,
        "--output", str(out_dir),
        "--report-dir", str(report_dir),
        "--limit", str(limit),
        "--min-group-size", "2",
        "--threads", "2",
        "--tag-only",
        "--force-fresh",
    ] + common_flags + cfg["flags"]

    print(f"\n{'='*60}")
    print(f"  Running: {cfg['label']}")
    print(f"  Output:  {out_dir}")
    print(f"{'='*60}")

    start = time.time()
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    elapsed = time.time() - start

    report = report_dir / "latest.json"
    ok = result.returncode == 0 and report.exists()
    status = "OK" if ok else f"FAILED (rc={result.returncode})"
    print(f"  → {status} in {elapsed:.0f}s  report: {report}")
    return ok, report


def launch_viewer(report_path, port, url, api_key):
    """Launch a web viewer for a report in a background thread."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from web_viewer import start_viewer_background
    from immich_client import ImmichClient

    client = ImmichClient(url=url, api_key=api_key, verify_ssl=False)
    report_dir = str(report_path.parent)
    start_viewer_background(
        str(report_path),
        port=port,
        immich_client=client,
        report_dir=report_dir,
    )


def main():
    parser = argparse.ArgumentParser(description="Run feature comparison tests")
    parser.add_argument("--limit", type=int, default=30, help="Photos per run (default: 30)")
    parser.add_argument("--port-start", type=int, default=8891, help="First viewer port (default: 8891)")
    parser.add_argument("--runs", nargs="*", help="Run only these config names (default: all)")
    parser.add_argument("--viewer-only", action="store_true",
                        help="Skip processing, only launch viewers for existing reports")
    args = parser.parse_args()

    url, api_key = load_immich_config()
    if not api_key:
        print("ERROR: No IMMICH_API_KEY found in config or environment.")
        print("Set it in ~/.config/photo-organizer/immich.conf or IMMICH_API_KEY env var.")
        sys.exit(1)

    print(f"\nImmich URL:      {url}")
    print(f"Immich library:  {IMMICH_LIBRARY}")
    print(f"Photo limit:     {args.limit} per run")
    print(f"Output base:     {BASE_DIR}")
    print(f"Configurations:  {len(CONFIGS)}")

    # Filter configs if --runs specified
    configs = CONFIGS
    if args.runs:
        configs = [c for c in CONFIGS if c["name"] in args.runs]
        if not configs:
            print(f"ERROR: No configs matched {args.runs}. Valid names: {[c['name'] for c in CONFIGS]}")
            sys.exit(1)

    results = []

    if not args.viewer_only:
        for cfg in configs:
            ok, report = run_config(cfg, url, api_key, args.limit, [])
            results.append((cfg, ok, report))
    else:
        for cfg in configs:
            report = BASE_DIR / cfg["name"] / "reports" / "latest.json"
            ok = report.exists()
            results.append((cfg, ok, report))

    # Launch web viewers for successful runs
    print(f"\n{'='*60}")
    print("  Launching web viewers...")
    print(f"{'='*60}\n")

    sys.path.insert(0, str(REPO_ROOT / "src"))

    port = args.port_start
    viewer_ports = []
    for cfg, ok, report in results:
        if ok:
            launch_viewer(report, port, url, api_key)
            viewer_ports.append((cfg, port, report))
            port += 1
        else:
            print(f"  SKIP {cfg['name']}: no report found")

    # Give servers a moment to bind
    time.sleep(1)

    print("\n" + "="*60)
    print("  COMPARISON VIEWER SUMMARY")
    print("="*60)
    for cfg, p, report in viewer_ports:
        print(f"  http://localhost:{p}  →  {cfg['label']}")
    print("="*60)
    print("\nPress Ctrl+C to stop all viewers.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

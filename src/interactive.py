"""
Interactive menu system for Photo Album Organizer.

Provides a guided setup experience as an alternative to CLI flags.
Launched via `python photo_organizer.py -i`.
"""

import argparse
import getpass
import os
import sys


# --- Primitive helpers ---

def _print_header(title):
    """Print a prominent section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _print_section(title):
    """Print a sub-section header."""
    print("\n" + "-" * 60)
    print(f"  {title}")
    print("-" * 60)


def _prompt_choice(prompt, choices, default=None, descriptions=None):
    """Prompt user to pick from a numbered list.

    Args:
        prompt: Question text.
        choices: List of short string values (e.g. ['local', 'immich']).
        default: Default value (must be in *choices*). Shown in brackets.
        descriptions: Optional list of descriptions, parallel to *choices*.

    Returns:
        The selected choice string.
    """
    print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        marker = " *" if choice == default else ""
        desc = f"  - {descriptions[i-1]}" if descriptions else ""
        print(f"  {i}) {choice}{marker}{desc}")
    if default:
        hint = f" [{default}]"
    else:
        hint = ""

    while True:
        raw = input(f"  Enter choice{hint}: ").strip()
        if not raw and default is not None:
            return default
        # Accept by number
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        # Accept by text (case-insensitive)
        for c in choices:
            if raw.lower() == c.lower():
                return c
        print(f"  Invalid choice. Enter 1-{len(choices)} or one of: {', '.join(choices)}")


def _prompt_text(prompt, default=None, required=False, validator=None):
    """Prompt for free-text input.

    Args:
        prompt: Question text.
        default: Default value shown in brackets.
        required: If True, empty input is rejected (unless default exists).
        validator: Optional callable(value) -> error_message or None.

    Returns:
        The entered string (with ~ expanded for paths).
    """
    hint = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {prompt}{hint}: ").strip()
        if not raw:
            if default is not None:
                return default
            if required:
                print("  This field is required.")
                continue
            return ""
        value = os.path.expanduser(raw)
        if validator:
            err = validator(value)
            if err:
                print(f"  {err}")
                continue
        return value


def _prompt_int(prompt, default=None, min_val=None, max_val=None):
    """Prompt for an integer within an optional range."""
    parts = []
    if min_val is not None:
        parts.append(f"min={min_val}")
    if max_val is not None:
        parts.append(f"max={max_val}")
    range_hint = f" ({', '.join(parts)})" if parts else ""
    default_hint = f" [{default}]" if default is not None else ""

    while True:
        raw = input(f"  {prompt}{range_hint}{default_hint}: ").strip()
        if not raw and default is not None:
            return default
        try:
            val = int(raw)
        except ValueError:
            print("  Please enter a valid integer.")
            continue
        if min_val is not None and val < min_val:
            print(f"  Value must be at least {min_val}.")
            continue
        if max_val is not None and val > max_val:
            print(f"  Value must be at most {max_val}.")
            continue
        return val


def _prompt_float(prompt, default=None, min_val=None, max_val=None):
    """Prompt for a float within an optional range."""
    parts = []
    if min_val is not None:
        parts.append(f"min={min_val}")
    if max_val is not None:
        parts.append(f"max={max_val}")
    range_hint = f" ({', '.join(parts)})" if parts else ""
    default_hint = f" [{default}]" if default is not None else ""

    while True:
        raw = input(f"  {prompt}{range_hint}{default_hint}: ").strip()
        if not raw and default is not None:
            return default
        try:
            val = float(raw)
        except ValueError:
            print("  Please enter a valid number.")
            continue
        if min_val is not None and val < min_val:
            print(f"  Value must be at least {min_val}.")
            continue
        if max_val is not None and val > max_val:
            print(f"  Value must be at most {max_val}.")
            continue
        return val


def _prompt_bool(prompt, default=True):
    """Prompt for yes/no. Returns bool."""
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"  {prompt} {hint}: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please enter y or n.")


# --- Path validator ---

def _validate_source_path(path):
    """Return error string if path doesn't exist, else None."""
    if not os.path.exists(path):
        return f"Path does not exist: {path}"
    return None


# --- Section prompts ---

def _prompt_source_type():
    """Step 1: choose local or immich."""
    _print_section("Step 1: Source Type")
    return _prompt_choice(
        "Where are your photos?",
        ["local", "immich"],
        default="local",
        descriptions=["Photos on your local filesystem", "Immich photo management server"],
    )


def _prompt_local_options():
    """Step 2a: local source paths."""
    _print_section("Step 2: Local Source Options")
    source = _prompt_text("Source directory", required=True, validator=_validate_source_path)
    output = _prompt_text("Output directory", required=True)
    # Ensure output dir path is expanded
    output = os.path.expanduser(output)
    return {"source": source, "output": output}


def _prompt_immich_options():
    """Step 2b: Immich connection settings."""
    _print_section("Step 2: Immich Connection")
    url = _prompt_text("Immich server URL (e.g. http://immich:2283)", required=True)
    print()
    # Use getpass so the key is not echoed
    api_key = getpass.getpass("  Immich API key (hidden): ").strip()
    while not api_key:
        print("  API key is required.")
        api_key = getpass.getpass("  Immich API key (hidden): ").strip()
    print()
    album = _prompt_text("Process specific album (leave blank for all)")
    cache_dir = _prompt_text("Cache directory (leave blank for default)")
    cache_size = _prompt_int("Cache size in MB", default=5000, min_val=100)
    verify_ssl = _prompt_bool("Verify SSL certificates?", default=True)
    full_res = _prompt_bool("Download full resolution? (default uses thumbnails)", default=False)

    return {
        "immich_url": url,
        "immich_api_key": api_key,
        "immich_album": album or None,
        "immich_cache_dir": cache_dir or None,
        "immich_cache_size": cache_size,
        "no_verify_ssl": not verify_ssl,
        "use_full_resolution": full_res,
    }


def _prompt_immich_actions():
    """Step 2b (continued): Immich-specific actions."""
    _print_section("Step 2b: Immich Actions")
    tag_only = _prompt_bool("Tag-only mode (just tag duplicates, no download)?", default=False)
    create_albums = _prompt_bool("Create albums for each group?", default=False)
    album_prefix = "Organized-"
    if create_albums:
        album_prefix = _prompt_text("Album prefix", default="Organized-")
    mark_fav = _prompt_bool("Mark best photo as favorite?", default=False)

    need_output = not tag_only and not create_albums
    output = None
    if need_output:
        output = _prompt_text("Output directory for downloads", required=True)
        output = os.path.expanduser(output)
    elif not tag_only:
        # Optional output when creating albums
        output = _prompt_text("Output directory (optional, leave blank to skip)")
        output = os.path.expanduser(output) if output else None

    return {
        "tag_only": tag_only,
        "create_albums": create_albums,
        "album_prefix": album_prefix,
        "mark_best_favorite": mark_fav,
        "output": output,
    }


def _prompt_processing():
    """Step 3: processing tuning."""
    _print_section("Step 3: Processing Options")
    threshold = _prompt_int("Similarity threshold (lower=stricter)", default=5, min_val=0, max_val=64)
    time_window = _prompt_int(
        "Time window in seconds (0 to disable)", default=300, min_val=0
    )
    threads = _prompt_int("Number of threads", default=2, min_val=1)
    return {"threshold": threshold, "time_window": time_window, "threads": threads}


def _prompt_advanced():
    """Step 4: HDR / face-swap (opt-in)."""
    _print_section("Step 4: Advanced Options")
    if not _prompt_bool("Configure advanced options (HDR, face-swap)?", default=False):
        return {
            "enable_hdr": False,
            "hdr_gamma": 2.2,
            "enable_face_swap": False,
            "swap_closed_eyes": True,
            "face_backend": "auto",
        }

    enable_hdr = _prompt_bool("Enable HDR merging for bracketed exposures?", default=False)
    hdr_gamma = 2.2
    if enable_hdr:
        hdr_gamma = _prompt_float("HDR tone-mapping gamma", default=2.2, min_val=0.1, max_val=10.0)

    enable_face_swap = _prompt_bool("Enable face swapping (fix closed eyes)?", default=False)
    swap_closed_eyes = True
    face_backend = "auto"
    if enable_face_swap:
        swap_closed_eyes = _prompt_bool("Swap faces with closed eyes?", default=True)
        face_backend = _prompt_choice(
            "Face detection backend:",
            ["auto", "face_recognition", "mediapipe"],
            default="auto",
        )

    return {
        "enable_hdr": enable_hdr,
        "hdr_gamma": hdr_gamma,
        "enable_face_swap": enable_face_swap,
        "swap_closed_eyes": swap_closed_eyes,
        "face_backend": face_backend,
    }


def _prompt_run_options():
    """Step 5: run options."""
    _print_section("Step 5: Run Options")
    dry_run = _prompt_bool("Dry run (show what would be done without acting)?", default=False)
    verbose = _prompt_bool("Verbose output?", default=False)
    limit_raw = _prompt_text("Limit to first N photos (leave blank for unlimited)")
    limit = None
    if limit_raw:
        try:
            limit = int(limit_raw)
            if limit < 1:
                limit = None
        except ValueError:
            print("  Invalid number, ignoring limit.")
            limit = None
    return {"dry_run": dry_run, "verbose": verbose, "limit": limit}


# --- Summary / confirmation ---

def _print_summary(settings):
    """Print a formatted summary of all settings."""
    _print_header("Configuration Summary")
    for key, value in sorted(settings.items()):
        display = value
        # Mask sensitive values
        if "api_key" in key and value:
            display = value[:4] + "****" + value[-4:] if len(str(value)) > 8 else "****"
        # Pretty-print None
        if value is None:
            display = "(not set)"
        if value == "":
            display = "(not set)"
        print(f"  {key:.<30s} {display}")
    print("=" * 60)


def _build_namespace(settings):
    """Convert flat settings dict to argparse.Namespace with correct attr names."""
    ns = argparse.Namespace()
    ns.source_type = settings["source_type"]
    ns.source = settings.get("source")
    ns.output = settings.get("output")
    ns.immich_url = settings.get("immich_url")
    ns.immich_api_key = settings.get("immich_api_key")
    ns.immich_album = settings.get("immich_album")
    ns.immich_cache_dir = settings.get("immich_cache_dir")
    ns.immich_cache_size = settings.get("immich_cache_size", 5000)
    ns.no_verify_ssl = settings.get("no_verify_ssl", False)
    ns.use_full_resolution = settings.get("use_full_resolution", False)
    ns.threshold = settings.get("threshold", 5)
    ns.time_window = settings.get("time_window", 300)
    ns.tag_only = settings.get("tag_only", False)
    ns.create_albums = settings.get("create_albums", False)
    ns.album_prefix = settings.get("album_prefix", "Organized-")
    ns.mark_best_favorite = settings.get("mark_best_favorite", False)
    ns.resume = False
    ns.force_fresh = False
    ns.state_file = None
    ns.enable_hdr = settings.get("enable_hdr", False)
    ns.hdr_gamma = settings.get("hdr_gamma", 2.2)
    ns.face_backend = settings.get("face_backend", "auto")
    ns.enable_face_swap = settings.get("enable_face_swap", False)
    ns.swap_closed_eyes = settings.get("swap_closed_eyes", True)
    ns.verbose = settings.get("verbose", False)
    ns.dry_run = settings.get("dry_run", False)
    ns.limit = settings.get("limit")
    ns.threads = settings.get("threads", 2)
    ns.interactive = True
    return ns


# --- Section re-edit helpers ---

_SECTION_NAMES = [
    "source type",
    "source options",
    "processing",
    "advanced",
    "run options",
]


def _edit_section(section_num, settings):
    """Re-run a single section and merge results into settings."""
    if section_num == 1:
        settings["source_type"] = _prompt_source_type()
        # Source options must be re-collected when type changes
        _collect_source_options(settings)
    elif section_num == 2:
        _collect_source_options(settings)
    elif section_num == 3:
        settings.update(_prompt_processing())
    elif section_num == 4:
        settings.update(_prompt_advanced())
    elif section_num == 5:
        settings.update(_prompt_run_options())


def _collect_source_options(settings):
    """Collect source-specific options based on current source_type."""
    if settings["source_type"] == "local":
        opts = _prompt_local_options()
        settings.update(opts)
        # Clear Immich-specific keys
        for key in ("immich_url", "immich_api_key", "immich_album",
                     "immich_cache_dir", "immich_cache_size",
                     "no_verify_ssl", "use_full_resolution",
                     "tag_only", "create_albums", "album_prefix",
                     "mark_best_favorite"):
            settings.setdefault(key, None if "cache_size" not in key else 5000)
        settings.setdefault("tag_only", False)
        settings.setdefault("create_albums", False)
        settings.setdefault("mark_best_favorite", False)
        settings.setdefault("no_verify_ssl", False)
        settings.setdefault("use_full_resolution", False)
    else:
        immich_opts = _prompt_immich_options()
        settings.update(immich_opts)
        action_opts = _prompt_immich_actions()
        # Merge output from actions (may override immich_options output)
        if action_opts.get("output"):
            settings["output"] = action_opts["output"]
        elif "output" not in settings or settings["source_type"] == "immich":
            settings["output"] = action_opts.get("output")
        settings["tag_only"] = action_opts["tag_only"]
        settings["create_albums"] = action_opts["create_albums"]
        settings["album_prefix"] = action_opts["album_prefix"]
        settings["mark_best_favorite"] = action_opts["mark_best_favorite"]
        # Clear local-specific keys
        settings.setdefault("source", None)


# --- Main entry point ---

def run_interactive_menu():
    """Run the interactive setup menu and return an argparse.Namespace.

    Raises SystemExit on Ctrl+C or user quit.
    """
    if not sys.stdin.isatty():
        print("Error: Interactive mode requires a terminal (stdin is not a TTY).",
              file=sys.stderr)
        sys.exit(1)

    try:
        _print_header("Photo Album Organizer - Interactive Setup")
        print("  Press Enter to accept defaults shown in [brackets].")
        print("  Press Ctrl+C at any time to cancel.\n")

        settings = {}

        # Step 1
        settings["source_type"] = _prompt_source_type()

        # Step 2
        _collect_source_options(settings)

        # Step 3
        settings.update(_prompt_processing())

        # Step 4
        settings.update(_prompt_advanced())

        # Step 5
        settings.update(_prompt_run_options())

        # Summary & confirmation loop
        while True:
            _print_summary(settings)
            print("\n  [c] Confirm and run")
            print("  [e] Edit a section")
            print("  [r] Restart from scratch")
            print("  [q] Quit")

            choice = input("\n  Your choice [c]: ").strip().lower()
            if choice in ("", "c", "confirm"):
                break
            elif choice in ("r", "restart"):
                return run_interactive_menu()
            elif choice in ("q", "quit"):
                print("\nSetup cancelled.")
                sys.exit(0)
            elif choice in ("e", "edit"):
                print("\n  Which section to edit?")
                for i, name in enumerate(_SECTION_NAMES, 1):
                    print(f"    {i}) {name}")
                sec = input("  Section number: ").strip()
                if sec.isdigit() and 1 <= int(sec) <= len(_SECTION_NAMES):
                    _edit_section(int(sec), settings)
                else:
                    print("  Invalid section number.")
            else:
                print("  Invalid choice.")

        print()
        return _build_namespace(settings)

    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(0)

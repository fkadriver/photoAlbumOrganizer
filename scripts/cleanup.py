#!/usr/bin/env python3
"""Interactive cleanup for photoOrganizer artifacts in Apple Photos.

Shows what the organizer has created, lets you choose what to remove,
then runs the cleanup — no editing of settings files required.
"""
import os
import sys

# Make src/ importable
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, 'src'))


def _hr(char="─", width=56):
    print(char * width)


def _section(title):
    print()
    _hr()
    print(f"  {title}")
    _hr()


def _prompt_bool(question, default=True):
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"  {question} [{hint}]: ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please enter y or n.")


def _prompt_choice(question, choices, default=None):
    print(f"  {question}")
    for i, c in enumerate(choices, 1):
        marker = " *" if c == default else "  "
        print(f"  {marker} {i}) {c}")
    while True:
        raw = input(f"  Choice [default: {default}]: ").strip()
        if not raw and default:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        # allow typing the name directly
        match = [c for c in choices if c.lower().startswith(raw.lower())]
        if len(match) == 1:
            return match[0]
        print(f"  Please enter a number 1–{len(choices)}.")


def _survey(photosdb):
    """Return a summary dict of what the organizer has written."""
    from apple_actions import _ORGANIZER_KEYWORDS, _KEYWORD_PREFIX_MODIFIED, _FOLDER

    summary = {
        'folder_exists': False,
        'album_count': 0,
        'album_names': [],
        'tagged_photos': 0,
        'modified_photos': 0,
    }

    # Check for photoOrganizer folder via osxphotos album info
    try:
        for album in photosdb.album_info:
            if hasattr(album, 'folder') and album.folder and album.folder.name == _FOLDER:
                summary['folder_exists'] = True
                summary['album_count'] += 1
                summary['album_names'].append(album.title)
    except Exception:
        pass

    # Also check via AppleScript (more reliable for folder presence)
    try:
        from apple_actions import _run, _esc
        ok, _ = _run(f'tell application "Photos" to exists folder "{_esc(_FOLDER)}"')
        if ok:
            summary['folder_exists'] = True
    except Exception:
        pass

    # Count tagged photos
    try:
        tagged = photosdb.photos(keywords=_ORGANIZER_KEYWORDS)
        summary['tagged_photos'] = len(tagged)
    except Exception:
        pass

    try:
        all_photos = photosdb.photos()
        summary['modified_photos'] = sum(
            1 for p in all_photos
            if any(k.startswith(_KEYWORD_PREFIX_MODIFIED) for k in (p.keywords or []))
        )
    except Exception:
        pass

    return summary


def main():
    _section("photoOrganizer — Cleanup")

    # Load Photos library
    print("\n  Loading Photos library (this may take a moment)…")
    try:
        import osxphotos
        photosdb = osxphotos.PhotosDB()
    except ImportError:
        print("\n  ✗  osxphotos not installed — cannot read Photos library.")
        print("     Albums can still be removed (keyword cleanup will be skipped).")
        photosdb = None
    except Exception as e:
        print(f"\n  ✗  Could not open Photos library: {e}")
        photosdb = None

    from apple_actions import check_permission
    print("  Checking Photos.app automation permission…")
    if not check_permission():
        print("\n  Cannot proceed without Photos.app automation access.")
        print("  Open System Settings → Privacy & Security → Automation")
        print("  and allow your terminal to control Photos, then re-run.")
        sys.exit(1)

    # Survey what exists
    _section("What photoOrganizer has created")
    if photosdb:
        summary = _survey(photosdb)
    else:
        summary = {'folder_exists': None, 'album_count': 0, 'album_names': [],
                   'tagged_photos': 0, 'modified_photos': 0}

    if summary['folder_exists']:
        print(f"  ✓  photoOrganizer folder exists in Photos.app")
        if summary['album_count']:
            print(f"     {summary['album_count']} album(s) inside it:")
            for name in summary['album_names'][:10]:
                print(f"       • {name}")
            if len(summary['album_names']) > 10:
                print(f"       … and {len(summary['album_names']) - 10} more")
    elif summary['folder_exists'] is False:
        print("  ✗  photoOrganizer folder not found in Photos.app")
    else:
        print("  ?  Could not check for photoOrganizer folder (osxphotos unavailable)")

    if photosdb:
        if summary['tagged_photos']:
            print(f"\n  ✓  {summary['tagged_photos']} photo(s) tagged with "
                  f"'best-photo' or 'archive' keywords")
        else:
            print("\n  ✗  No photos tagged with organizer keywords")

        if summary['modified_photos']:
            print(f"  ✓  {summary['modified_photos']} photo(s) with 'modified-*' keywords")

    if (not summary['folder_exists'] and not summary['tagged_photos']
            and not summary['modified_photos']):
        print("\n  Nothing to clean up.")
        sys.exit(0)

    # Choose what to clean
    _section("What to remove")

    scope = _prompt_choice(
        "Remove:",
        ["Everything (albums + keywords)", "Albums only", "Keywords only", "Cancel"],
        default="Everything (albums + keywords)",
    )

    if scope == "Cancel":
        print("\n  Cancelled.")
        sys.exit(0)

    remove_albums   = scope in ("Everything (albums + keywords)", "Albums only")
    remove_keywords = scope in ("Everything (albums + keywords)", "Keywords only")

    # Confirm
    _section("Confirm")
    print("  About to remove:")
    if remove_albums:
        print("    • photoOrganizer folder and all albums inside it")
    if remove_keywords and photosdb:
        print(f"    • best-photo / archive keywords "
              f"({summary['tagged_photos']} photos)")
        if summary['modified_photos']:
            print(f"    • modified-* keywords "
                  f"({summary['modified_photos']} photos)")
    print()
    if not _prompt_bool("Proceed?", default=False):
        print("  Cancelled.")
        sys.exit(0)

    # Run cleanup
    _section("Cleaning up")
    from apple_actions import cleanup_all, _run, _esc, _FOLDER

    if remove_albums and not remove_keywords:
        f = _esc(_FOLDER)
        ok, _ = _run(f'''tell application "Photos"
    if exists folder "{f}" then
        delete folder "{f}"
    end if
end tell''')
        if ok:
            print(f"  ✓  Removed photoOrganizer folder and all albums.")
        else:
            print(f"  ✗  Could not remove folder (check Photos.app automation permission).")

    elif remove_keywords and not remove_albums:
        from apple_actions import _remove_keyword_from_batch, _ORGANIZER_KEYWORDS, _KEYWORD_PREFIX_MODIFIED, remove_keyword
        if photosdb:
            tagged = photosdb.photos(keywords=_ORGANIZER_KEYWORDS)
            uuids = [p.uuid for p in tagged]
            total = 0
            for kw in _ORGANIZER_KEYWORDS:
                total += _remove_keyword_from_batch(uuids, kw)
            print(f"  ✓  Removed organizer keywords from {len(uuids)} photos.")

            mod_tagged = [p for p in photosdb.photos()
                         if any(k.startswith(_KEYWORD_PREFIX_MODIFIED) for k in (p.keywords or []))]
            for p in mod_tagged:
                for kw in [k for k in p.keywords if k.startswith(_KEYWORD_PREFIX_MODIFIED)]:
                    remove_keyword(p.uuid, kw)
            if mod_tagged:
                print(f"  ✓  Removed modified-* keywords from {len(mod_tagged)} photos.")
        else:
            print("  ✗  Keyword cleanup requires osxphotos (not available).")

    else:
        results = cleanup_all(photosdb=photosdb if remove_keywords else None)
        if results['albums_removed']:
            print(f"  ✓  Albums removed.")
        if results['keywords_cleaned']:
            print(f"  ✓  Keywords cleaned from {results['keywords_cleaned']} photos.")

    _section("Done")
    print("  All selected photoOrganizer artifacts have been removed.")
    print("  You may need to refresh Photos.app (Cmd+R) to see the changes.")
    print()


if __name__ == "__main__":
    main()

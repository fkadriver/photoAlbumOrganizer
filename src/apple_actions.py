"""AppleScript-based write operations for Apple Photos.app.

osxphotos is read-only; this module uses `osascript` to drive Photos.app
for mutations: setting favorites, adding keywords, creating albums.

FIRST-RUN NOTE
--------------
The first time any function here is called, macOS may show a permission
dialog: "<app> wants to control Photos". The terminal/process must be
granted Automation access in:
  System Settings → Privacy & Security → Automation

Run `check_permission()` at startup to surface this early rather than
hitting a 30-second timeout mid-run.
"""
import logging
import subprocess

_TIMEOUT = 60   # seconds per osascript call
_TIMEOUT_KEYWORDS = 30  # keyword read+write is slower than album ops
_PERM_CHECKED = False  # module-level flag so we only warn once


def _run(script: str, timeout: int = _TIMEOUT) -> tuple[bool, str]:
    """Execute an AppleScript snippet and return (success, output).

    Never raises — TimeoutExpired and other errors are logged and
    returned as (False, reason) so callers can continue.
    """
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        msg = (
            "osascript timed out — Photos.app may be waiting for an "
            "Automation permission dialog. Open System Settings → "
            "Privacy & Security → Automation and allow your terminal "
            "app to control Photos, then re-run."
        )
        logging.warning(msg)
        return False, "timeout"
    except FileNotFoundError:
        logging.warning("osascript not found — Apple Photos actions require macOS")
        return False, "osascript not found"

    if result.returncode != 0:
        logging.debug("osascript error: %s", result.stderr.strip())
        return False, result.stderr.strip()
    return True, result.stdout.strip()


def _esc(s: str) -> str:
    """Escape a string for embedding in an AppleScript double-quoted literal."""
    return s.replace('\\', '\\\\').replace('"', '\\"')


# ---------------------------------------------------------------------------
# Permission pre-check
# ---------------------------------------------------------------------------

def check_permission() -> bool:
    """Test automation access to Photos.app with a fast, harmless script.

    Returns True if Photos.app responds.  Call this once at startup so
    the user sees a clear message rather than a timeout mid-run.
    """
    global _PERM_CHECKED
    ok, err = _run('tell application "Photos" to get name')
    if not ok:
        if err == "timeout":
            print(
                "\n⚠  Could not reach Photos.app via AppleScript.\n"
                "   Open System Settings → Privacy & Security → Automation\n"
                "   and allow your terminal app to control Photos, then re-run.\n"
            )
        else:
            print(f"\n⚠  Photos.app AppleScript error: {err}\n")
        return False
    _PERM_CHECKED = True
    return True


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

def set_favorite(uuid: str, favorite: bool = True) -> bool:
    """Mark (or unmark) a Photos media item as favorite."""
    val = 'true' if favorite else 'false'
    ok, _ = _run(
        f'tell application "Photos" to '
        f'set favorite of (media item id "{uuid}") to {val}'
    )
    return ok


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

def add_keyword(uuid: str, keyword: str) -> bool:
    """Add a keyword to a Photos media item (no-op if already present)."""
    return add_keywords_batch([uuid], keyword) == 1


def remove_keyword(uuid: str, keyword: str) -> bool:
    """Remove a keyword from a Photos media item (no-op if not present)."""
    kw = _esc(keyword)
    script = f'''tell application "Photos"
    set theItem to media item id "{uuid}"
    set kws to keywords of theItem
    set newKws to {{}}
    repeat with k in kws
        if (k as string) is not "{kw}" then
            set newKws to newKws & {{(k as string)}}
        end if
    end repeat
    set keywords of theItem to newKws
end tell'''
    ok, _ = _run(script)
    return ok


def add_keywords_batch(uuids: list[str], keyword: str, batch_size: int = 25) -> int:
    """Add a keyword to multiple photos in batches (one AppleScript call per batch).

    Batching avoids a per-photo osascript round-trip, which is the main
    source of slowness.  Returns count of photos successfully keyworded.
    """
    kw = _esc(keyword)
    succeeded = 0
    for start in range(0, len(uuids), batch_size):
        batch = uuids[start:start + batch_size]
        lines = ['tell application "Photos"']
        for idx, uuid in enumerate(batch):
            lines.append(
                f'    set kws{idx} to keywords of (media item id "{uuid}")\n'
                f'    if "{kw}" is not in kws{idx} then\n'
                f'        set keywords of (media item id "{uuid}") to kws{idx} & {{"{kw}"}}\n'
                f'    end if'
            )
        lines.append('end tell')
        ok, err = _run('\n'.join(lines), timeout=_TIMEOUT_KEYWORDS)
        if ok:
            succeeded += len(batch)
        elif err != "timeout":
            logging.debug("keyword batch error: %s", err)
    return succeeded


# ---------------------------------------------------------------------------
# Albums
# ---------------------------------------------------------------------------

_FOLDER = "photoOrganizer"
_BATCH_SIZE = 200


def _ensure_folder() -> bool:
    """Create the photoOrganizer folder in Photos.app if it doesn't exist."""
    f = _esc(_FOLDER)
    ok, _ = _run(f'''tell application "Photos"
    if not (exists folder "{f}") then
        make new folder named "{f}"
    end if
end tell''')
    return ok


def create_album(name: str) -> bool:
    """Create a Photos album inside the photoOrganizer folder."""
    _ensure_folder()
    n = _esc(name)
    f = _esc(_FOLDER)
    ok, _ = _run(f'''tell application "Photos"
    if not (exists album "{n}" of folder "{f}") then
        make new album named "{n}" at folder "{f}"
    end if
end tell''')
    return ok


def add_to_album(album_name: str, uuids: list[str]) -> bool:
    """Add photos to an album in the photoOrganizer folder (creates if needed)."""
    if not create_album(album_name):
        return False
    n = _esc(album_name)
    f = _esc(_FOLDER)
    ok = True
    for start in range(0, len(uuids), _BATCH_SIZE):
        batch = uuids[start:start + _BATCH_SIZE]
        items = ', '.join(f'media item id "{u}"' for u in batch)
        batch_ok, _ = _run(f'''tell application "Photos"
    add {{{items}}} to album "{n}" of folder "{f}"
end tell''')
        ok = ok and batch_ok
    return ok


def create_album_with_photos(name: str, uuids: list[str]) -> bool:
    """Convenience: create album and populate it in one call."""
    if not uuids:
        return create_album(name)
    return add_to_album(name, uuids)


# ---------------------------------------------------------------------------
# Curated albums (visible on iPhone via iCloud)
# ---------------------------------------------------------------------------
# Keywords are not visible in iOS Photos.app, so we also maintain dedicated
# albums for archive and best-photo candidates inside photoOrganizer.

_ALBUM_BEST    = "⭐ Best Photos"
_ALBUM_ARCHIVE = "🗂 Archive (Review to Delete)"


def add_to_best_photos(uuids: list[str]) -> bool:
    """Add photos to the 'Best Photos' curated album."""
    return add_to_album(_ALBUM_BEST, uuids)


def add_to_archive(uuids: list[str]) -> bool:
    """Add photos to the 'Archive' curated album for review/deletion."""
    return add_to_album(_ALBUM_ARCHIVE, uuids)

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

_TIMEOUT = 10   # seconds per osascript call (permission dialogs time out fast)
_PERM_CHECKED = False  # module-level flag so we only warn once


def _run(script: str) -> tuple[bool, str]:
    """Execute an AppleScript snippet and return (success, output).

    Never raises — TimeoutExpired and other errors are logged and
    returned as (False, reason) so callers can continue.
    """
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=_TIMEOUT,
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
    kw = _esc(keyword)
    script = f'''tell application "Photos"
    set theItem to media item id "{uuid}"
    set kws to keywords of theItem
    if "{kw}" is not in kws then
        set keywords of theItem to kws & {{"{kw}"}}
    end if
end tell'''
    ok, _ = _run(script)
    return ok


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


def add_keywords_batch(uuids: list[str], keyword: str) -> int:
    """Add a keyword to multiple photos. Returns count of successes."""
    count = 0
    for uuid in uuids:
        if add_keyword(uuid, keyword):
            count += 1
    return count


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

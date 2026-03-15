"""AppleScript-based write operations for Apple Photos.app.

osxphotos is read-only; this module uses `osascript` to drive Photos.app
for mutations: setting favorites, adding keywords, creating albums.
"""
import logging
import subprocess

_TIMEOUT = 30  # seconds per osascript call


def _run(script: str) -> tuple[bool, str]:
    """Execute an AppleScript snippet and return (success, output)."""
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    if result.returncode != 0:
        logging.debug("osascript error: %s", result.stderr.strip())
        return False, result.stderr.strip()
    return True, result.stdout.strip()


def _esc(s: str) -> str:
    """Escape a string for embedding in an AppleScript double-quoted literal."""
    return s.replace('\\', '\\\\').replace('"', '\\"')


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

_BATCH_SIZE = 200  # media items per AppleScript call (avoids arg-list limits)


def create_album(name: str) -> bool:
    """Create a Photos album if it does not already exist."""
    n = _esc(name)
    ok, _ = _run(f'''tell application "Photos"
    if not (exists album "{n}") then
        make new album with properties {{name: "{n}"}}
    end if
end tell''')
    return ok


def add_to_album(album_name: str, uuids: list[str]) -> bool:
    """Add photos to an album (creates the album if needed)."""
    if not create_album(album_name):
        return False
    n = _esc(album_name)
    ok = True
    for start in range(0, len(uuids), _BATCH_SIZE):
        batch = uuids[start:start + _BATCH_SIZE]
        items = ', '.join(f'media item id "{u}"' for u in batch)
        batch_ok, _ = _run(f'''tell application "Photos"
    add {{{items}}} to album "{n}"
end tell''')
        ok = ok and batch_ok
    return ok


def create_album_with_photos(name: str, uuids: list[str]) -> bool:
    """Convenience: create album and populate it in one call."""
    if not uuids:
        return create_album(name)
    return add_to_album(name, uuids)

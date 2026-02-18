"""
Immich cleanup module for undoing photo-organizer changes.

Provides interactive menu to delete albums, remove tags, unfavorite,
and unarchive assets that were modified by the photo organizer.
"""


def _confirm(prompt, default=False):
    """Prompt user for yes/no confirmation."""
    hint = "[y/N]" if not default else "[Y/n]"
    raw = input(f"  {prompt} {hint}: ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def _cleanup_albums(client, prefix="Organized-"):
    """Delete albums matching the organizer prefix."""
    print(f"\n--- Delete albums with prefix '{prefix}' ---")
    matched, _ = client.delete_albums_by_prefix(prefix, dry_run=True)
    if matched == 0:
        return
    if _confirm(f"Delete {matched} album(s)?"):
        _, deleted = client.delete_albums_by_prefix(prefix, dry_run=False)
        print(f"  Done: {deleted} album(s) deleted")
    else:
        print("  Skipped.")


def _cleanup_tags(client, prefix="photo-organizer/"):
    """Delete all photo-organizer tags."""
    print(f"\n--- Remove tags with prefix '{prefix}' ---")
    matched, _ = client.delete_tags_by_prefix(prefix, dry_run=True)
    if matched == 0:
        return
    if _confirm(f"Delete {matched} tag(s)?"):
        _, deleted = client.delete_tags_by_prefix(prefix, dry_run=False)
        print(f"  Done: {deleted} tag(s) deleted")
    else:
        print("  Skipped.")


def _unfavorite_best(client):
    """Unfavorite assets tagged as photo-organizer/best."""
    print("\n--- Unfavorite 'best' tagged photos ---")
    asset_ids = client.search_assets_by_tag("photo-organizer/best")
    if not asset_ids:
        print("  No assets found with 'photo-organizer/best' tag")
        return
    print(f"  Found {len(asset_ids)} asset(s) tagged 'photo-organizer/best'")
    if _confirm(f"Unfavorite {len(asset_ids)} asset(s)?"):
        if client.bulk_update_assets(asset_ids, is_favorite=False):
            print(f"  Done: {len(asset_ids)} asset(s) unfavorited")
        else:
            print("  Failed to bulk unfavorite")
    else:
        print("  Skipped.")


def _unarchive_non_best(client):
    """Unarchive assets tagged as photo-organizer/non-best."""
    print("\n--- Unarchive 'non-best' tagged photos ---")
    asset_ids = client.search_assets_by_tag("photo-organizer/non-best")
    if not asset_ids:
        print("  No assets found with 'photo-organizer/non-best' tag")
        return
    print(f"  Found {len(asset_ids)} asset(s) tagged 'photo-organizer/non-best'")
    if _confirm(f"Unarchive {len(asset_ids)} asset(s)?"):
        if client.bulk_update_assets(asset_ids, is_archived=False):
            print(f"  Done: {len(asset_ids)} asset(s) unarchived")
        else:
            print("  Failed to bulk unarchive")
    else:
        print("  Skipped.")


def _full_cleanup(client, album_prefix="Organized-"):
    """Run all cleanup steps in order."""
    print("\n=== Full Cleanup ===")
    print("This will: unfavorite best -> unarchive non-best -> delete tags -> delete albums")
    if not _confirm("Proceed with full cleanup?"):
        print("  Cancelled.")
        return
    _unfavorite_best(client)
    _unarchive_non_best(client)
    _cleanup_tags(client)
    _cleanup_albums(client, album_prefix)
    print("\n  Full cleanup complete.")


def run_cleanup_menu(client, album_prefix="Organized-"):
    """
    Display interactive cleanup menu.

    Args:
        client: ImmichClient instance
        album_prefix: Album prefix used by the organizer
    """
    while True:
        print("\n" + "=" * 50)
        print("  Immich Cleanup Menu")
        print("=" * 50)
        print(f"  [1] Delete albums by prefix ('{album_prefix}')")
        print("  [2] Remove photo-organizer/* tags")
        print("  [3] Unfavorite 'best' tagged photos")
        print("  [4] Unarchive 'non-best' tagged photos")
        print("  [5] Full cleanup (all of the above)")
        print("  [b] Back")
        print("=" * 50)

        choice = input("\n  Your choice: ").strip().lower()

        if choice == "1":
            _cleanup_albums(client, album_prefix)
        elif choice == "2":
            _cleanup_tags(client)
        elif choice == "3":
            _unfavorite_best(client)
        elif choice == "4":
            _unarchive_non_best(client)
        elif choice == "5":
            _full_cleanup(client, album_prefix)
        elif choice in ("b", "back", "q"):
            break
        else:
            print("  Invalid choice.")

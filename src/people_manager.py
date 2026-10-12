"""
Immich people-merge module.

Immich's face clustering sometimes splits one real person into multiple
person records — most visibly when the same name was typed for two
different clusters. This module provides an interactive menu to find and
merge those duplicate person records, and to reassign an individual
misassigned face without merging the people entirely.
"""

from collections import defaultdict


def _confirm(prompt, default=False):
    """Prompt user for yes/no confirmation."""
    hint = "[y/N]" if not default else "[Y/n]"
    raw = input(f"  {prompt} {hint}: ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def _print_person(client, person, prefix="  "):
    pid = person.get('id', '?')
    name = person.get('name') or '(unnamed)'
    count = client.get_person_statistics(pid)
    fav = " ★" if person.get('isFavorite') else ""
    print(f"{prefix}{name}{fav} — {count} photo(s) (ID: {pid})")


def _find_name_collisions(people):
    """Group named people by case-insensitive name.

    Returns {lowercased_name: [person dicts]} for names used by 2+ records
    — Immich's strongest signal that two clusters are really the same person.
    """
    by_name = defaultdict(list)
    for p in people:
        name = (p.get('name') or '').strip()
        if name:
            by_name[name.lower()].append(p)
    return {name: ps for name, ps in by_name.items() if len(ps) > 1}


def _merge_group(client, people, survivor_idx=0):
    """Merge `people` into people[survivor_idx]. Returns True on success."""
    ordered = [people[survivor_idx]] + [p for i, p in enumerate(people) if i != survivor_idx]
    ids = [p['id'] for p in ordered]

    print(f"\n  Will merge into: {ordered[0].get('name') or '(unnamed)'} (ID: {ids[0]})")
    for p in ordered[1:]:
        print(f"    + absorbing: {p.get('name') or '(unnamed)'} (ID: {p['id']}) "
              f"— this record will be deleted")

    if not _confirm("Proceed with merge? This cannot be undone"):
        print("  Skipped.")
        return False

    if client.merge_people(ids):
        print("  Done.")
        return True
    print("  Failed.")
    return False


def _manual_merge(client, people):
    """Let the user type two or more names/IDs to merge manually."""
    print("\n  Enter the names or person IDs to merge, separated by commas.")
    print("  The FIRST one entered becomes the survivor; the rest are merged into it and deleted.")
    raw = input("  Names/IDs: ").strip()
    if not raw:
        return
    tokens = [t.strip() for t in raw.split(',') if t.strip()]
    if len(tokens) < 2:
        print("  Need at least 2 people to merge.")
        return

    by_id = {p['id']: p for p in people}
    by_name = defaultdict(list)
    for p in people:
        by_name[(p.get('name') or '').lower()].append(p)

    selected = []
    for tok in tokens:
        if tok in by_id:
            selected.append(by_id[tok])
            continue
        matches = by_name.get(tok.lower(), [])
        if len(matches) == 1:
            selected.append(matches[0])
        elif len(matches) > 1:
            print(f"  '{tok}' matches {len(matches)} person records — use the person ID instead:")
            for p in matches:
                _print_person(client, p, prefix="    ")
            return
        else:
            print(f"  No person found matching '{tok}'")
            return

    _merge_group(client, selected)


def _reassign_face(client):
    """Move one misassigned face to a different person without merging."""
    asset_id = input("\n  Asset ID containing the misassigned face: ").strip()
    if not asset_id:
        return

    faces = client.get_asset_faces(asset_id)
    if not faces:
        print("  No faces found for that asset (check the asset ID).")
        return

    print("\n  Faces on this asset:")
    for i, f in enumerate(faces, 1):
        person = f.get('person') or {}
        print(f"  [{i}] {person.get('name') or '(unassigned)'} (person ID: {person.get('id', '?')})")

    choice = input("\n  Which face is misassigned? [number]: ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(faces)):
        print("  Invalid choice.")
        return

    face = faces[int(choice) - 1]
    source_person_id = (face.get('person') or {}).get('id')
    if not source_person_id:
        print("  This face has no assigned person to move.")
        return

    target = input("  Target person name or ID: ").strip()
    if not target:
        return

    people = client.get_people(with_hidden=True)
    target_person = next((p for p in people if p.get('id') == target), None)
    if not target_person:
        matches = [p for p in people if (p.get('name') or '').lower() == target.lower()]
        if len(matches) == 1:
            target_person = matches[0]
        elif len(matches) > 1:
            print(f"  '{target}' matches {len(matches)} person records — use the person ID instead:")
            for p in matches:
                _print_person(client, p, prefix="    ")
            return
        else:
            print(f"  No person found matching '{target}'")
            return

    print(f"\n  Moving this face from person {source_person_id} to "
          f"{target_person.get('name') or '(unnamed)'} (ID: {target_person['id']})")
    if not _confirm("Proceed?"):
        print("  Skipped.")
        return

    if client.reassign_faces(target_person['id'],
                              [{'person_id': source_person_id, 'asset_id': asset_id}]):
        print("  Done.")
    else:
        print("  Failed.")


def run_merge_people_menu(client):
    """
    Display interactive 'merge duplicate people' menu.

    Args:
        client: ImmichClient instance
    """
    while True:
        print("\n" + "=" * 50)
        print("  Immich: Merge Duplicate People")
        print("=" * 50)

        people = [p for p in client.get_people(with_hidden=True) if p.get('name')]
        collisions = _find_name_collisions(people)
        groups_list = list(collisions.values())

        if groups_list:
            print(f"\n  Found {len(groups_list)} name(s) shared by more than one person record:")
            for idx, group in enumerate(groups_list, 1):
                print(f"\n  [{idx}] \"{group[0].get('name')}\" ({len(group)} records)")
                for p in group:
                    _print_person(client, p, prefix="      ")
        else:
            print("\n  No same-name duplicates detected.")
            print("  (Different names that are really the same person won't show up "
                  "automatically — use [m] to merge those manually.)")

        print("\n  [1-N] Merge a detected group above")
        print("  [m]   Manually merge by name or ID")
        print("  [r]   Reassign a single misassigned face")
        print("  [b]   Back")
        print("=" * 50)

        choice = input("\n  Your choice: ").strip().lower()

        if choice in ("b", "back", "q"):
            break
        elif choice == "m":
            _manual_merge(client, people)
        elif choice == "r":
            _reassign_face(client)
        elif choice.isdigit() and groups_list:
            idx = int(choice) - 1
            if 0 <= idx < len(groups_list):
                _merge_group(client, groups_list[idx])
            else:
                print("  Invalid choice.")
        else:
            print("  Invalid choice.")

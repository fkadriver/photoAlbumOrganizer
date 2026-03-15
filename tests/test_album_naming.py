#!/usr/bin/env python3
"""Unit tests for PhotoOrganizer._build_album_name and _load_people_favorites."""
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _make_organizer(source=None):
    """Build a minimal PhotoOrganizer with a mock source, bypassing heavy init."""
    from organizer import PhotoOrganizer
    from photo_sources import Photo
    org = PhotoOrganizer.__new__(PhotoOrganizer)
    org.photo_source = source or MagicMock()
    org.create_albums = True
    org.album_prefix = "Organized-"
    return org


def _make_group(uuids, dt=None, persons_per_photo=None):
    """Create a list of photo_data dicts as used in _process_groups."""
    from photo_sources import Photo
    dt = dt or datetime(2024, 3, 15, tzinfo=timezone.utc)
    group = []
    for i, uid in enumerate(uuids):
        p = Photo(uid, "apple")
        persons = (persons_per_photo or {}).get(uid, [])
        p.metadata = {"persons": persons, "filename": f"{uid}.jpg"}
        group.append({"photo": p, "datetime": dt, "metadata": p.metadata})
    return group


class TestBuildAlbumName:
    def test_contains_date(self):
        org = _make_organizer()
        group = _make_group(["A", "B"], dt=datetime(2024, 3, 15, tzinfo=timezone.utc))
        name = org._build_album_name(group, 1)
        assert "2024-03-15" in name

    def test_contains_group_index(self):
        org = _make_organizer()
        group = _make_group(["A"])
        name = org._build_album_name(group, 42)
        assert "0042" in name

    def test_contains_people(self):
        org = _make_organizer()
        group = _make_group(["A", "B"],
                            persons_per_photo={"A": ["Alice", "Bob"], "B": []})
        name = org._build_album_name(group, 1)
        assert "Alice" in name
        assert "Bob" in name

    def test_max_six_people(self):
        org = _make_organizer()
        many_persons = [f"Person{i}" for i in range(10)]
        group = _make_group(["A"], persons_per_photo={"A": many_persons})
        name = org._build_album_name(group, 1)
        # Count how many persons appear in the name
        count = sum(1 for p in many_persons if p in name)
        assert count <= 6

    def test_favorites_sorted_first(self):
        org = _make_organizer()
        favorites = {"Alice": True, "Bob": False, "Carol": True}
        group = _make_group(["A"],
                            persons_per_photo={"A": ["Bob", "Carol", "Alice"]})
        name = org._build_album_name(group, 1, favorites=favorites)
        # Alice and Carol are favorites; they should appear before Bob
        alice_pos = name.find("Alice")
        carol_pos = name.find("Carol")
        bob_pos   = name.find("Bob")
        assert alice_pos < bob_pos or carol_pos < bob_pos

    def test_no_people_omits_people_segment(self):
        org = _make_organizer()
        group = _make_group(["A"], persons_per_photo={"A": []})
        name = org._build_album_name(group, 1)
        # Should still be valid: Organized-2024-03-15-0001
        parts = name.split("-")
        assert len(parts) >= 3  # at least prefix + date + index

    def test_person_name_from_group_data(self):
        """person_name field (set in person-grouping mode) is also included."""
        org = _make_organizer()
        group = _make_group(["A"])
        group[0]["person_name"] = "Dave"
        name = org._build_album_name(group, 1)
        assert "Dave" in name

    def test_unknown_date_falls_back(self):
        org = _make_organizer()
        group = _make_group(["A"])
        group[0]["datetime"] = None
        group[0]["metadata"]["date"] = None
        name = org._build_album_name(group, 1)
        assert name  # doesn't crash

    def test_format_starts_with_organized(self):
        org = _make_organizer()
        group = _make_group(["A"])
        name = org._build_album_name(group, 5)
        assert name.startswith("Organized-")

    def test_index_zero_padded_to_four_digits(self):
        org = _make_organizer()
        group = _make_group(["A"])
        assert "0001" in org._build_album_name(group, 1)
        assert "0099" in org._build_album_name(group, 99)
        assert "1234" in org._build_album_name(group, 1234)


class TestLoadPeopleFavorites:
    def test_returns_dict_of_name_to_bool(self):
        org = _make_organizer()
        org.photo_source.list_people.return_value = [
            {"name": "Alice", "is_favorite": True},
            {"name": "Bob",   "is_favorite": False},
        ]
        fav = org._load_people_favorites()
        assert fav == {"Alice": True, "Bob": False}

    def test_returns_empty_dict_on_exception(self):
        org = _make_organizer()
        org.photo_source.list_people.side_effect = Exception("not supported")
        fav = org._load_people_favorites()
        assert fav == {}

    def test_returns_empty_dict_when_no_people(self):
        org = _make_organizer()
        org.photo_source.list_people.return_value = []
        assert org._load_people_favorites() == {}

    def test_skips_people_without_name(self):
        org = _make_organizer()
        org.photo_source.list_people.return_value = [
            {"name": "Alice", "is_favorite": True},
            {"name": None,    "is_favorite": True},
            {"is_favorite": True},  # no name key
        ]
        fav = org._load_people_favorites()
        assert list(fav.keys()) == ["Alice"]


class TestOrganizeByAppleDuplicates:
    """_organize_by_apple_duplicates groups photos by their duplicate_group UUID."""

    def _make_source_with_photos(self, photos_meta):
        from photo_sources import Photo
        source = MagicMock()
        photos = []
        for uid, dup_group in photos_meta:
            p = Photo(uid, "apple")
            p.metadata = {"duplicate_group": dup_group, "filename": f"{uid}.jpg"}
            photos.append(p)
        source.list_photos.return_value = photos
        return source

    def _make_full_organizer(self, source):
        """Build an organizer with just enough attributes for _organize_by_apple_duplicates."""
        from organizer import PhotoOrganizer
        org = PhotoOrganizer.__new__(PhotoOrganizer)
        org.photo_source = source
        org.limit = None
        org.media_type = "image"
        org.apple_local_only = True
        org.apple_start_date = None
        org.apple_end_date = None
        org.apple_use_duplicates = True
        org.min_group_size = 2
        # Minimal state mock
        state = MagicMock()
        state.mark_photo_discovered = MagicMock()
        org.state = state
        return org

    def test_groups_photos_by_duplicate_uuid(self):
        from organizer import PhotoOrganizer
        source = self._make_source_with_photos([
            ("A", "DUP-GROUP-1"),
            ("B", "DUP-GROUP-1"),
            ("C", "DUP-GROUP-2"),
            ("D", "DUP-GROUP-2"),
            ("E", None),  # no duplicate
        ])
        org = self._make_full_organizer(source)
        # Patch extract_metadata and get_datetime_from_metadata
        org.extract_metadata = lambda p: p.metadata.copy()
        org.get_datetime_from_metadata = lambda m: None
        groups = org._organize_by_apple_duplicates()
        assert len(groups) == 2

    def test_singletons_excluded(self):
        from organizer import PhotoOrganizer
        source = self._make_source_with_photos([
            ("A", "DUP-1"),
            ("B", "DUP-1"),
            ("C", None),   # no group
        ])
        org = self._make_full_organizer(source)
        org.extract_metadata = lambda p: p.metadata.copy()
        org.get_datetime_from_metadata = lambda m: None
        groups = org._organize_by_apple_duplicates()
        flat_ids = [pd["photo"].id for g in groups for pd in g]
        assert "C" not in flat_ids

    def test_respects_min_group_size(self):
        from organizer import PhotoOrganizer
        source = self._make_source_with_photos([
            ("A", "DUP-1"),
            ("B", "DUP-1"),
            ("C", "DUP-1"),
        ])
        org = self._make_full_organizer(source)
        org.min_group_size = 3
        org.extract_metadata = lambda p: p.metadata.copy()
        org.get_datetime_from_metadata = lambda m: None
        groups = org._organize_by_apple_duplicates()
        assert len(groups) == 1

        org.min_group_size = 4  # too high — group should be excluded
        groups = org._organize_by_apple_duplicates()
        assert len(groups) == 0

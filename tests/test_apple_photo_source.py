#!/usr/bin/env python3
"""
Tests for ApplePhotoSource.

Tests are split into two layers:
  - Unit tests: mock osxphotos, no real library required (fast, always runnable)
  - Integration tests: hit the real Photos library (macOS only, skipped elsewhere)

Run all:
    python -m pytest tests/test_apple_photo_source.py -v

Run only unit tests:
    python -m pytest tests/test_apple_photo_source.py -v -m "not integration"

Run only integration tests:
    python -m pytest tests/test_apple_photo_source.py -v -m integration
"""

import platform
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure src/ is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from photo_sources import ApplePhotoSource, Photo


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_osxphoto(
    uuid="AABBCCDD-0000-0000-0000-000000000001",
    original_filename="IMG_001.jpg",
    path="/Users/scott/Pictures/Photos Library.photoslibrary/originals/A/IMG_001.jpg",
    date=None,
    title="Test Photo",
    description="A test photo",
    keywords=None,
    albums=None,  # list of album title strings
    persons=None,
    favorite=False,
    hidden=False,
    latitude=37.7749,
    longitude=-122.4194,
    uti="public.jpeg",
    isphoto=True,
    ismovie=False,
):
    """Return a MagicMock that looks like an osxphotos PhotoInfo object."""
    p = MagicMock()
    p.uuid = uuid
    p.original_filename = original_filename
    p.path = path
    p.date = date or datetime(2023, 6, 15, 12, 0, 0)
    p.title = title
    p.description = description
    p.keywords = keywords or []
    p.album_info = [MagicMock(title=a) for a in (albums or [])]
    p.persons = persons or []
    p.favorite = favorite
    p.hidden = hidden
    p.latitude = latitude
    p.longitude = longitude
    p.uti = uti
    p.isphoto = isphoto
    p.ismovie = ismovie
    # Apple ML score (default: no score)
    p.score = None
    p.duplicates = []
    p.burst = False
    p.burst_key_photo = False
    return p


@pytest.fixture
def mock_db():
    """A minimal mock PhotosDB with two photos and two people."""
    photo1 = _make_osxphoto(
        uuid="UUID-001",
        original_filename="beach.jpg",
        albums=["Summer 2023"],
        persons=["Alice"],
        keywords=["vacation", "beach"],
        favorite=True,
    )
    photo2 = _make_osxphoto(
        uuid="UUID-002",
        original_filename="party.heic",
        albums=["Birthday"],
        persons=["Bob", "Alice"],
        uti="public.heic",
    )
    video1 = _make_osxphoto(
        uuid="UUID-003",
        original_filename="clip.mov",
        isphoto=False,
        ismovie=True,
        uti="com.apple.quicktime-movie",
    )

    # Build mock PersonInfo objects for person_info
    def _make_person(name, facecount=5):
        pi = MagicMock()
        pi.name = name
        pi.facecount = facecount
        pi.favorite = False
        pi.keyphoto = None
        return pi

    db = MagicMock()
    db.library_path = "/Users/scott/Pictures/Photos Library.photoslibrary"
    # photos() returns all by default; albums=[x] returns subset
    db.photos.return_value = [photo1, photo2, video1]
    db.persons = ["Alice", "Bob"]
    db.person_info = [_make_person("Alice", 10), _make_person("Bob", 3)]
    return db


@pytest.fixture
def source(mock_db):
    """ApplePhotoSource with a mocked PhotosDB (no real library needed)."""
    with patch("platform.system", return_value="Darwin"), \
         patch("osxphotos.PhotosDB", return_value=mock_db):
        src = ApplePhotoSource.__new__(ApplePhotoSource)
        src.photosdb = mock_db
    return src


# ---------------------------------------------------------------------------
# Unit tests — constructor / platform guard
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_raises_on_non_darwin(self):
        with patch("platform.system", return_value="Linux"):
            with pytest.raises(RuntimeError, match="requires macOS"):
                ApplePhotoSource()

    def test_raises_if_osxphotos_missing(self):
        with patch("platform.system", return_value="Darwin"), \
             patch.dict("sys.modules", {"osxphotos": None}):
            with pytest.raises((ImportError, TypeError)):
                ApplePhotoSource()

    def test_constructs_with_mock_db(self, mock_db):
        with patch("platform.system", return_value="Darwin"), \
             patch("osxphotos.PhotosDB", return_value=mock_db) as MockDB:
            src = ApplePhotoSource()
            MockDB.assert_called_once_with(dbfile=None)
            assert src.photosdb is mock_db

    def test_passes_library_path(self, mock_db):
        custom_path = "/Volumes/External/MyPhotos.photoslibrary"
        with patch("platform.system", return_value="Darwin"), \
             patch("osxphotos.PhotosDB", return_value=mock_db) as MockDB:
            ApplePhotoSource(library_path=custom_path)
            MockDB.assert_called_once_with(dbfile=custom_path)


# ---------------------------------------------------------------------------
# Unit tests — list_photos
# ---------------------------------------------------------------------------

class TestListPhotos:
    def test_returns_only_images_by_default(self, source, mock_db):
        photos = source.list_photos(local_only=False)
        # UUID-003 is a video; should be excluded
        ids = [p.id for p in photos]
        assert "UUID-001" in ids
        assert "UUID-002" in ids
        assert "UUID-003" not in ids

    def test_returns_only_videos_when_requested(self, source, mock_db):
        photos = source.list_photos(media_type='video', local_only=False)
        assert len(photos) == 1
        assert photos[0].id == "UUID-003"

    def test_limit_is_respected(self, source, mock_db):
        photos = source.list_photos(limit=1, local_only=False)
        assert len(photos) == 1

    def test_filters_by_album(self, source, mock_db):
        # Stub album filter: only return photo1
        photo1 = mock_db.photos.return_value[0]
        mock_db.photos.return_value = [photo1]
        photos = source.list_photos(album="Summer 2023", local_only=False)
        mock_db.photos.assert_called_with(albums=["Summer 2023"])

    def test_photo_fields_populated(self, source):
        photos = source.list_photos(local_only=False)
        p = next(ph for ph in photos if ph.id == "UUID-001")

        assert p.source == "apple"
        m = p.metadata
        assert m["filename"] == "beach.jpg"
        assert m["albums"] == ["Summer 2023"]
        assert m["persons"] == ["Alice"]
        assert m["keywords"] == ["vacation", "beach"]
        assert m["favorite"] is True
        assert m["hidden"] is False
        assert m["media_type"] == "image"
        assert m["uti"] == "public.jpeg"
        # Apple-specific fields
        assert "apple_score" in m
        assert "apple_curation" in m
        assert "duplicate_group" in m
        assert "is_burst" in m
        assert "burst_key" in m
        # Default: no score, no duplicates, not a burst
        assert m["apple_score"] is None
        assert m["duplicate_group"] is None
        assert m["is_burst"] is False

    def test_date_is_iso_string(self, source):
        photos = source.list_photos(local_only=False)
        p = photos[0]
        date_str = p.metadata["date"]
        # Should be parseable as ISO 8601
        parsed = datetime.fromisoformat(date_str)
        assert isinstance(parsed, datetime)

    def test_none_date_handled(self, source, mock_db):
        mock_db.photos.return_value[0].date = None
        photos = source.list_photos(local_only=False)
        p = next(ph for ph in photos if ph.id == "UUID-001")
        assert p.metadata["date"] is None

    def test_cached_path_set_when_file_exists(self, source, mock_db, tmp_path):
        fake_file = tmp_path / "IMG_001.jpg"
        fake_file.write_bytes(b"JPEG")
        mock_db.photos.return_value[0].path = str(fake_file)
        photos = source.list_photos()  # local_only=True, file exists
        p = next(ph for ph in photos if ph.id == "UUID-001")
        assert p.cached_path == fake_file

    def test_cached_path_none_when_file_missing(self, source, mock_db):
        # With local_only=False, missing-path photos are included but cached_path is None
        mock_db.photos.return_value[0].path = "/nonexistent/path.jpg"
        photos = source.list_photos(local_only=False)
        p = next(ph for ph in photos if ph.id == "UUID-001")
        assert p.cached_path is None

    def test_local_only_skips_missing_files(self, source, mock_db):
        # With local_only=True (default), photos without local files are excluded
        mock_db.photos.return_value[0].path = "/nonexistent/path.jpg"
        photos = source.list_photos(local_only=True)
        ids = [p.id for p in photos]
        assert "UUID-001" not in ids

    def test_cached_path_none_when_path_is_none(self, source, mock_db):
        mock_db.photos.return_value[0].path = None
        photos = source.list_photos(local_only=False)
        p = next(ph for ph in photos if ph.id == "UUID-001")
        assert p.cached_path is None

    def test_local_only_true_skips_none_path(self, source, mock_db):
        mock_db.photos.return_value[0].path = None
        photos = source.list_photos(local_only=True)
        ids = [p.id for p in photos]
        assert "UUID-001" not in ids

    def test_heic_photo_included(self, source, mock_db, tmp_path):
        # Give UUID-002 a real file so local_only=True includes it
        fake_file = tmp_path / "party.heic"
        fake_file.write_bytes(b"HEIC")
        mock_db.photos.return_value[1].path = str(fake_file)
        photos = source.list_photos()
        p = next((ph for ph in photos if ph.id == "UUID-002"), None)
        assert p is not None
        assert p.metadata["uti"] == "public.heic"


# ---------------------------------------------------------------------------
# Unit tests — get_photo_data
# ---------------------------------------------------------------------------

class TestGetPhotoData:
    def test_reads_from_cached_path(self, source, tmp_path):
        fake_file = tmp_path / "photo.jpg"
        fake_file.write_bytes(b"\xff\xd8\xff\xe0JPEG")
        photo = Photo("UUID-001", "apple")
        photo.cached_path = fake_file
        data = source.get_photo_data(photo)
        assert data == b"\xff\xd8\xff\xe0JPEG"

    def test_exports_when_no_cached_path(self, source, mock_db, tmp_path):
        exported_file = tmp_path / "exported.jpg"
        exported_file.write_bytes(b"EXPORTED")

        mock_photo_info = MagicMock()
        mock_photo_info.export.return_value = [str(exported_file)]
        mock_db.get_photo = MagicMock(return_value=mock_photo_info)

        photo = Photo("UUID-001", "apple")
        photo.cached_path = None

        with patch("osxphotos.PhotosDB"):
            data = source.get_photo_data(photo)

        assert data == b"EXPORTED"

    def test_raises_when_photo_not_found(self, source, mock_db):
        mock_db.get_photo = MagicMock(return_value=None)
        photo = Photo("MISSING", "apple")
        photo.cached_path = None
        with pytest.raises(FileNotFoundError):
            source.get_photo_data(photo)

    def test_raises_when_export_fails(self, source, mock_db):
        mock_photo_info = MagicMock()
        mock_photo_info.export.return_value = []  # nothing exported
        mock_db.get_photo = MagicMock(return_value=mock_photo_info)

        photo = Photo("UUID-001", "apple")
        photo.cached_path = None
        with pytest.raises(FileNotFoundError):
            source.get_photo_data(photo)


# ---------------------------------------------------------------------------
# Unit tests — get_metadata
# ---------------------------------------------------------------------------

class TestGetMetadata:
    def test_returns_copy_of_metadata(self, source):
        photos = source.list_photos(local_only=False)
        p = photos[0]
        meta = source.get_metadata(p)
        assert meta == p.metadata
        # Must be a copy
        meta["injected"] = True
        assert "injected" not in p.metadata


# ---------------------------------------------------------------------------
# Unit tests — read-only write operations
# ---------------------------------------------------------------------------

class TestReadOnlyOperations:
    def test_tag_photo_returns_false(self, source):
        photo = Photo("UUID-001", "apple")
        assert source.tag_photo(photo, ["tag1"]) is False

    def test_create_album_returns_false(self, source):
        assert source.create_album("New Album", []) is False

    def test_set_favorite_returns_false(self, source):
        photo = Photo("UUID-001", "apple")
        assert source.set_favorite(photo, True) is False


# ---------------------------------------------------------------------------
# Unit tests — list_people
# ---------------------------------------------------------------------------

class TestListPeople:
    def test_returns_all_people(self, source, mock_db):
        people = source.list_people()
        assert len(people) == 2

    def test_people_have_id_and_name(self, source):
        people = source.list_people()
        for person in people:
            assert "id" in person
            assert "name" in person
            assert "photo_count" in person
            assert isinstance(person["name"], str)
            assert isinstance(person["photo_count"], int)

    def test_people_names_match_db(self, source):
        people = source.list_people()
        names = {p["name"] for p in people}
        assert names == {"Alice", "Bob"}

    def test_id_matches_name(self, source):
        """id should equal name (used as lookup key for list_photos_by_person)."""
        for person in source.list_people():
            assert person["id"] == person["name"]

    def test_empty_library_has_no_people(self, source, mock_db):
        mock_db.person_info = []
        assert source.list_people() == []

    def test_unknown_people_are_excluded(self, source, mock_db):
        """_UNKNOWN_ faces should not appear in the people list."""
        unknown = MagicMock()
        unknown.name = "_UNKNOWN_"
        unknown.facecount = 100
        unknown.favorite = False
        unknown.keyphoto = None
        mock_db.person_info = mock_db.person_info + [unknown]
        names = {p["name"] for p in source.list_people()}
        assert "_UNKNOWN_" not in names

    def test_people_sorted_alphabetically(self, source):
        people = source.list_people()
        names = [p["name"] for p in people]
        assert names == sorted(names, key=str.lower)


# ---------------------------------------------------------------------------
# Unit tests — list_photos_by_person
# ---------------------------------------------------------------------------

class TestListPhotosByPerson:
    def test_calls_db_with_person_filter(self, source, mock_db):
        mock_db.photos.return_value = [mock_db.photos.return_value[0]]  # only photo1
        source.list_photos_by_person("Alice")
        mock_db.photos.assert_called_with(persons=["Alice"])

    def test_excludes_videos(self, source, mock_db):
        video = _make_osxphoto(uuid="VID", isphoto=False, ismovie=True)
        mock_db.photos.return_value = [video]
        photos = source.list_photos_by_person("Alice")
        assert len(photos) == 0

    def test_limit_applied(self, source, mock_db):
        photo1 = _make_osxphoto(uuid="P1")
        photo2 = _make_osxphoto(uuid="P2")
        photo3 = _make_osxphoto(uuid="P3")
        mock_db.photos.return_value = [photo1, photo2, photo3]
        photos = source.list_photos_by_person("Alice", limit=2, local_only=False)
        assert len(photos) == 2

    def test_returned_photos_have_source_apple(self, source, mock_db):
        mock_db.photos.return_value = [mock_db.photos.return_value[0]]
        photos = source.list_photos_by_person("Alice")
        assert all(p.source == "apple" for p in photos)


# ---------------------------------------------------------------------------
# Integration tests — hit the real Photos library
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="Apple Photos integration requires macOS"
)
class TestIntegration:
    """
    These tests connect to the real Photos library.
    They are slower and require Photos.app to have some content.
    """

    @pytest.fixture(scope="class")
    def real_source(self):
        return ApplePhotoSource()

    def test_library_opens(self, real_source):
        assert real_source.photosdb is not None

    def test_list_photos_returns_results(self, real_source):
        photos = real_source.list_photos(limit=5)
        assert len(photos) > 0

    def test_all_photos_have_required_fields(self, real_source):
        photos = real_source.list_photos(limit=20)
        required_fields = {"filename", "date", "albums", "persons",
                           "favorite", "hidden", "media_type", "uti"}
        for p in photos:
            missing = required_fields - p.metadata.keys()
            assert not missing, f"Photo {p.id} missing fields: {missing}"

    def test_source_is_apple(self, real_source):
        photos = real_source.list_photos(limit=5)
        assert all(p.source == "apple" for p in photos)

    def test_limit_respected(self, real_source):
        photos = real_source.list_photos(limit=3)
        assert len(photos) <= 3

    def test_media_type_image_excludes_videos(self, real_source):
        photos = real_source.list_photos(limit=50, media_type='image')
        assert all(p.metadata["media_type"] == "image" for p in photos)

    def test_list_people_returns_list_of_dicts(self, real_source):
        people = real_source.list_people()
        assert isinstance(people, list)
        for person in people:
            assert "id" in person
            assert "name" in person

    def test_get_metadata_returns_dict(self, real_source):
        photos = real_source.list_photos(limit=1)
        assert photos
        meta = real_source.get_metadata(photos[0])
        assert isinstance(meta, dict)

    def test_get_photo_data_for_available_photo(self, real_source):
        """Test reading bytes for a photo that has a local path."""
        photos = real_source.list_photos(limit=50)
        available = [p for p in photos if p.cached_path is not None]
        if not available:
            pytest.skip("No locally available photos found")
        data = real_source.get_photo_data(available[0])
        assert len(data) > 0

    def test_list_photos_by_person_for_known_person(self, real_source):
        people = real_source.list_people()
        if not people:
            pytest.skip("No recognized people in library")
        person_name = people[0]["name"]
        photos = real_source.list_photos_by_person(person_name, limit=5)
        assert isinstance(photos, list)
        # All results should be photos (not movies)
        assert all(p.source == "apple" for p in photos)

    def test_album_filter(self, real_source):
        """list_photos(album=X) should only return photos from that album."""
        import osxphotos
        db = real_source.photosdb
        albums = [a.title for a in db.album_info]
        if not albums:
            pytest.skip("No albums in library")
        album_name = albums[0]
        photos = real_source.list_photos(album=album_name, limit=10)
        for p in photos:
            assert album_name in p.metadata["albums"], \
                f"Photo {p.id} not in album '{album_name}'"

    def test_write_ops_return_false(self, real_source):
        photos = real_source.list_photos(limit=1)
        assert photos
        p = photos[0]
        assert real_source.tag_photo(p, ["x"]) is False
        assert real_source.create_album("TestAlbum", [p]) is False
        assert real_source.set_favorite(p, True) is False

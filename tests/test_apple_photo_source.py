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
    pytest tests/test_apple_photo_source.py -m integration -v --apple-limit=50
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
    path_derivatives=None,   # list of derivative file paths
    ismissing=False,
    score_overall=None,
    score_curation=None,
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
    p.path_derivatives = path_derivatives or []
    p.ismissing = ismissing
    if score_overall is not None or score_curation is not None:
        score = MagicMock()
        score.overall = score_overall
        score.curation = score_curation
        p.score = score
    else:
        p.score = None
    p.duplicates = []
    p.burst = False
    p.burst_key_photo = False
    return p


@pytest.fixture
def mock_db(tmp_path):
    """A minimal mock PhotosDB with two photos and two people.

    Photos are given real on-disk paths so the iCloud-only prefilter does not
    skip them in local_only=False tests.  Individual tests may override .path
    to simulate missing/iCloud-only photos.
    """
    # Create real files so Path.exists() returns True
    file1 = tmp_path / "beach.jpg"
    file1.write_bytes(b"JPEG1")
    file2 = tmp_path / "party.heic"
    file2.write_bytes(b"HEIC2")
    file3 = tmp_path / "clip.mov"
    file3.write_bytes(b"MOV3")

    photo1 = _make_osxphoto(
        uuid="UUID-001",
        original_filename="beach.jpg",
        path=str(file1),
        albums=["Summer 2023"],
        persons=["Alice"],
        keywords=["vacation", "beach"],
        favorite=True,
    )
    photo2 = _make_osxphoto(
        uuid="UUID-002",
        original_filename="party.heic",
        path=str(file2),
        albums=["Birthday"],
        persons=["Bob", "Alice"],
        uti="public.heic",
    )
    video1 = _make_osxphoto(
        uuid="UUID-003",
        original_filename="clip.mov",
        path=str(file3),
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

    def test_cached_path_none_when_file_missing_but_has_derivative(self, source, mock_db, tmp_path):
        """With local_only=False, an iCloud-only photo with a derivative is included
        but cached_path is None (derivative is used for hashing, not as cached_path)."""
        deriv = tmp_path / "thumb.jpg"
        deriv.write_bytes(b"THUMB")
        mock_db.photos.return_value[0].path = "/nonexistent/path.jpg"
        mock_db.photos.return_value[0].path_derivatives = [str(deriv)]
        photos = source.list_photos(local_only=False)
        p = next(ph for ph in photos if ph.id == "UUID-001")
        assert p.cached_path is None

    def test_local_only_skips_missing_files(self, source, mock_db):
        # With local_only=True (default), photos without local files are excluded
        mock_db.photos.return_value[0].path = "/nonexistent/path.jpg"
        photos = source.list_photos(local_only=True)
        ids = [p.id for p in photos]
        assert "UUID-001" not in ids

    def test_cached_path_none_when_path_is_none_but_has_derivative(self, source, mock_db, tmp_path):
        """Photo with path=None is included if it has a derivative; cached_path stays None."""
        deriv = tmp_path / "thumb.jpg"
        deriv.write_bytes(b"THUMB")
        mock_db.photos.return_value[0].path = None
        mock_db.photos.return_value[0].path_derivatives = [str(deriv)]
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

    def test_reads_from_path_when_no_cached_path(self, source, mock_db, tmp_path):
        """When cached_path is None but p.path exists on disk, read from it."""
        real_file = tmp_path / "original.jpg"
        real_file.write_bytes(b"ORIGINAL_DATA")

        mock_photo_info = MagicMock()
        mock_photo_info.path = str(real_file)
        mock_photo_info.path_derivatives = []
        mock_db.get_photo = MagicMock(return_value=mock_photo_info)

        photo = Photo("UUID-001", "apple")
        photo.cached_path = None
        data = source.get_photo_data(photo)
        assert data == b"ORIGINAL_DATA"

    def test_raises_when_photo_not_found(self, source, mock_db):
        mock_db.get_photo = MagicMock(return_value=None)
        photo = Photo("MISSING", "apple")
        photo.cached_path = None
        with pytest.raises(FileNotFoundError):
            source.get_photo_data(photo)

    def test_raises_when_no_path_and_no_derivatives(self, source, mock_db):
        """Raises FileNotFoundError when photo has no local file and no derivatives."""
        mock_photo_info = MagicMock()
        mock_photo_info.path = None
        mock_photo_info.path_derivatives = []
        mock_db.get_photo = MagicMock(return_value=mock_photo_info)

        photo = Photo("UUID-001", "apple")
        photo.cached_path = None
        with pytest.raises(FileNotFoundError):
            source.get_photo_data(photo)

    def test_uses_derivative_when_no_cached_path(self, source, mock_db, tmp_path):
        """For iCloud-only photos, falls back to path_derivatives thumbnail."""
        deriv = tmp_path / "thumb.jpg"
        deriv.write_bytes(b"THUMBNAIL_DATA")

        mock_info = MagicMock()
        mock_info.path = None
        mock_info.path_derivatives = [str(deriv)]
        mock_db.get_photo = MagicMock(return_value=mock_info)

        photo = Photo("UUID-001", "apple")
        photo.cached_path = None
        data = source.get_photo_data(photo)
        assert data == b"THUMBNAIL_DATA"

    def test_raises_when_no_local_data_at_all(self, source, mock_db):
        """Photo with no path and no derivatives raises FileNotFoundError."""
        mock_info = MagicMock()
        mock_info.path = None
        mock_info.path_derivatives = []
        mock_db.get_photo = MagicMock(return_value=mock_info)

        photo = Photo("UUID-GHOST", "apple")
        photo.cached_path = None
        with pytest.raises(FileNotFoundError, match="iCloud-only"):
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
# Unit tests — write-back operations via AppleScript
# ---------------------------------------------------------------------------

class TestAppleScriptActions:
    """Write-back actions use apple_actions (AppleScript). Test with mocked subprocess."""

    def _make_photo(self, uid="UUID-001"):
        p = Photo(uid, "apple")
        p.metadata = {}
        return p

    def test_add_keyword_calls_applescript(self, source):
        photo = self._make_photo()
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            result = source.add_keyword(photo, "best-photo")
        assert result is True
        script = mock_run.call_args[0][0]
        assert "best-photo" in script
        assert "UUID-001" in script

    def test_add_keyword_returns_false_on_failure(self, source):
        photo = self._make_photo()
        with patch("src.apple_actions._run", return_value=(False, "error")):
            result = source.add_keyword(photo, "best-photo")
        assert result is False

    def test_set_favorite_calls_applescript(self, source):
        photo = self._make_photo()
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            result = source.set_favorite(photo, True)
        assert result is True
        script = mock_run.call_args[0][0]
        assert "favorite" in script
        assert "UUID-001" in script
        assert "true" in script

    def test_set_favorite_false_calls_applescript(self, source):
        photo = self._make_photo()
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            source.set_favorite(photo, False)
        script = mock_run.call_args[0][0]
        assert "false" in script

    def test_set_archived_adds_archive_keyword(self, source):
        photo = self._make_photo()
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            result = source.set_archived(photo, True)
        assert result is True
        script = mock_run.call_args[0][0]
        assert "archive" in script

    def test_set_archived_false_removes_archive_keyword(self, source):
        photo = self._make_photo()
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            result = source.set_archived(photo, False)
        assert result is True

    def test_create_album_calls_applescript(self, source):
        photos = [self._make_photo("A"), self._make_photo("B")]
        with patch("src.apple_actions._run", return_value=(True, "")):
            result = source.create_album("Test Album", photos)
        assert result is True

    def test_tag_photo_adds_each_tag_as_keyword(self, source):
        photo = self._make_photo()
        calls = []
        with patch("src.apple_actions._run", side_effect=lambda s: calls.append(s) or (True, "")):
            source.tag_photo(photo, ["best-photo", "archive"])
        # One AppleScript call per tag (add_keyword called for each)
        assert len(calls) == 2


# ---------------------------------------------------------------------------
# Unit tests — iCloud pre-filter
# ---------------------------------------------------------------------------

class TestICloudPrefilter:
    """Photos with no local file and no derivative are silently skipped at list time."""

    def test_icloud_only_with_no_derivative_is_skipped(self, source, mock_db):
        """Photo has no path and no derivatives -> skipped, count logged."""
        p = _make_osxphoto(uuid="ICLOUD-001", path=None, path_derivatives=[])
        p.ismissing = True
        # Replace db contents with just this iCloud-only photo
        mock_db.photos.return_value = [p]
        photos = source.list_photos(local_only=False)
        ids = [ph.id for ph in photos]
        assert "ICLOUD-001" not in ids

    def test_icloud_only_with_derivative_is_included(self, source, mock_db, tmp_path):
        """iCloud photo that has a cached thumbnail IS included."""
        deriv = tmp_path / "thumb.jpg"
        deriv.write_bytes(b"THUMB")
        p = _make_osxphoto(uuid="ICLOUD-002", path=None, path_derivatives=[str(deriv)])
        p.ismissing = True
        mock_db.photos.return_value = [p]
        photos = source.list_photos(local_only=False)
        ids = [ph.id for ph in photos]
        assert "ICLOUD-002" in ids

    def test_skipped_count_logged(self, source, mock_db, caplog):
        """A single WARNING with the skip count is emitted, not one per photo."""
        import logging
        p = _make_osxphoto(uuid="ICLOUD-003", path=None, path_derivatives=[])
        p.ismissing = True
        mock_db.photos.return_value = [p]
        with caplog.at_level(logging.WARNING):
            source.list_photos(local_only=False)
        # Should have exactly one warning mentioning the skip count, not one per photo
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "1" in warnings[0].message

    def test_local_only_still_skips_missing(self, source, mock_db, tmp_path):
        """local_only=True skips iCloud photos regardless of derivatives."""
        deriv = tmp_path / "thumb.jpg"
        deriv.write_bytes(b"THUMB")
        p = _make_osxphoto(uuid="ICLOUD-004", path=None, path_derivatives=[str(deriv)])
        p.ismissing = True
        mock_db.photos.return_value = [p]
        photos = source.list_photos(local_only=True)
        assert len(photos) == 0


# ---------------------------------------------------------------------------
# Unit tests — date range filter
# ---------------------------------------------------------------------------

class TestDateRangeFilter:
    """list_photos respects start_date and end_date filters."""

    def _make_dated_db(self, mock_db, tmp_path):
        """Return (early_photo, late_photo) with distinct dates and real on-disk paths."""
        early_file = tmp_path / "early.jpg"
        early_file.write_bytes(b"EARLY")
        late_file = tmp_path / "late.jpg"
        late_file.write_bytes(b"LATE")
        early = _make_osxphoto(uuid="EARLY", path=str(early_file),
                               date=datetime(2020, 1, 15, tzinfo=timezone.utc))
        late  = _make_osxphoto(uuid="LATE",  path=str(late_file),
                               date=datetime(2024, 6, 20, tzinfo=timezone.utc))
        mock_db.photos.return_value = [early, late]
        return early, late

    def test_start_date_excludes_older(self, source, mock_db, tmp_path):
        self._make_dated_db(mock_db, tmp_path)
        cutoff = datetime(2023, 1, 1, tzinfo=timezone.utc)
        photos = source.list_photos(local_only=False, start_date=cutoff)
        ids = [p.id for p in photos]
        assert "EARLY" not in ids
        assert "LATE" in ids

    def test_end_date_excludes_newer(self, source, mock_db, tmp_path):
        self._make_dated_db(mock_db, tmp_path)
        cutoff = datetime(2022, 12, 31, tzinfo=timezone.utc)
        photos = source.list_photos(local_only=False, end_date=cutoff)
        ids = [p.id for p in photos]
        assert "LATE" not in ids
        assert "EARLY" in ids

    def test_start_and_end_date_range(self, source, mock_db, tmp_path):
        self._make_dated_db(mock_db, tmp_path)
        start = datetime(2019, 1, 1, tzinfo=timezone.utc)
        end   = datetime(2021, 1, 1, tzinfo=timezone.utc)
        photos = source.list_photos(local_only=False, start_date=start, end_date=end)
        ids = [p.id for p in photos]
        assert "EARLY" in ids
        assert "LATE" not in ids

    def test_no_date_filter_includes_all(self, source, mock_db, tmp_path):
        self._make_dated_db(mock_db, tmp_path)
        photos = source.list_photos(local_only=False)
        assert len(photos) == 2

    def test_photo_with_no_date_included_when_filtering(self, source, mock_db, tmp_path):
        """Photos with no date are included even when a range is set (no date = unknown)."""
        nodate_file = tmp_path / "nodate.jpg"
        nodate_file.write_bytes(b"NODATE")
        no_date = _make_osxphoto(uuid="NODATE", path=str(nodate_file))
        no_date.date = None
        mock_db.photos.return_value = [no_date]
        cutoff = datetime(2023, 1, 1, tzinfo=timezone.utc)
        photos = source.list_photos(local_only=False, start_date=cutoff)
        ids = [p.id for p in photos]
        assert "NODATE" in ids


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
    Hit the real Photos library — read-only.
    Write-back tests mock osascript so nothing is modified.

    Run with:
        pytest tests/test_apple_photo_source.py -m integration -v
        pytest tests/test_apple_photo_source.py -m integration -v --apple-limit=50
    """

    @pytest.fixture(scope="class")
    def real_source(self):
        return ApplePhotoSource()

    @pytest.fixture(scope="class")
    def photos(self, real_source, request):
        limit = request.config.getoption("--apple-limit", default=100)
        return real_source.list_photos(limit=limit, local_only=False)

    # --- library basics ---

    def test_library_opens(self, real_source):
        assert real_source.photosdb is not None

    def test_list_photos_returns_results(self, real_source):
        photos = real_source.list_photos(limit=5)
        assert len(photos) > 0

    def test_photo_count_respects_limit(self, photos, apple_limit):
        assert len(photos) <= apple_limit

    def test_all_photos_have_required_fields(self, photos):
        required = {"filename", "date", "albums", "persons",
                    "favorite", "hidden", "media_type", "uti"}
        for p in photos:
            missing = required - p.metadata.keys()
            assert not missing, f"Photo {p.id} missing: {missing}"

    def test_all_photos_have_apple_fields(self, photos):
        apple_fields = {"apple_score", "apple_curation",
                        "duplicate_group", "is_burst", "burst_key"}
        for p in photos:
            missing = apple_fields - p.metadata.keys()
            assert not missing, f"Photo {p.id} missing Apple fields: {missing}"

    def test_source_is_apple(self, photos):
        assert all(p.source == "apple" for p in photos)

    def test_media_type_image_excludes_videos(self, real_source):
        photos = real_source.list_photos(limit=50, media_type='image')
        assert all(p.metadata["media_type"] == "image" for p in photos)

    def test_metadata_returns_copy(self, real_source):
        photos = real_source.list_photos(limit=1)
        assert photos
        meta = real_source.get_metadata(photos[0])
        meta["injected"] = True
        assert "injected" not in photos[0].metadata

    # --- local_only ---

    def test_local_only_photos_have_cached_path(self, real_source, apple_limit):
        photos = real_source.list_photos(limit=apple_limit, local_only=True)
        for p in photos:
            assert p.cached_path is not None, f"{p.id} has no cached_path"
            assert p.cached_path.exists(), f"{p.cached_path} does not exist"

    def test_include_icloud_may_add_photos(self, real_source, apple_limit):
        local = real_source.list_photos(limit=apple_limit, local_only=True)
        all_  = real_source.list_photos(limit=apple_limit, local_only=False)
        # With iCloud enabled, count is >= local-only count (up to limit)
        assert len(all_) >= len(local)

    # --- date range ---

    def test_start_date_reduces_results(self, real_source, apple_limit):
        from datetime import datetime, timezone
        all_photos = real_source.list_photos(limit=apple_limit, local_only=False)
        if not all_photos:
            pytest.skip("No photos in library")
        dates = [p.metadata.get("date") for p in all_photos if p.metadata.get("date")]
        if not dates:
            pytest.skip("No dated photos found")
        dates_sorted = sorted(dates)
        midpoint_str = dates_sorted[len(dates_sorted) // 2][:10]
        midpoint = datetime.strptime(midpoint_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        filtered = real_source.list_photos(limit=apple_limit, local_only=False,
                                            start_date=midpoint)
        assert len(filtered) <= len(all_photos)

    def test_end_date_reduces_results(self, real_source, apple_limit):
        from datetime import datetime, timezone
        all_photos = real_source.list_photos(limit=apple_limit, local_only=False)
        if not all_photos:
            pytest.skip("No photos in library")
        dates = sorted(p.metadata.get("date","") for p in all_photos if p.metadata.get("date"))
        if not dates:
            pytest.skip("No dated photos found")
        midpoint_str = dates[len(dates) // 2][:10]
        midpoint = datetime.strptime(midpoint_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        filtered = real_source.list_photos(limit=apple_limit, local_only=False,
                                            end_date=midpoint)
        assert len(filtered) <= len(all_photos)

    # --- people ---

    def test_list_people_returns_list_of_dicts(self, real_source):
        people = real_source.list_people()
        assert isinstance(people, list)
        for person in people:
            assert "id" in person
            assert "name" in person
            assert "photo_count" in person
            assert person["id"] == person["name"]

    def test_people_sorted_alphabetically(self, real_source):
        people = real_source.list_people()
        names = [p["name"] for p in people]
        assert names == sorted(names, key=str.lower)

    def test_no_unknown_people(self, real_source):
        people = real_source.list_people()
        assert all(p["name"] != "_UNKNOWN_" for p in people)

    def test_list_photos_by_person(self, real_source):
        people = real_source.list_people()
        if not people:
            pytest.skip("No recognized people in library")
        name = people[0]["name"]
        photos = real_source.list_photos_by_person(name, limit=10)
        assert isinstance(photos, list)
        assert all(p.source == "apple" for p in photos)

    # --- get_photo_data (read-only) ---

    def test_get_photo_data_for_local_photo(self, real_source):
        photos = real_source.list_photos(limit=50, local_only=True)
        if not photos:
            pytest.skip("No local photos")
        data = real_source.get_photo_data(photos[0])
        assert len(data) > 100  # real image file

    def test_get_photo_data_for_derivative(self, real_source, apple_limit):
        """iCloud-only photos with a cached thumbnail can be read via derivative."""
        all_photos = real_source.list_photos(limit=apple_limit, local_only=False)
        icloud = [p for p in all_photos if p.cached_path is None]
        if not icloud:
            pytest.skip("No iCloud-only photos (all fully local)")
        # Try up to 5; some may have no derivative either
        for p in icloud[:5]:
            try:
                data = real_source.get_photo_data(p)
                assert len(data) > 0
                return
            except FileNotFoundError:
                continue
        pytest.skip("No iCloud photos with cached thumbnails found")

    # --- album filter ---

    def test_album_filter(self, real_source):
        albums = [a.title for a in real_source.photosdb.album_info]
        if not albums:
            pytest.skip("No albums in library")
        name = albums[0]
        photos = real_source.list_photos(album=name, limit=10)
        for p in photos:
            assert name in p.metadata["albums"]

    # --- native duplicates ---

    def test_duplicate_group_field_present(self, photos):
        """All photos have a duplicate_group field (may be None)."""
        for p in photos:
            assert "duplicate_group" in p.metadata

    def test_photos_with_duplicates_have_uuid(self, photos):
        """If Apple detected duplicates, duplicate_group is a UUID string."""
        dups = [p for p in photos if p.metadata.get("duplicate_group")]
        for p in dups:
            uid = p.metadata["duplicate_group"]
            assert isinstance(uid, str)
            assert len(uid) > 0

    # --- write-back tests (osascript MOCKED — non-destructive) ---

    def test_set_favorite_mocked(self, real_source):
        """set_favorite calls osascript with correct UUID (no actual write)."""
        photos = real_source.list_photos(limit=1, local_only=True)
        if not photos:
            pytest.skip("No local photos")
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            result = real_source.set_favorite(photos[0], True)
        assert result is True
        script = mock_run.call_args[0][0]
        assert photos[0].id in script
        assert "favorite" in script

    def test_add_keyword_mocked(self, real_source):
        """add_keyword calls osascript with correct UUID and keyword (no actual write)."""
        photos = real_source.list_photos(limit=1, local_only=True)
        if not photos:
            pytest.skip("No local photos")
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            result = real_source.add_keyword(photos[0], "best-photo")
        assert result is True
        script = mock_run.call_args[0][0]
        assert photos[0].id in script
        assert "best-photo" in script

    def test_set_archived_mocked(self, real_source):
        """set_archived adds 'archive' keyword via osascript (no actual write)."""
        photos = real_source.list_photos(limit=1, local_only=True)
        if not photos:
            pytest.skip("No local photos")
        with patch("src.apple_actions._run", return_value=(True, "")) as mock_run:
            result = real_source.set_archived(photos[0], True)
        assert result is True
        script = mock_run.call_args[0][0]
        assert "archive" in script

    def test_create_album_mocked(self, real_source):
        """create_album calls osascript with photoOrganizer folder (no actual write)."""
        photos = real_source.list_photos(limit=2, local_only=True)
        if not photos:
            pytest.skip("No local photos")
        scripts_called = []
        with patch("src.apple_actions._run",
                   side_effect=lambda s: scripts_called.append(s) or (True, "")):
            result = real_source.create_album("Test-Noop-Album", photos)
        assert result is True
        combined = "\n".join(scripts_called)
        assert "photoOrganizer" in combined

    def test_tag_photo_mocked(self, real_source):
        """tag_photo adds each tag as a keyword (no actual write)."""
        photos = real_source.list_photos(limit=1, local_only=True)
        if not photos:
            pytest.skip("No local photos")
        calls = []
        with patch("src.apple_actions._run",
                   side_effect=lambda s: calls.append(s) or (True, "")):
            real_source.tag_photo(photos[0], ["best-photo", "archive"])
        assert len(calls) == 2

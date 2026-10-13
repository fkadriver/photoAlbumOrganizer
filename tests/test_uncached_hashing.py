#!/usr/bin/env python3
"""Unit tests for the uncached-fetch path used during library-wide hashing.

Found live: hashing a ~62K-photo library via the normal cached
get_photo_data() (through an eager bulk prefetch_photos() call) grew the
local disk cache to ~18GB — roughly the size of the whole library — to
support a one-time hash computation per photo, when only the small subset
that ends up in an actual group (183 of 62,297 photos in that run) is ever
looked at again. get_photo_data_uncached() fetches without touching the
cache; compute_hash() prefers it when the source offers one."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from photo_sources import ImmichPhotoSource, Photo  # noqa: E402
from grouping import compute_hash  # noqa: E402


def _make_immich_source(use_thumbnails=True):
    source = ImmichPhotoSource.__new__(ImmichPhotoSource)
    source.client = MagicMock()
    source.cache = MagicMock()
    source.use_thumbnails = use_thumbnails
    return source


class TestGetPhotoDataUncached:
    def test_does_not_touch_the_cache(self):
        source = _make_immich_source()
        source.client.get_asset_thumbnail.return_value = b"thumbnail-bytes"
        photo = Photo(photo_id="p1", source="immich", metadata={"asset_id": "p1"})

        data = source.get_photo_data_uncached(photo)

        assert data == b"thumbnail-bytes"
        source.cache.cache_photo.assert_not_called()
        assert photo.cached_path is None

    def test_uses_thumbnail_when_use_thumbnails_true(self):
        source = _make_immich_source(use_thumbnails=True)
        source.client.get_asset_thumbnail.return_value = b"x"
        photo = Photo(photo_id="p1", source="immich", metadata={"asset_id": "p1"})

        source.get_photo_data_uncached(photo)

        source.client.get_asset_thumbnail.assert_called_once_with("p1", size="preview")
        source.client.download_asset.assert_not_called()

    def test_uses_full_download_when_use_thumbnails_false(self):
        source = _make_immich_source(use_thumbnails=False)
        source.client.download_asset.return_value = b"x"
        photo = Photo(photo_id="p1", source="immich", metadata={"asset_id": "p1"})

        source.get_photo_data_uncached(photo)

        source.client.download_asset.assert_called_once_with("p1")
        source.client.get_asset_thumbnail.assert_not_called()

    def test_raises_on_empty_response(self):
        source = _make_immich_source()
        source.client.get_asset_thumbnail.return_value = None
        photo = Photo(photo_id="p1", source="immich", metadata={"asset_id": "p1"})

        try:
            source.get_photo_data_uncached(photo)
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestComputeHashPrefersUncachedFetch:
    def test_uses_uncached_method_when_source_offers_one(self, monkeypatch):
        source = _make_immich_source()
        source.client.get_asset_thumbnail.return_value = _tiny_jpeg_bytes()
        photo = Photo(photo_id="p1", source="immich", metadata={"asset_id": "p1"})

        result = compute_hash(photo, source)

        assert result is not None
        source.cache.cache_photo.assert_not_called()
        source.client.get_asset_thumbnail.assert_called_once()

    def test_falls_back_to_get_photo_data_when_uncached_unavailable(self):
        # A source with no get_photo_data_uncached at all (e.g. Local/Apple).
        class PlainSource:
            def get_photo_data(self, photo):
                return _tiny_jpeg_bytes()

        photo = Photo(photo_id="p1", source="local", metadata={})
        result = compute_hash(photo, PlainSource())

        assert result is not None

    def test_still_prefers_existing_cached_path_over_either_fetch(self, tmp_path):
        source = _make_immich_source()
        cached_file = tmp_path / "cached.jpg"
        cached_file.write_bytes(_tiny_jpeg_bytes())
        photo = Photo(photo_id="p1", source="immich", metadata={"asset_id": "p1"})
        photo.cached_path = cached_file

        result = compute_hash(photo, source)

        assert result is not None
        source.client.get_asset_thumbnail.assert_not_called()
        source.cache.cache_photo.assert_not_called()


def _tiny_jpeg_bytes() -> bytes:
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(255, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()

#!/usr/bin/env python3
"""Unit tests for PhotoCache's incremental size tracking and batched
metadata saves.

Found live: with the default 5GB cache against a ~15GB batch of prefetched
thumbnails, cache_photo() was recomputing cache size via a full directory
walk (_get_cache_size()) AND rewriting the entire (growing) metadata JSON
file on every single call — turning a bulk prefetch of tens of thousands
of photos into a single-threaded, worse-than-O(n^2) pass with zero log
output until it finished."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from photo_sources import PhotoCache  # noqa: E402


def _make_cache(tmp_path, max_size_mb=5000):
    return PhotoCache(str(tmp_path / "cache"), max_size_mb=max_size_mb)


class TestIncrementalSizeTracking:
    def test_does_not_rescan_directory_on_every_write(self, tmp_path):
        cache = _make_cache(tmp_path)
        with patch.object(cache, '_get_cache_size', wraps=cache._get_cache_size) as spy:
            for i in range(20):
                cache.cache_photo(f"photo-{i}", b"x" * 1000)
            # Only the one call made during __init__ (before the patch) should
            # have happened — cache_photo()/_evict_old_entries() must use the
            # incrementally-tracked self._current_size instead.
            assert spy.call_count == 0

    def test_current_size_tracks_writes(self, tmp_path):
        cache = _make_cache(tmp_path)
        start = cache._current_size
        cache.cache_photo("a", b"x" * 1000)
        cache.cache_photo("b", b"y" * 2000)
        assert cache._current_size == start + 3000

    def test_current_size_tracks_eviction(self, tmp_path):
        # Tiny cache: writing a second photo must evict the first.
        cache = _make_cache(tmp_path, max_size_mb=0)
        cache.max_size = 1500  # bytes, small enough to force eviction
        cache.cache_photo("a", b"x" * 1000)
        assert cache._current_size == 1000
        cache.cache_photo("b", b"y" * 1000)
        # "a" must have been evicted to make room; size reflects only "b".
        assert cache._current_size == 1000
        assert cache.get_cached_photo("a") is None
        assert cache.get_cached_photo("b") is not None


class TestBatchedMetadataSave:
    def test_does_not_save_metadata_on_every_call(self, tmp_path):
        cache = _make_cache(tmp_path)
        with patch.object(cache, '_save_metadata', wraps=cache._save_metadata) as spy:
            for i in range(cache._METADATA_SAVE_INTERVAL - 1):
                cache.cache_photo(f"photo-{i}", b"x")
            assert spy.call_count == 0

    def test_saves_metadata_at_interval(self, tmp_path):
        cache = _make_cache(tmp_path)
        with patch.object(cache, '_save_metadata', wraps=cache._save_metadata) as spy:
            for i in range(cache._METADATA_SAVE_INTERVAL):
                cache.cache_photo(f"photo-{i}", b"x")
            assert spy.call_count == 1

    def test_flush_saves_pending_writes(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.cache_photo("a", b"x")
        assert cache._dirty_writes == 1

        cache.flush()

        assert cache._dirty_writes == 0
        # Reload from disk to confirm it was actually persisted.
        cache2 = _make_cache(tmp_path)
        assert "photo_id" not in cache2.metadata  # sanity: top-level is keyed by safe_id
        assert any(v.get('photo_id') == 'a' for v in cache2.metadata.values())

    def test_flush_is_noop_when_nothing_pending(self, tmp_path):
        cache = _make_cache(tmp_path)
        with patch.object(cache, '_save_metadata', wraps=cache._save_metadata) as spy:
            cache.flush()
            assert spy.call_count == 0

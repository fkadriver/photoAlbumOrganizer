#!/usr/bin/env python3
"""Unit tests for _group_image_photo_data()'s time-window-indexed grouping.

This replaced a true O(n^2) all-pairs comparison — for a real ~62K-photo
library it was still running after the entire hash-computation phase
finished, with the first progress checkpoint (just 5% through the outer
loop) alone requiring ~189M comparisons. Since any pair further apart than
the time window fails the time check regardless of hash distance, indexing
dated photos by time and binary-searching each inner loop prunes those
guaranteed-failing comparisons without changing which pairs can match.
These tests exist to pin that equivalence down directly, not just trust it."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grouping import _group_image_photo_data  # noqa: E402


class FakeHash:
    """Minimal stand-in for imagehash.ImageHash: supports subtraction to a
    Hamming-like distance, which is all _group_image_photo_data needs."""
    def __init__(self, value):
        self.value = value

    def __sub__(self, other):
        return abs(self.value - other.value)


def _pd(hash_value, dt=None, name=None):
    return {'hash': FakeHash(hash_value), 'datetime': dt, 'name': name or str(hash_value)}


BASE = datetime(2024, 1, 1, 12, 0, 0)


class TestBasicGrouping:
    def test_similar_hashes_within_window_group_together(self):
        photo_data = [
            _pd(0, BASE),
            _pd(1, BASE + timedelta(seconds=10)),
            _pd(2, BASE + timedelta(seconds=20)),
        ]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_dissimilar_hashes_do_not_group(self):
        photo_data = [
            _pd(0, BASE),
            _pd(100, BASE + timedelta(seconds=10)),
        ]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert groups == []

    def test_groups_smaller_than_min_size_are_dropped(self):
        photo_data = [_pd(0, BASE), _pd(1, BASE + timedelta(seconds=10))]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=3)
        assert groups == []


class TestTimeWindowBoundary:
    def test_exactly_at_window_boundary_still_matches(self):
        photo_data = [_pd(0, BASE), _pd(0, BASE + timedelta(seconds=300))]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert len(groups) == 1

    def test_just_past_window_boundary_does_not_match(self):
        photo_data = [_pd(0, BASE), _pd(0, BASE + timedelta(seconds=301))]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert groups == []

    def test_similar_hash_but_far_apart_in_time_does_not_match(self):
        # Same scene photographed a year apart — must not be pruned into a
        # false match just because the binary search window is narrow.
        photo_data = [_pd(0, BASE), _pd(0, BASE + timedelta(days=365))]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert groups == []


class TestTimeWindowDisabled:
    def test_matches_by_hash_alone_regardless_of_time_distance(self):
        photo_data = [_pd(0, BASE), _pd(0, BASE + timedelta(days=365))]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=False, time_window=300,
                                          min_group_size=2)
        assert len(groups) == 1
        assert len(groups[0]) == 2


class TestUndatedPhotos:
    def test_undated_seed_matches_dated_partner_by_hash_alone(self):
        photo_data = [_pd(0, dt=None), _pd(0, BASE + timedelta(days=365))]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert len(groups) == 1

    def test_dated_seed_matches_undated_partner_by_hash_alone(self):
        # The seed (index 0) HAS a datetime; the candidate doesn't. This is
        # the case the time-window index can't prune by construction —
        # undated photos are always added as extra candidates.
        photo_data = [_pd(0, BASE), _pd(0, dt=None)]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert len(groups) == 1

    def test_two_undated_photos_match_by_hash_alone(self):
        photo_data = [_pd(0, dt=None), _pd(0, dt=None)]
        groups = _group_image_photo_data(photo_data, similarity_threshold=5,
                                          use_time_window=True, time_window=300,
                                          min_group_size=2)
        assert len(groups) == 1


def _brute_force_reference(photo_data, similarity_threshold, use_time_window, time_window, min_group_size):
    """The original O(n^2) algorithm, kept only as a test oracle."""
    groups = []
    used = set()
    for i, data1 in enumerate(photo_data):
        if i in used:
            continue
        group = [data1]
        used.add(i)
        for j, data2 in enumerate(photo_data[i + 1:], start=i + 1):
            if j in used:
                continue
            hash_diff = data1['hash'] - data2['hash']
            if hash_diff <= similarity_threshold:
                if use_time_window and data1['datetime'] and data2['datetime']:
                    time_diff = abs((data1['datetime'] - data2['datetime']).total_seconds())
                    if time_diff <= time_window:
                        group.append(data2)
                        used.add(j)
                elif not use_time_window:
                    group.append(data2)
                    used.add(j)
                elif not data1['datetime'] or not data2['datetime']:
                    group.append(data2)
                    used.add(j)
        if len(group) >= min_group_size:
            groups.append(group)
    return groups


class TestEquivalenceToBruteForce:
    """Randomized check that the indexed version produces exactly the same
    groupings as the original brute-force all-pairs comparison, across a
    mix of clustered timestamps, scattered timestamps, and undated photos."""

    def test_matches_brute_force_on_mixed_dataset(self):
        import random
        rng = random.Random(42)

        photo_data = []
        # A few genuine bursts: same-ish hash, clustered in time.
        for burst in range(5):
            base_hash = burst * 20
            burst_time = BASE + timedelta(days=burst * 3)
            for _ in range(rng.randint(2, 4)):
                photo_data.append(_pd(
                    base_hash + rng.randint(0, 2),
                    burst_time + timedelta(seconds=rng.randint(0, 60)),
                ))
        # Scattered singles with random hashes/times (mostly shouldn't group).
        for _ in range(30):
            photo_data.append(_pd(
                rng.randint(0, 200),
                BASE + timedelta(days=rng.randint(0, 400), seconds=rng.randint(0, 86400)),
            ))
        # A handful with no datetime at all.
        for _ in range(5):
            photo_data.append(_pd(rng.randint(0, 200), dt=None))

        rng.shuffle(photo_data)

        for use_time_window in (True, False):
            indexed = _group_image_photo_data(
                list(photo_data), similarity_threshold=5,
                use_time_window=use_time_window, time_window=300, min_group_size=2,
            )
            reference = _brute_force_reference(
                list(photo_data), similarity_threshold=5,
                use_time_window=use_time_window, time_window=300, min_group_size=2,
            )

            def _as_comparable(groups):
                return sorted(
                    tuple(sorted(id(pd['hash']) for pd in g)) for g in groups
                )

            assert _as_comparable(indexed) == _as_comparable(reference)

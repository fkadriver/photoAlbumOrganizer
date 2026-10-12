#!/usr/bin/env python3
"""Unit tests for find_best_photo()'s fallback to ML quality scoring when no
face is detected in any photo in the group — this is the only place the
organizer picks a "best" photo, so a silent fallback to group[0] (no face
backend, no quality signal) directly affects what --resolve-duplicates
and --archive-non-best keep vs. discard."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import image_processing  # noqa: E402
from photo_sources import Photo  # noqa: E402


def _make_group(ids):
    group = []
    for pid in ids:
        photo = Photo(photo_id=pid, source='local', metadata={'filename': pid})
        photo.cached_path = Path(f"/fake/{pid}.jpg")
        group.append({'photo': photo, 'metadata': {}})
    return group


class FakeScorer:
    """Returns a preset score per cached_path, keyed by filename stem."""
    def __init__(self, scores_by_id):
        self.scores_by_id = scores_by_id

    def score(self, image_path):
        stem = Path(image_path).stem
        return self.scores_by_id[stem]


def test_falls_back_to_quality_scorer_when_no_faces(monkeypatch):
    monkeypatch.setattr(image_processing, 'score_face_quality', lambda photo, source: [])
    group = _make_group(['a', 'b', 'c'])
    scorer = FakeScorer({'a': 0.2, 'b': 0.9, 'c': 0.5})

    result = image_processing.find_best_photo(group, photo_source=MagicMock(), quality_scorer=scorer)

    assert result['photo'].id == 'b'


def test_returns_first_photo_when_no_faces_and_no_scorer(monkeypatch):
    monkeypatch.setattr(image_processing, 'score_face_quality', lambda photo, source: [])
    group = _make_group(['a', 'b', 'c'])

    result = image_processing.find_best_photo(group, photo_source=MagicMock(), quality_scorer=None)

    assert result['photo'].id == 'a'


def test_face_score_wins_over_quality_scorer_when_faces_present(monkeypatch):
    # Photo 'b' has a detected face with a high score; others have none.
    def fake_score_face_quality(photo, source):
        return [10] if photo.id == 'b' else []
    monkeypatch.setattr(image_processing, 'score_face_quality', fake_score_face_quality)

    group = _make_group(['a', 'b', 'c'])
    # Quality scorer would pick 'a' if consulted — it must NOT be, since a
    # face was found somewhere in the group.
    scorer = FakeScorer({'a': 0.99, 'b': 0.1, 'c': 0.1})

    result = image_processing.find_best_photo(group, photo_source=MagicMock(), quality_scorer=scorer)

    assert result['photo'].id == 'b'


def test_immich_faces_fallback_passes_quality_scorer_through(monkeypatch):
    monkeypatch.setattr(image_processing, 'score_face_quality', lambda photo, source: [])
    group = _make_group(['a', 'b'])
    scorer = FakeScorer({'a': 0.1, 'b': 0.8})

    source = MagicMock()
    source.get_asset_face_data.return_value = []  # no Immich face data either

    result = image_processing.find_best_photo_immich_faces(group, source, quality_scorer=scorer)

    assert result['photo'].id == 'b'

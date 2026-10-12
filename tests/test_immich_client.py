#!/usr/bin/env python3
"""Unit tests for ImmichClient's duplicate-resolve, people-merge, and
permission-hint behavior. Covers endpoints added for Immich's newer
people-tagging and duplicate-resolve APIs, since they're destructive and
had zero prior test coverage."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from immich_client import ImmichClient  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


@pytest.fixture
def client():
    c = ImmichClient(url="http://immich.test", api_key="fake-key")
    c.session = MagicMock()
    return c


class TestResolveDuplicates:
    def test_posts_expected_payload(self, client):
        client.session.post.return_value = FakeResponse(200, [])
        groups = [{
            'duplicate_id': 'dup-1',
            'keep_asset_ids': ['keep-1'],
            'trash_asset_ids': ['trash-1', 'trash-2'],
        }]
        assert client.resolve_duplicates(groups) is True

        url, kwargs = client.session.post.call_args
        assert url[0] == "http://immich.test/api/duplicates/resolve"
        assert kwargs['json'] == {
            'groups': [{
                'duplicateId': 'dup-1',
                'keepAssetIds': ['keep-1'],
                'trashAssetIds': ['trash-1', 'trash-2'],
            }]
        }

    def test_returns_false_on_error(self, client):
        client.session.post.return_value = FakeResponse(500)
        result = client.resolve_duplicates([{
            'duplicate_id': 'dup-1', 'keep_asset_ids': ['a'], 'trash_asset_ids': ['b'],
        }])
        assert result is False


class TestDismissDuplicates:
    def test_single_id_uses_path_param(self, client):
        client.session.delete.return_value = FakeResponse(200)
        assert client.dismiss_duplicates(['dup-1']) is True
        url, kwargs = client.session.delete.call_args
        assert url[0] == "http://immich.test/api/duplicates/dup-1"

    def test_multiple_ids_uses_bulk_body(self, client):
        client.session.delete.return_value = FakeResponse(200)
        assert client.dismiss_duplicates(['dup-1', 'dup-2']) is True
        url, kwargs = client.session.delete.call_args
        assert url[0] == "http://immich.test/api/duplicates"
        assert kwargs['json'] == {'ids': ['dup-1', 'dup-2']}


class TestMergePeople:
    def test_requires_at_least_two_distinct_ids(self, client):
        assert client.merge_people(['only-one']) is False
        assert client.merge_people(['same', 'same']) is False
        client.session.post.assert_not_called()

    def test_posts_ids_with_first_as_survivor(self, client):
        client.session.post.return_value = FakeResponse(200, [])
        assert client.merge_people(['survivor', 'absorbed']) is True
        url, kwargs = client.session.post.call_args
        assert url[0] == "http://immich.test/api/people/merge"
        assert kwargs['json'] == {'ids': ['survivor', 'absorbed']}

    def test_returns_false_on_error(self, client):
        client.session.post.return_value = FakeResponse(400)
        assert client.merge_people(['a', 'b']) is False


class TestReassignFaces:
    def test_puts_expected_payload(self, client):
        client.session.put.return_value = FakeResponse(200, [])
        ok = client.reassign_faces('target-person', [
            {'person_id': 'source-person', 'asset_id': 'asset-1'},
        ])
        assert ok is True
        url, kwargs = client.session.put.call_args
        assert url[0] == "http://immich.test/api/people/target-person/reassign"
        assert kwargs['json'] == {
            'data': [{'personId': 'source-person', 'assetId': 'asset-1'}]
        }

    def test_returns_false_on_error(self, client):
        client.session.put.return_value = FakeResponse(403)
        ok = client.reassign_faces('target', [{'person_id': 's', 'asset_id': 'a'}])
        assert ok is False


class TestGetPersonStatistics:
    def test_returns_asset_count(self, client):
        client.session.get.return_value = FakeResponse(200, {'assets': 42})
        assert client.get_person_statistics('person-1') == 42

    def test_returns_zero_on_error(self, client):
        client.session.get.return_value = FakeResponse(404)
        assert client.get_person_statistics('person-1') == 0


class TestPermissionHints:
    """403s should name the specific Immich permission scope, not a stale one."""

    @pytest.mark.parametrize("method,endpoint,expected_scope", [
        ("GET", "/api/duplicates", "duplicate.read"),
        ("POST", "/api/duplicates/resolve", "duplicate.delete"),
        ("DELETE", "/api/duplicates", "duplicate.delete"),
        ("GET", "/api/people", "person.read"),
        ("GET", "/api/people/abc/statistics", "person.read"),
        ("POST", "/api/people/merge", "person.merge"),
        ("PUT", "/api/people/abc/reassign", "person.reassign"),
        ("PUT", "/api/people/abc", "person.update"),
        ("GET", "/api/faces", "person.read"),
        ("POST", "/api/search/smart", "asset.read"),
        ("GET", "/api/tags", "tag.read"),
        ("POST", "/api/tags", "tag.create"),
        ("PUT", "/api/tags/t1/assets", "tag.asset"),
    ])
    def test_hint_names_correct_scope(self, client, method, endpoint, expected_scope):
        hint = client._permission_hint(method, endpoint)
        assert expected_scope in hint

    def test_403_on_raw_get_includes_hint_text(self, client):
        client.session.get.return_value = FakeResponse(403)
        with pytest.raises(requests.HTTPError, match="person.read"):
            client._get('/api/people')

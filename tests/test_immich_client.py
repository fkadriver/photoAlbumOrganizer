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

import time  # noqa: E402

from immich_client import ImmichClient, _run_with_deadline  # noqa: E402


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
        ("PUT", "/api/tags", "tag.create"),  # bulk upsert — same scope as POST
        ("PUT", "/api/tags/t1", "tag.update"),
        ("PUT", "/api/tags/t1/assets", "tag.asset"),
        ("POST", "/api/assets", "asset.upload"),
        ("PUT", "/api/assets/a1", "asset.update"),
        ("GET", "/api/assets/a1", "asset.read"),
    ])
    def test_hint_names_correct_scope(self, client, method, endpoint, expected_scope):
        hint = client._permission_hint(method, endpoint)
        assert expected_scope in hint

    def test_403_on_raw_get_includes_hint_text(self, client):
        client.session.get.return_value = FakeResponse(403)
        with pytest.raises(requests.HTTPError, match="person.read"):
            client._get('/api/people')


class TestGetOrCreateTag:
    """Immich's tags are hierarchical: GET /tags returns 'name' (leaf only,
    e.g. "best") and 'value' (full path, e.g. "photo-organizer/best").
    POST /tags rejects any '/' in the name outright, so this must go through
    the bulk-upsert endpoint (PUT /tags), which auto-creates missing levels
    and is matched back by 'value', not 'name'."""

    def test_uses_bulk_upsert_with_full_path(self, client):
        client.session.put.return_value = FakeResponse(200, [
            {'id': 'tag-1', 'name': 'best', 'value': 'photo-organizer/best'},
        ])
        tag_id = client.get_or_create_tag('photo-organizer/best')
        assert tag_id == 'tag-1'

        url, kwargs = client.session.put.call_args
        assert url[0] == "http://immich.test/api/tags"
        assert kwargs['json'] == {'tags': ['photo-organizer/best']}

    def test_matches_response_by_value_not_leaf_name(self, client):
        # Response includes an unrelated tag sharing the same leaf name.
        client.session.put.return_value = FakeResponse(200, [
            {'id': 'wrong-tag', 'name': 'best', 'value': 'other-app/best'},
            {'id': 'right-tag', 'name': 'best', 'value': 'photo-organizer/best'},
        ])
        assert client.get_or_create_tag('photo-organizer/best') == 'right-tag'

    def test_falls_back_to_get_tags_when_upsert_response_lacks_match(self, client):
        client.session.put.return_value = FakeResponse(200, [])
        client.session.get.return_value = FakeResponse(200, [
            {'id': 'existing-tag', 'name': 'best', 'value': 'photo-organizer/best'},
        ])
        assert client.get_or_create_tag('photo-organizer/best') == 'existing-tag'

    def test_returns_none_on_error(self, client):
        client.session.put.return_value = FakeResponse(400)
        assert client.get_or_create_tag('photo-organizer/best') is None


class TestDeleteTagsByPrefix:
    def test_matches_by_full_path_value_not_leaf_name(self, client):
        client.session.get.return_value = FakeResponse(200, [
            {'id': 't1', 'name': 'best', 'value': 'photo-organizer/best'},
            {'id': 't2', 'name': 'non-best', 'value': 'photo-organizer/non-best'},
            {'id': 't3', 'name': 'best', 'value': 'other-app/best'},
        ])
        matched, deleted = client.delete_tags_by_prefix('photo-organizer/', dry_run=True)
        assert matched == 2
        assert deleted == 0

    def test_deletes_deepest_tags_before_shallower_ones(self, client):
        # Deleting a parent while a child still exists has been observed to
        # 400 in practice; deepest-first avoids that regardless of the
        # order get_tags() happens to return.
        client.session.get.return_value = FakeResponse(200, [
            {'id': 'root', 'value': 'photo-organizer'},
            {'id': 'parent', 'value': 'photo-organizer/modified'},
            {'id': 'child', 'value': 'photo-organizer/modified/face-swapped'},
        ])
        client.session.delete.return_value = FakeResponse(200)

        client.delete_tags_by_prefix('photo-organizer/', dry_run=False)

        deleted_order = [call.args[0].rsplit('/', 1)[-1]
                          for call in client.session.delete.call_args_list]
        # 'child' (2 slashes) must come before 'parent' (1 slash).
        assert deleted_order.index('child') < deleted_order.index('parent')


class TestSearchAssetsByTag:
    def test_matches_full_path_not_leaf_name(self, client):
        client.session.get.return_value = FakeResponse(200, [
            {'id': 'tag-1', 'name': 'best', 'value': 'photo-organizer/best'},
        ])
        client.session.post.return_value = FakeResponse(200, {
            'assets': {'items': [{'id': 'asset-1'}, {'id': 'asset-2'}]}
        })
        asset_ids = client.search_assets_by_tag('photo-organizer/best')
        assert asset_ids == ['asset-1', 'asset-2']
        _, kwargs = client.session.post.call_args
        assert kwargs['json']['tagIds'] == ['tag-1']


class TestRunWithDeadline:
    """requests' (connect, read) timeout only bounds each individual socket
    read, not total call duration — a stalled DNS lookup or a proxy that
    keeps a stuck connection "alive" with periodic bytes can hang forever
    with no error. This hard wall-clock backstop is what actually caught
    that in practice; cover it directly rather than only through mocks that
    always return instantly."""

    def test_returns_value_when_fn_completes_in_time(self):
        assert _run_with_deadline(lambda: 42, deadline_seconds=1) == 42

    def test_reraises_exception_from_fn(self):
        def _boom():
            raise ValueError("network broke")
        with pytest.raises(ValueError, match="network broke"):
            _run_with_deadline(_boom, deadline_seconds=1)

    def test_raises_timeout_error_past_deadline(self):
        def _hang_forever():
            time.sleep(10)
            return "too late"
        start = time.monotonic()
        with pytest.raises(TimeoutError, match="did not complete within"):
            _run_with_deadline(_hang_forever, deadline_seconds=0.2)
        # Must return control at the deadline, not wait for fn() to finish.
        assert time.monotonic() - start < 2

    def test_client_calls_respect_configured_hard_deadline(self):
        c = ImmichClient(url="http://immich.test", api_key="fake-key",
                          hard_deadline=0.2)
        c.session = MagicMock()

        def _slow_get(*args, **kwargs):
            time.sleep(10)
            return FakeResponse(200, {})
        c.session.get.side_effect = _slow_get

        with pytest.raises(TimeoutError):
            c._get('/api/server/ping')


class TestUploadAsset:
    def test_posts_multipart_with_required_fields(self, client, tmp_path):
        f = tmp_path / "result.jpg"
        f.write_bytes(b"fake-jpeg-bytes")
        client.session.post.return_value = FakeResponse(200, {'id': 'new-id', 'status': 'created'})

        result = client.upload_asset(str(f), file_created_at='2024-01-01T12:00:00.000Z')

        assert result == {'id': 'new-id', 'status': 'created'}
        url, kwargs = client.session.post.call_args
        assert url[0] == "http://immich.test/api/assets"
        assert kwargs['data']['fileCreatedAt'] == '2024-01-01T12:00:00.000Z'
        # Defaults fileModifiedAt to fileCreatedAt when not given.
        assert kwargs['data']['fileModifiedAt'] == '2024-01-01T12:00:00.000Z'
        assert 'assetData' in kwargs['files']
        assert kwargs['files']['assetData'][0] == 'result.jpg'

    def test_uses_explicit_filename_and_modified_at(self, client, tmp_path):
        f = tmp_path / "result.jpg"
        f.write_bytes(b"x")
        client.session.post.return_value = FakeResponse(200, {'id': 'a', 'status': 'created'})

        client.upload_asset(str(f), file_created_at='2024-01-01T12:00:00.000Z',
                             file_modified_at='2024-06-01T00:00:00.000Z',
                             filename='renamed.jpg')

        _, kwargs = client.session.post.call_args
        assert kwargs['data']['fileModifiedAt'] == '2024-06-01T00:00:00.000Z'
        assert kwargs['files']['assetData'][0] == 'renamed.jpg'

    def test_is_favorite_sets_form_field(self, client, tmp_path):
        f = tmp_path / "result.jpg"
        f.write_bytes(b"x")
        client.session.post.return_value = FakeResponse(200, {'id': 'a', 'status': 'created'})

        client.upload_asset(str(f), file_created_at='2024-01-01T12:00:00.000Z', is_favorite=True)

        _, kwargs = client.session.post.call_args
        assert kwargs['data']['isFavorite'] == 'true'

    def test_returns_duplicate_status_from_immich(self, client, tmp_path):
        f = tmp_path / "result.jpg"
        f.write_bytes(b"x")
        client.session.post.return_value = FakeResponse(
            200, {'id': 'existing-id', 'status': 'duplicate'})

        result = client.upload_asset(str(f), file_created_at='2024-01-01T12:00:00.000Z')

        assert result['status'] == 'duplicate'

    def test_returns_none_on_error(self, client, tmp_path):
        f = tmp_path / "result.jpg"
        f.write_bytes(b"x")
        client.session.post.return_value = FakeResponse(400)

        result = client.upload_asset(str(f), file_created_at='2024-01-01T12:00:00.000Z')

        assert result is None

    def test_returns_none_when_file_missing(self, client, tmp_path):
        result = client.upload_asset(str(tmp_path / "nope.jpg"),
                                      file_created_at='2024-01-01T12:00:00.000Z')
        assert result is None

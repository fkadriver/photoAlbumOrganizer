#!/usr/bin/env python3
"""Unit tests for the web viewer's finalize-group action: uploading a
locally-reprocessed result (face swap / HDR) back to Immich as the group's
new best photo, then archiving or trashing the rest."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import web_viewer  # noqa: E402


def _make_handler():
    return web_viewer.ViewerHandler.__new__(web_viewer.ViewerHandler)


def _write_report(path, groups):
    path.write_text(json.dumps({"groups": groups, "metadata": {}}))


def _basic_group(group_index=1, duplicate_id=None):
    return {
        "group_index": group_index,
        "immich_duplicate_id": duplicate_id,
        "best_photo": {"id": "orig-a", "asset_id": "orig-a", "filename": "a.jpg"},
        "photos": [
            {"id": "orig-a", "asset_id": "orig-a", "filename": "a.jpg", "is_best": True,
             "exif_dateTimeOriginal": "2024:01:01 12:00:00"},
            {"id": "orig-b", "asset_id": "orig-b", "filename": "b.jpg", "is_best": False},
            {"id": "orig-c", "asset_id": "orig-c", "filename": "c.jpg", "is_best": False},
        ],
        "actions_taken": [],
    }


def _call(handler, body):
    result = {}
    handler._send_json = lambda data, status=200: result.update(data, _status=status)
    handler._handle_finalize_group(body)
    return result


class TestSourceExisting:
    def test_marks_whichever_photo_is_already_best(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group()])
        web_viewer._report_path = str(report_path)
        web_viewer._immich_client = MagicMock()
        web_viewer._output_dir = None

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "existing", "cleanup": "none"})

        assert result["ok"] is True
        assert result["uploaded"] is False
        assert result["new_best_asset_id"] == "orig-a"
        web_viewer._immich_client.upload_asset.assert_not_called()

    def test_errors_when_no_immich_client(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group()])
        web_viewer._report_path = str(report_path)
        web_viewer._immich_client = None

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "existing"})

        assert result["ok"] is False

    def test_errors_on_unknown_group(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group()])
        web_viewer._report_path = str(report_path)
        web_viewer._immich_client = MagicMock()

        handler = _make_handler()
        result = _call(handler, {"group_index": 999, "source": "existing"})

        assert result["ok"] is False


class TestSourceFaceSwap:
    def test_uploads_local_result_and_updates_report(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group()])
        output_dir = tmp_path / "output"
        group_dir = output_dir / "group_0001"
        group_dir.mkdir(parents=True)
        (group_dir / "face_swapped_reprocessed.jpg").write_bytes(b"fake-jpeg")

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(output_dir)
        client = MagicMock()
        client.upload_asset.return_value = {"id": "new-asset-id", "status": "created"}
        client.get_or_create_tag.return_value = "best-tag-id"
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "face_swap", "cleanup": "none"})

        assert result["ok"] is True
        assert result["uploaded"] is True
        assert result["new_best_asset_id"] == "new-asset-id"

        # Uploaded with the original best photo's capture time, not "now".
        _, kwargs = client.upload_asset.call_args
        assert kwargs["file_created_at"] == "2024:01:01 12:00:00"

        # Tagged like everything else this tool creates.
        client.tag_assets_by_tag_id.assert_called_once_with("best-tag-id", ["new-asset-id"])

        # Report reflects the new best; originals are still listed (as
        # non-best) since cleanup was "none".
        saved = json.loads(report_path.read_text())
        group = saved["groups"][0]
        assert group["best_photo"]["asset_id"] == "new-asset-id"
        ids = {p["asset_id"]: p["is_best"] for p in group["photos"]}
        assert ids["new-asset-id"] is True
        assert ids["orig-a"] is False
        assert ids["orig-b"] is False
        assert ids["orig-c"] is False
        assert "uploaded_reprocessed" in group["actions_taken"]

    def test_404_when_no_reprocess_output_exists(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group()])
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(output_dir)
        web_viewer._immich_client = MagicMock()

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "face_swap"})

        assert result["ok"] is False
        web_viewer._immich_client.upload_asset.assert_not_called()

    def test_upload_failure_does_not_corrupt_report(self, tmp_path):
        report_path = tmp_path / "report.json"
        original = _basic_group()
        _write_report(report_path, [original])
        output_dir = tmp_path / "output"
        group_dir = output_dir / "group_0001"
        group_dir.mkdir(parents=True)
        (group_dir / "face_swapped.jpg").write_bytes(b"x")

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(output_dir)
        client = MagicMock()
        client.upload_asset.return_value = None  # upload failed
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "face_swap"})

        assert result["ok"] is False
        saved = json.loads(report_path.read_text())
        assert saved["groups"][0]["best_photo"]["asset_id"] == "orig-a"  # unchanged


class TestCleanup:
    def test_trash_uses_native_resolve_when_group_is_a_known_duplicate_and_not_uploaded(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group(duplicate_id="dup-123")])
        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = None
        client = MagicMock()
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "existing", "cleanup": "trash"})

        assert result["ok"] is True
        assert result["cleanup_count"] == 2
        client.resolve_duplicates.assert_called_once_with([{
            'duplicate_id': 'dup-123',
            'keep_asset_ids': ['orig-a'],
            'trash_asset_ids': ['orig-b', 'orig-c'],
        }])
        client.bulk_delete_assets.assert_not_called()

    def test_trash_falls_back_to_plain_delete_when_best_was_uploaded(self, tmp_path):
        # An uploaded asset was never part of Immich's own duplicate
        # detection, so it can't be a "keep" id for resolve_duplicates even
        # if the group itself came from one.
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group(duplicate_id="dup-123")])
        output_dir = tmp_path / "output"
        group_dir = output_dir / "group_0001"
        group_dir.mkdir(parents=True)
        (group_dir / "hdr_merged.jpg").write_bytes(b"x")

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(output_dir)
        client = MagicMock()
        client.upload_asset.return_value = {"id": "new-asset-id", "status": "created"}
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "hdr", "cleanup": "trash"})

        assert result["ok"] is True
        client.resolve_duplicates.assert_not_called()
        client.bulk_delete_assets.assert_called_once_with(
            ['orig-a', 'orig-b', 'orig-c'], force=False)

    def test_archive_updates_non_best_assets(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group()])
        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = None
        client = MagicMock()
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "existing", "cleanup": "archive"})

        assert result["ok"] is True
        client.bulk_update_assets.assert_called_once_with(
            ['orig-b', 'orig-c'], is_archived=True)

    def test_cleanup_none_touches_nothing(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_basic_group()])
        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = None
        client = MagicMock()
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call(handler, {"group_index": 1, "source": "existing", "cleanup": "none"})

        assert result["ok"] is True
        assert result["cleanup_count"] == 0
        client.bulk_delete_assets.assert_not_called()
        client.bulk_update_assets.assert_not_called()
        client.resolve_duplicates.assert_not_called()

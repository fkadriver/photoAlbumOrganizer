#!/usr/bin/env python3
"""Unit tests for the web viewer's 'download-fullres' bulk action: pulling
true full-resolution originals for every photo in selected groups, since the
copies written during a normal run may only be preview-quality thumbnails
(ImmichPhotoSource defaults to use_thumbnails=True unless the run was started
with --use-full-resolution)."""
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


def _group(group_index=1):
    return {
        "group_index": group_index,
        "best_photo": {"id": "a", "asset_id": "a", "filename": "a.jpg"},
        "photos": [
            {"id": "a", "asset_id": "a", "filename": "a.jpg", "is_best": True},
            {"id": "b", "asset_id": "b", "filename": "b.jpg", "is_best": False},
        ],
        "actions_taken": [],
    }


def _call_bulk(handler, body):
    result = {}
    handler._send_json = lambda data, status=200: result.update(data, _status=status)
    handler._handle_bulk(body)
    return result


class TestDownloadFullres:
    def test_downloads_every_photo_in_selected_groups(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_group(1), _group(2)])
        output_dir = tmp_path / "output"

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(output_dir)
        client = MagicMock()
        client.download_asset.return_value = b"full-res-bytes"
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call_bulk(handler, {"action": "download-fullres", "group_indices": [1]})

        assert result["ok"] is True
        assert result["downloaded"] == 2
        assert client.download_asset.call_count == 2
        client.download_asset.assert_any_call("a")
        client.download_asset.assert_any_call("b")

        group1_dir = output_dir / "group_0001" / "originals"
        assert (group1_dir / "a.jpg").read_bytes() == b"full-res-bytes"
        assert (group1_dir / "b.jpg").read_bytes() == b"full-res-bytes"
        # Group 2 was not selected, so nothing was written for it.
        assert not (output_dir / "group_0002").exists()

    def test_overwrites_existing_preview_quality_file(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_group(1)])
        output_dir = tmp_path / "output"
        orig_dir = output_dir / "group_0001" / "originals"
        orig_dir.mkdir(parents=True)
        (orig_dir / "a.jpg").write_bytes(b"stale-preview-bytes")

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(output_dir)
        client = MagicMock()
        client.download_asset.return_value = b"real-fullres-bytes"
        web_viewer._immich_client = client

        handler = _make_handler()
        _call_bulk(handler, {"action": "download-fullres", "group_indices": [1]})

        assert (orig_dir / "a.jpg").read_bytes() == b"real-fullres-bytes"

    def test_errors_when_no_output_dir_configured(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_group(1)])

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = None
        web_viewer._immich_client = MagicMock()

        handler = _make_handler()
        result = _call_bulk(handler, {"action": "download-fullres", "group_indices": [1]})

        assert result["ok"] is False
        web_viewer._immich_client.download_asset.assert_not_called()

    def test_errors_when_no_immich_client(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_group(1)])

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(tmp_path / "output")
        web_viewer._immich_client = None

        handler = _make_handler()
        result = _call_bulk(handler, {"action": "download-fullres", "group_indices": [1]})

        assert result["ok"] is False

    def test_reports_failures_without_crashing(self, tmp_path):
        report_path = tmp_path / "report.json"
        _write_report(report_path, [_group(1)])
        output_dir = tmp_path / "output"

        web_viewer._report_path = str(report_path)
        web_viewer._output_dir = str(output_dir)
        client = MagicMock()
        # 'a' downloads fine, 'b' fails (returns None, as download_asset does
        # on error).
        client.download_asset.side_effect = lambda aid: b"bytes" if aid == "a" else None
        web_viewer._immich_client = client

        handler = _make_handler()
        result = _call_bulk(handler, {"action": "download-fullres", "group_indices": [1]})

        assert result["ok"] is True
        assert result["downloaded"] == 1
        assert result["failed"] == ["b.jpg"]

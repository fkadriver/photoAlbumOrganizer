#!/usr/bin/env python3
"""Unit tests for src/apple_actions.py (AppleScript helpers).

All tests mock subprocess so no actual Photos.app interaction occurs.
"""
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import apple_actions


def _make_run_result(returncode=0, stdout="", stderr=""):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


class TestRun:
    def test_success_returns_true_and_output(self):
        with patch("subprocess.run", return_value=_make_run_result(stdout="ok")):
            ok, out = apple_actions._run("tell application \"Photos\" to get name")
        assert ok is True
        assert out == "ok"

    def test_nonzero_returncode_returns_false(self):
        with patch("subprocess.run", return_value=_make_run_result(returncode=1, stderr="error")):
            ok, err = apple_actions._run("bad script")
        assert ok is False

    def test_timeout_returns_false_not_raises(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 10)):
            ok, msg = apple_actions._run("slow script")
        assert ok is False
        assert "timeout" in msg.lower() or msg == "timeout"

    def test_file_not_found_returns_false(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("osascript not found")):
            ok, msg = apple_actions._run("any script")
        assert ok is False


class TestCheckPermission:
    def test_returns_true_when_photos_responds(self):
        with patch("apple_actions._run", return_value=(True, "Photos")):
            assert apple_actions.check_permission() is True

    def test_returns_false_on_timeout(self, capsys):
        with patch("apple_actions._run", return_value=(False, "timeout")):
            result = apple_actions.check_permission()
        assert result is False
        captured = capsys.readouterr()
        assert "Permission" in captured.out or "permission" in captured.out or \
               "Automation" in captured.out or "Photos" in captured.out

    def test_returns_false_on_error(self):
        with patch("apple_actions._run", return_value=(False, "some error")):
            assert apple_actions.check_permission() is False


class TestSetFavorite:
    def test_sets_favorite_true(self):
        with patch("apple_actions._run", return_value=(True, "")) as mock_run:
            result = apple_actions.set_favorite("UUID-001", True)
        assert result is True
        script = mock_run.call_args[0][0]
        assert "UUID-001" in script
        assert "true" in script
        assert "favorite" in script

    def test_sets_favorite_false(self):
        with patch("apple_actions._run", return_value=(True, "")) as mock_run:
            apple_actions.set_favorite("UUID-001", False)
        script = mock_run.call_args[0][0]
        assert "false" in script


class TestAddKeyword:
    def test_adds_keyword_to_photo(self):
        with patch("apple_actions._run", return_value=(True, "")) as mock_run:
            result = apple_actions.add_keyword("UUID-002", "best-photo")
        assert result is True
        script = mock_run.call_args[0][0]
        assert "UUID-002" in script
        assert "best-photo" in script

    def test_escapes_double_quotes_in_keyword(self):
        with patch("apple_actions._run", return_value=(True, "")) as mock_run:
            apple_actions.add_keyword("UUID", 'say "hello"')
        script = mock_run.call_args[0][0]
        # Raw double quotes in keyword must be escaped
        assert '"hello"' not in script or '\\"hello\\"' in script

    def test_returns_false_on_failure(self):
        with patch("apple_actions._run", return_value=(False, "error")):
            assert apple_actions.add_keyword("UUID", "kw") is False


class TestRemoveKeyword:
    def test_removes_keyword(self):
        with patch("apple_actions._run", return_value=(True, "")) as mock_run:
            result = apple_actions.remove_keyword("UUID-003", "archive")
        assert result is True
        script = mock_run.call_args[0][0]
        assert "UUID-003" in script
        assert "archive" in script


class TestEnsureFolder:
    def test_creates_folder_if_missing(self):
        with patch("apple_actions._run", return_value=(True, "")) as mock_run:
            apple_actions._ensure_folder()
        script = mock_run.call_args[0][0]
        assert "photoOrganizer" in script
        assert "make new folder" in script


class TestCreateAlbum:
    def test_creates_album_in_folder(self):
        calls = []
        with patch("apple_actions._run",
                   side_effect=lambda s: calls.append(s) or (True, "")):
            result = apple_actions.create_album("My Album")
        assert result is True
        combined = "\n".join(calls)
        assert "photoOrganizer" in combined
        assert "My Album" in combined

    def test_returns_false_when_folder_creation_fails(self):
        with patch("apple_actions._run", return_value=(False, "denied")):
            assert apple_actions.create_album("Album") is False


class TestAddToAlbum:
    def test_adds_single_batch(self):
        calls = []
        with patch("apple_actions._run",
                   side_effect=lambda s: calls.append(s) or (True, "")):
            result = apple_actions.add_to_album("Test", ["UUID-A", "UUID-B"])
        assert result is True
        combined = "\n".join(calls)
        assert "UUID-A" in combined
        assert "UUID-B" in combined

    def test_batches_large_input(self):
        """With > _BATCH_SIZE items, multiple add calls are made."""
        uuids = [f"UUID-{i:04d}" for i in range(apple_actions._BATCH_SIZE + 10)]
        calls = []
        with patch("apple_actions._run",
                   side_effect=lambda s: calls.append(s) or (True, "")):
            apple_actions.add_to_album("BigAlbum", uuids)
        # At least 3 calls: ensure_folder + create_album + 2 add batches
        assert len(calls) >= 3

    def test_returns_false_if_album_creation_fails(self):
        with patch("apple_actions._run", return_value=(False, "error")):
            assert apple_actions.add_to_album("Album", ["UUID-1"]) is False


class TestCreateAlbumWithPhotos:
    def test_empty_list_just_creates_album(self):
        calls = []
        with patch("apple_actions._run",
                   side_effect=lambda s: calls.append(s) or (True, "")):
            apple_actions.create_album_with_photos("Empty", [])
        combined = "\n".join(calls)
        assert "Empty" in combined

    def test_with_photos_adds_them(self):
        calls = []
        with patch("apple_actions._run",
                   side_effect=lambda s: calls.append(s) or (True, "")):
            apple_actions.create_album_with_photos("Full", ["U1", "U2"])
        combined = "\n".join(calls)
        assert "U1" in combined

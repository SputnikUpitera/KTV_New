import importlib
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from remote_player.storage.database import Database


class FakeRuntimeScheduler:
    def __init__(self):
        self.reload_count = 0

    def reload_schedules(self):
        self.reload_count += 1

    def get_current_scheduled_playback(self):
        return None


class FakeRuntimePlayer:
    def get_status(self):
        return {"is_playing": False}


@pytest.fixture
def daemon_module(monkeypatch):
    remote_player_root = Path(__file__).resolve().parents[1] / "remote_player"
    monkeypatch.syspath_prepend(str(remote_player_root))

    fake_player = types.ModuleType("player")
    fake_player.Player = object
    fake_scheduler = types.ModuleType("scheduler")
    fake_scheduler.Scheduler = object
    fake_time_controller = types.ModuleType("time_controller")
    fake_time_controller.TimeController = object
    fake_playlist_manager = types.ModuleType("playlist_manager")
    fake_playlist_manager.PlaylistManager = object

    monkeypatch.setitem(sys.modules, "player", fake_player)
    monkeypatch.setitem(sys.modules, "scheduler", fake_scheduler)
    monkeypatch.setitem(sys.modules, "time_controller", fake_time_controller)
    monkeypatch.setitem(sys.modules, "playlist_manager", fake_playlist_manager)
    sys.modules.pop("daemon", None)
    return importlib.import_module("daemon")


@pytest.fixture
def daemon(daemon_module, tmp_path):
    instance = daemon_module.KTVDaemon.__new__(daemon_module.KTVDaemon)
    instance.media_base_path = tmp_path / "oktv"
    instance.clips_root = instance.media_base_path / "clips"
    instance.media_base_path.mkdir()
    instance.clips_root.mkdir()
    instance.config = {
        "aggressive_normalization": False,
        "api_port": 8888,
        "broadcast_start": "06:00",
        "broadcast_end": "22:00",
    }
    instance.db = Database(str(tmp_path / "schedule.db"))
    instance.player = FakeRuntimePlayer()
    instance.scheduler = FakeRuntimeScheduler()
    instance.playlist_manager = None
    instance.time_controller = None
    return instance


def test_get_linux_time_status_has_stable_shape(daemon_module):
    now = datetime(2026, 5, 15, 12, 34, 56, 987000, tzinfo=timezone(timedelta(hours=3), "MSK"))

    linux_time = daemon_module.get_linux_time_status(now)

    assert linux_time == {
        "iso": "2026-05-15T12:34:56+03:00",
        "epoch": int(now.timestamp()),
        "timezone": "MSK",
        "display": "2026-05-15 12:34:56 MSK",
    }


def test_get_status_includes_linux_time_field(daemon):
    status = daemon._handle_get_status({})

    assert set(status["linux_time"]) == {"iso", "epoch", "timezone", "display"}
    assert "T" in status["linux_time"]["iso"]
    assert isinstance(status["linux_time"]["epoch"], int)


def test_add_schedule_handler_validates_and_moves_to_weekly_path(daemon, tmp_path):
    source_dir = tmp_path / "uploads"
    source_dir.mkdir()
    source_path = source_dir / "movie.mp4"
    source_path.write_text("media")

    result = daemon._handle_add_schedule(
        {
            "weekday": 2,
            "hour": 9,
            "minute": 30,
            "filepath": str(source_path),
            "filename": "movie.mp4",
            "category": "movies",
        }
    )

    row = daemon.db.get_schedule(result["schedule_id"])
    expected_path = daemon.media_base_path / "weekly" / "2" / "09-30" / "movie.mp4"
    assert row["weekday"] == 2
    assert row["hour"] == 9
    assert row["minute"] == 30
    assert row["filepath"] == str(expected_path)
    assert expected_path.exists()
    assert daemon.scheduler.reload_count == 1


@pytest.mark.parametrize(
    "params, match",
    [
        (
            {"weekday": 7, "hour": 9, "minute": 30, "filepath": "__ABS_MOVIE__", "filename": "movie.mp4"},
            "weekday",
        ),
        (
            {"weekday": 1, "hour": 24, "minute": 30, "filepath": "__ABS_MOVIE__", "filename": "movie.mp4"},
            "hour",
        ),
        (
            {"weekday": 1, "hour": 9, "minute": 30, "filepath": "relative/movie.mp4", "filename": "movie.mp4"},
            "absolute",
        ),
        (
            {"weekday": 1, "hour": 9, "minute": 30, "filepath": "__ABS_MOVIE__", "filename": "../movie.mp4"},
            "filename",
        ),
    ],
)
def test_add_schedule_handler_rejects_invalid_input(daemon, params, match):
    params = dict(params)
    if params.get("filepath") == "__ABS_MOVIE__":
        params["filepath"] = str(Path.cwd() / "movie.mp4")
    with pytest.raises(ValueError, match=match):
        daemon._handle_add_schedule(params)


def test_update_schedule_handler_moves_existing_movie_to_new_weekly_slot(daemon):
    original_path = daemon.media_base_path / "weekly" / "0" / "08-00" / "movie.mp4"
    original_path.parent.mkdir(parents=True)
    original_path.write_text("media")
    schedule_id = daemon.db.add_schedule(
        weekday=0,
        hour=8,
        minute=0,
        filepath=str(original_path),
        filename="movie.mp4",
        category="movies",
    )

    result = daemon._handle_update_schedule(
        {
            "schedule_id": schedule_id,
            "weekday": 5,
            "hour": 18,
            "minute": 45,
        }
    )

    expected_path = daemon.media_base_path / "weekly" / "5" / "18-45" / "movie.mp4"
    row = daemon.db.get_schedule(schedule_id)
    assert result == {"success": True, "filepath": str(expected_path)}
    assert row["weekday"] == 5
    assert row["hour"] == 18
    assert row["minute"] == 45
    assert row["filepath"] == str(expected_path)
    assert expected_path.exists()


def test_sync_playlists_keeps_existing_files_and_playlist_rows_in_place(daemon):
    root_clip = daemon.clips_root / "root.mp4"
    root_clip.write_text("root")
    playlist_dir = daemon.clips_root / "old"
    playlist_dir.mkdir()
    nested_clip = playlist_dir / "nested.mp4"
    nested_clip.write_text("nested")
    playlist_id = daemon.db.create_playlist("old", str(playlist_dir))

    result = daemon.sync_playlists()

    assert result == {
        "success": True,
        "created": 0,
        "updated": 0,
        "imported": 0,
        "moved_root_files": 0,
    }
    assert root_clip.exists()
    assert nested_clip.exists()
    assert daemon.db.get_playlist(playlist_id)["folder_path"] == str(playlist_dir)
    assert daemon.db.get_active_playlist() is None


def test_play_clip_file_handler_rejects_unsafe_names(daemon):
    class FakePlaylistManager:
        def play_clip_file(self, filename):
            return True

    daemon.playlist_manager = FakePlaylistManager()

    for filename in ("../clip.mp4", "/tmp/clip.mp4", r"nested\clip.mp4"):
        with pytest.raises(ValueError):
            daemon._handle_play_clip_file({"filename": filename})


def test_play_clip_file_handler_reloads_clip_list_before_lookup(daemon):
    class FakePlaylistManager:
        def __init__(self):
            self.reload_count = 0
            self.played = []

        def reload_clips(self):
            self.reload_count += 1

        def play_clip_file(self, filename):
            self.played.append(filename)
            return True

        def get_status_snapshot(self):
            return {
                "has_files": True,
                "transport_available": True,
                "current_filename": "clip.mp4",
                "current_file": "/clips/clip.mp4",
                "next_filename": None,
                "next_file": None,
                "shuffle_enabled": False,
            }

    playlist_manager = FakePlaylistManager()
    daemon.playlist_manager = playlist_manager

    result = daemon._handle_play_clip_file({"filename": "clip.mp4"})

    assert playlist_manager.reload_count == 1
    assert playlist_manager.played == ["clip.mp4"]
    assert result["current_playback"]["filename"] == "clip.mp4"


def test_sync_playlists_handler_reloads_runtime_clip_state(daemon):
    class FakePlaylistManager:
        def __init__(self):
            self.reload_count = 0

        def reload_clips(self):
            self.reload_count += 1

    playlist_manager = FakePlaylistManager()
    daemon.playlist_manager = playlist_manager

    result = daemon._handle_sync_playlists({})

    assert result["success"] is True
    assert playlist_manager.reload_count == 1

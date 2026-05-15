from pathlib import Path

from remote_player.playlist_manager import PlaylistManager
from remote_player.storage.database import Database


class FakePlayer:
    def __init__(self):
        self.is_paused = False
        self.media = False
        self.played = []
        self.stop_count = 0

    def has_media(self):
        return self.media

    def play(self, path, fullscreen=True):
        self.played.append((path, fullscreen))
        self.media = True
        self.is_paused = False
        return True

    def stop(self):
        self.stop_count += 1
        self.media = False
        self.is_paused = False
        return True

    def pause(self):
        if not self.media:
            return False
        self.is_paused = True
        return True

    def resume(self):
        if not self.media:
            return False
        self.is_paused = False
        return True


def test_default_clip_list_ignores_active_playlist_rows(tmp_path):
    clips_root = tmp_path / "clips"
    clips_root.mkdir()
    (clips_root / "root.mp4").write_text("root")
    (clips_root / "notes.txt").write_text("notes")

    playlist_dir = tmp_path / "old-playlist"
    playlist_dir.mkdir()
    (playlist_dir / "old.mp4").write_text("old")

    database = Database(str(tmp_path / "schedule.db"))
    playlist_id = database.create_playlist("old", str(playlist_dir))
    database.set_active_playlist(playlist_id)

    manager = PlaylistManager(database, FakePlayer(), str(clips_root))
    manager.reload_active_playlist()

    assert [path.name for path in manager.current_files] == ["root.mp4"]
    assert manager.get_active_playlist_name() is None


def test_video_extension_filtering_is_case_insensitive(tmp_path):
    clips_root = tmp_path / "clips"
    clips_root.mkdir()
    (clips_root / "a.MKV").write_text("a")
    (clips_root / "b.webm").write_text("b")
    (clips_root / "c.txt").write_text("c")

    manager = PlaylistManager(Database(str(tmp_path / "schedule.db")), FakePlayer(), str(clips_root))
    manager.reload_active_playlist()

    assert [path.name for path in manager.current_files] == ["a.MKV", "b.webm"]


def test_play_clip_file_rejects_unsafe_names_and_selects_clip(tmp_path):
    clips_root = tmp_path / "clips"
    clips_root.mkdir()
    (clips_root / "alpha.mp4").write_text("alpha")
    (clips_root / "beta.mp4").write_text("beta")

    player = FakePlayer()
    player.media = True
    manager = PlaylistManager(Database(str(tmp_path / "schedule.db")), player, str(clips_root))
    manager.reload_active_playlist()

    assert not manager.play_clip_file("../beta.mp4")
    assert not manager.play_clip_file(str(clips_root / "beta.mp4"))

    assert manager.play_clip_file("beta.mp4")
    assert player.stop_count == 1
    assert manager.pending_index_override == 1
    assert not manager.user_paused


def test_transport_controls_with_fake_player(tmp_path):
    clips_root = tmp_path / "clips"
    clips_root.mkdir()
    (clips_root / "alpha.mp4").write_text("alpha")
    (clips_root / "beta.mp4").write_text("beta")

    player = FakePlayer()
    manager = PlaylistManager(Database(str(tmp_path / "schedule.db")), player, str(clips_root))
    manager.reload_active_playlist()

    assert manager.toggle_play_pause()
    assert manager.pending_index_override == 0
    next_video = manager._get_next_video()
    assert next_video.name == "alpha.mp4"
    assert player.play(str(next_video), fullscreen=True)

    assert manager.toggle_play_pause()
    assert player.is_paused
    assert manager.user_paused

    assert manager.toggle_play_pause()
    assert not player.is_paused
    assert not manager.user_paused

    assert manager.play_next()
    assert player.stop_count == 1
    assert manager.pending_index_override == 1
    assert not manager.user_paused

    assert manager.stop_playback()
    assert player.stop_count == 1
    assert manager.user_paused
    assert manager.paused

    assert manager.toggle_shuffle() is True
    assert manager.shuffle_enabled

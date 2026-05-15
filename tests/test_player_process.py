from pathlib import Path

from remote_player.player import Player


def test_player_builds_ordinary_vlc_command(tmp_path):
    media_file = tmp_path / "movie.mp4"
    media_file.write_text("not real media")

    player = Player(
        vlc_path="/usr/bin/vlc",
        avcodec_hw="none",
        video_output="xcb_x11",
        file_caching_ms=750,
        network_caching_ms=1250,
        extra_vlc_args=["--dummy-extra"],
    )

    command = player._build_command(str(media_file), fullscreen=True)

    assert command[0] == "/usr/bin/vlc"
    assert "--fullscreen" in command
    assert "--play-and-exit" in command
    assert "--file-caching=750" in command
    assert "--network-caching=1250" in command
    assert "--avcodec-hw=none" in command
    assert "--vout=xcb_x11" in command
    assert "--dummy-extra" in command
    assert command[-1] == str(media_file)


def test_player_import_has_no_python_vlc_dependency():
    # Importing Player is the production smoke check: it must not require the
    # Python VLC binding because the daemon is meant to use ordinary VLC.
    assert Player(vlc_path="vlc").vlc_path == "vlc"


def test_play_rejects_missing_file_without_starting_vlc(tmp_path):
    player = Player(vlc_path="vlc")

    assert not player.play(str(tmp_path / "missing.mp4"))
    assert player.get_status()["current_file"] is None

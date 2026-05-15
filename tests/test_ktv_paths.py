from pathlib import PurePosixPath

import ktv_paths


def test_remote_roots_are_built_under_normalized_home():
    assert ktv_paths.normalize_remote_home("  /remote/operator  ") == PurePosixPath("/remote/operator")
    assert ktv_paths.normalize_remote_home("") == PurePosixPath("~")
    assert ktv_paths.get_oktv_root("/remote/operator") == "/remote/operator/oktv"
    assert ktv_paths.get_movie_root("/remote/operator") == "/remote/operator/oktv/weekly"
    assert ktv_paths.get_clips_root("/remote/operator") == "/remote/operator/oktv/clips"


def test_movie_paths_are_zero_padded_and_use_filename_only():
    movie_dir = ktv_paths.build_movie_directory("/remote/operator", 5, 7, 8)

    assert movie_dir == "/remote/operator/oktv/weekly/5/07-08"
    assert (
        ktv_paths.build_movie_file_path("/remote/operator", 5, 7, 8, r"C:\upload\Movie.MP4")
        == "/remote/operator/oktv/weekly/5/07-08/Movie.MP4"
    )


def test_weekday_validation_rejects_invalid_values():
    for weekday in (-1, 7):
        try:
            ktv_paths.build_movie_directory("/remote/operator", weekday, 7, 8)
        except ValueError as exc:
            assert "weekday" in str(exc)
        else:
            raise AssertionError("invalid weekday was accepted")


def test_movie_filename_validation_rejects_unsafe_names():
    for filename in ("../movie.mp4", "nested/movie.mp4", "movie\x00.mp4"):
        try:
            ktv_paths.build_movie_file_path("/remote/operator", 1, 7, 8, filename)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe filename was accepted")


def test_playlist_directory_trims_playlist_name():
    assert (
        ktv_paths.build_playlist_directory("/remote/operator", "  morning clips  ")
        == "/remote/operator/oktv/clips/morning clips"
    )


def test_clip_file_path_uses_default_clips_root_and_filename_only():
    assert (
        ktv_paths.build_clip_file_path("/remote/operator", r"C:\upload\Clip.MP4")
        == "/remote/operator/oktv/clips/Clip.MP4"
    )


def test_clip_filename_validation_rejects_unsafe_names():
    for filename in (
        "../clip.mp4",
        "nested/clip.mp4",
        r"nested\clip.mp4",
        "/tmp/clip.mp4",
        r"C:\tmp\clip.mp4",
        "notes.txt",
    ):
        try:
            ktv_paths.validate_clip_filename(filename)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe clip filename was accepted")


def test_supported_video_files_are_case_insensitive():
    assert ktv_paths.is_supported_video_file("clip.MKV")
    assert ktv_paths.is_supported_video_file(PurePosixPath("/tmp/movie.webm"))
    assert not ktv_paths.is_supported_video_file("notes.txt")


def test_parse_movie_path_returns_schedule_parts():
    assert ktv_paths.parse_movie_path("/remote/operator/oktv/weekly/6/23-59/movie.mp4") == (
        6,
        23,
        59,
        "movie.mp4",
    )


def test_parse_movie_path_rejects_non_schedule_paths():
    assert ktv_paths.parse_movie_path("/remote/operator/clips/movie.mp4") is None
    assert ktv_paths.parse_movie_path("/remote/operator/oktv/12/31/23-59/movie.mp4") is None
    assert ktv_paths.parse_movie_path("/remote/operator/oktv/weekly/7/23-59/movie.mp4") is None
    assert ktv_paths.parse_movie_path("/remote/operator/oktv/weekly/6/2359/movie.mp4") is None
    assert ktv_paths.parse_movie_path("/remote/operator/oktv/weekly/6/23-59/nested/movie.mp4") is None

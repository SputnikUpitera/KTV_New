"""
Shared media/path helpers for scheduled movies and clip playlists.
"""

from pathlib import Path, PurePosixPath
from typing import Optional, Tuple, Union

OKTV_ROOT_NAME = "oktv"
CLIPS_DIR_NAME = "clips"
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv', '.wmv', '.m4v')
VIDEO_FILE_DIALOG_FILTER = "Видео (*.mp4 *.avi *.mkv *.webm *.mov *.flv *.wmv *.m4v);;Все файлы (*)"


def normalize_remote_home(home_dir: str) -> PurePosixPath:
    """Normalize a remote Linux home path for GUI-side path building."""
    home = (home_dir or "~").strip() or "~"
    return PurePosixPath(home)


def get_oktv_root(home_dir: str) -> str:
    """Return the shared media root under the user's home directory."""
    return str(normalize_remote_home(home_dir) / OKTV_ROOT_NAME)


def get_movie_root(home_dir: str) -> str:
    """Return the root folder for scheduled movies."""
    return get_oktv_root(home_dir)


def get_clips_root(home_dir: str) -> str:
    """Return the root folder for playlist directories."""
    return str(normalize_remote_home(home_dir) / OKTV_ROOT_NAME / CLIPS_DIR_NAME)


def build_movie_directory(home_dir: str, month: int, day: int, hour: int, minute: int) -> str:
    """Build the schedule slot directory for a movie."""
    return str(
        normalize_remote_home(home_dir)
        / OKTV_ROOT_NAME
        / f"{month:02d}"
        / f"{day:02d}"
        / f"{hour:02d}-{minute:02d}"
    )


def build_movie_file_path(home_dir: str, month: int, day: int, hour: int, minute: int, filename: str) -> str:
    """Build the full remote path for a scheduled movie file."""
    return str(PurePosixPath(build_movie_directory(home_dir, month, day, hour, minute)) / Path(filename).name)


def build_playlist_directory(home_dir: str, playlist_name: str) -> str:
    """Build the playlist directory path."""
    return str(PurePosixPath(get_clips_root(home_dir)) / playlist_name.strip())


def is_supported_video_file(path_like: Union[str, Path, PurePosixPath]) -> bool:
    """Check whether a filename/path has a supported video extension."""
    return Path(str(path_like)).suffix.lower() in VIDEO_EXTENSIONS


def parse_movie_path(filepath: str) -> Optional[Tuple[int, int, int, int, str]]:
    """Parse a scheduled movie path inside ~/oktv/MM/DD/HH-MM/file."""
    path = PurePosixPath(filepath)
    parts = path.parts

    try:
        oktv_index = parts.index(OKTV_ROOT_NAME)
    except ValueError:
        return None

    if len(parts) < oktv_index + 5:
        return None

    try:
        month = int(parts[oktv_index + 1])
        day = int(parts[oktv_index + 2])
        hour_part, minute_part = parts[oktv_index + 3].split("-", 1)
        hour = int(hour_part)
        minute = int(minute_part)
    except (ValueError, IndexError):
        return None

    filename = path.name
    if not filename:
        return None

    return month, day, hour, minute, filename


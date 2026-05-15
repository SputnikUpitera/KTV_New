"""
Shared media/path helpers for scheduled movies and clips.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional, Tuple, Union

OKTV_ROOT_NAME = "oktv"
CLIPS_DIR_NAME = "clips"
WEEKLY_MOVIES_DIR_NAME = "weekly"
WEEKDAY_MIN = 0
WEEKDAY_MAX = 6
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
    return str(normalize_remote_home(home_dir) / OKTV_ROOT_NAME / WEEKLY_MOVIES_DIR_NAME)


def get_clips_root(home_dir: str) -> str:
    """Return the root folder for clip files."""
    return str(normalize_remote_home(home_dir) / OKTV_ROOT_NAME / CLIPS_DIR_NAME)


def validate_weekday(weekday: int) -> int:
    """Validate weekday convention: 0=Monday through 6=Sunday."""
    if isinstance(weekday, bool) or not isinstance(weekday, int):
        raise ValueError("weekday must be an integer from 0=Monday through 6=Sunday")
    if weekday < WEEKDAY_MIN or weekday > WEEKDAY_MAX:
        raise ValueError("weekday must be from 0=Monday through 6=Sunday")
    return weekday


def validate_time(hour: int, minute: int) -> Tuple[int, int]:
    """Validate a wall-clock hour/minute pair."""
    if isinstance(hour, bool) or not isinstance(hour, int):
        raise ValueError("hour must be an integer from 0 through 23")
    if isinstance(minute, bool) or not isinstance(minute, int):
        raise ValueError("minute must be an integer from 0 through 59")
    if hour < 0 or hour > 23:
        raise ValueError("hour must be from 0 through 23")
    if minute < 0 or minute > 59:
        raise ValueError("minute must be from 0 through 59")
    return hour, minute


def extract_upload_filename(path_or_name: str) -> str:
    """Return a safe basename from a local upload path or filename."""
    raw = str(path_or_name or "").strip()
    if not raw:
        raise ValueError("filename is required")
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if ".." in posix_path.parts or ".." in windows_path.parts:
        raise ValueError("filename must not contain parent directory references")
    if "/" in raw and not posix_path.is_absolute():
        raise ValueError("filename must not contain relative path separators")
    if "\\" in raw and not (windows_path.is_absolute() or windows_path.drive):
        raise ValueError("filename must not contain relative path separators")

    filename = PureWindowsPath(raw).name if "\\" in raw else Path(raw).name
    return validate_movie_filename(filename)


def validate_movie_filename(filename: str) -> str:
    """Validate an already-extracted movie filename."""
    raw = str(filename or "").strip()
    if not raw:
        raise ValueError("filename is required")
    if raw in {".", ".."}:
        raise ValueError("filename is not safe")
    if "/" in raw or "\\" in raw:
        raise ValueError("filename must not contain path separators")
    if "\x00" in raw or any(ord(char) < 32 for char in raw):
        raise ValueError("filename contains unsafe characters")
    return raw


def validate_clip_filename(filename: str) -> str:
    """Validate a single clip filename."""
    safe_filename = validate_movie_filename(filename)
    if PurePosixPath(safe_filename).is_absolute() or PureWindowsPath(safe_filename).is_absolute():
        raise ValueError("filename must not be absolute")
    if not is_supported_video_file(safe_filename):
        raise ValueError("filename must point to a supported video file")
    return safe_filename


def build_movie_directory(home_dir: str, weekday: int, hour: int, minute: int) -> str:
    """Build the weekly schedule slot directory for a movie."""
    weekday = validate_weekday(weekday)
    hour, minute = validate_time(hour, minute)
    return str(
        normalize_remote_home(home_dir)
        / OKTV_ROOT_NAME
        / WEEKLY_MOVIES_DIR_NAME
        / f"{weekday}"
        / f"{hour:02d}-{minute:02d}"
    )


def build_movie_file_path(home_dir: str, weekday: int, hour: int, minute: int, filename: str) -> str:
    """Build the full remote path for a scheduled movie file."""
    safe_filename = extract_upload_filename(filename)
    return str(PurePosixPath(build_movie_directory(home_dir, weekday, hour, minute)) / safe_filename)


def build_playlist_directory(home_dir: str, playlist_name: str) -> str:
    """Build the playlist directory path."""
    return str(PurePosixPath(get_clips_root(home_dir)) / playlist_name.strip())


def build_clip_file_path(home_dir: str, filename: str) -> str:
    """Build the full remote path for a clip in the default clips folder."""
    safe_filename = validate_clip_filename(extract_upload_filename(filename))
    return str(PurePosixPath(get_clips_root(home_dir)) / safe_filename)


def is_supported_video_file(path_like: Union[str, Path, PurePosixPath]) -> bool:
    """Check whether a filename/path has a supported video extension."""
    return Path(str(path_like)).suffix.lower() in VIDEO_EXTENSIONS


def parse_movie_path(filepath: str) -> Optional[Tuple[int, int, int, str]]:
    """Parse a weekly movie path inside ~/oktv/weekly/<weekday>/HH-MM/file."""
    path = PurePosixPath(filepath)
    parts = path.parts

    try:
        oktv_index = parts.index(OKTV_ROOT_NAME)
    except ValueError:
        return None

    if len(parts) != oktv_index + 5:
        return None
    if parts[oktv_index + 1] != WEEKLY_MOVIES_DIR_NAME:
        return None

    try:
        weekday = validate_weekday(int(parts[oktv_index + 2]))
        hour_part, minute_part = parts[oktv_index + 3].split("-", 1)
        hour, minute = validate_time(int(hour_part), int(minute_part))
    except (ValueError, IndexError):
        return None

    try:
        filename = validate_movie_filename(path.name)
    except ValueError:
        return None

    return weekday, hour, minute, filename

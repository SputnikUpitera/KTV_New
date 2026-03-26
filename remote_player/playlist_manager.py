"""
Playlist Manager for KTV daemon
Manages continuous background playlist playback
"""

import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class PlaylistManager:
    """
    Manages continuous playlist playback.
    Plays videos from a playlist when no scheduled content is playing.
    """

    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv', '.wmv', '.m4v'}

    def __init__(self, database, player, clips_path: str = '~/oktv/clips'):
        self.db = database
        self.player = player
        self.clips_path = Path(os.path.expanduser(clips_path))

        self.running = False
        self.system_paused = False
        self.user_paused = False
        self.paused = False
        self.shuffle_enabled = False
        self.loop_enabled = True
        self.playlist_thread: Optional[threading.Thread] = None
        self.control_event = threading.Event()

        self.current_playlist: Optional[dict] = None
        self.current_files: List[Path] = []
        self.current_index = -1
        self.current_playlist_file: Optional[Path] = None

        self.pending_index_override: Optional[int] = None
        self.pending_index_from_history = False
        self.play_history: List[int] = []
        self.history_cursor = -1
        self.shuffle_pool: List[int] = []
        self.state_lock = threading.Lock()

        self.clips_path.mkdir(parents=True, exist_ok=True)
        logger.info("PlaylistManager initialized")

    def start(self):
        """Start the playlist manager."""
        if self.running:
            logger.warning("PlaylistManager already running")
            return

        self.running = True
        self.reload_active_playlist()
        self.playlist_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playlist_thread.start()
        self.control_event.set()
        logger.info("PlaylistManager started")

    def stop(self):
        """Stop the playlist manager."""
        if not self.running:
            return

        self.running = False
        self.control_event.set()
        if self.playlist_thread and self.playlist_thread.is_alive():
            self.playlist_thread.join(timeout=2)

        if self.player.has_media():
            self.player.stop()

        logger.info("PlaylistManager stopped")

    def pause(self):
        """Pause playlist playback for a scheduled movie."""
        if not self.running:
            return

        logger.info("Pausing playlist playback")
        with self.state_lock:
            self.system_paused = True
            self._update_paused_flag_locked()
            self.current_playlist_file = None

        if self.player.has_media():
            self.player.stop()
        self.control_event.set()

    def resume(self):
        """Resume playlist playback after scheduled content."""
        if not self.running:
            return

        logger.info("Resuming playlist playback")
        with self.state_lock:
            self.system_paused = False
            self._update_paused_flag_locked()
        self.control_event.set()

    def is_playing(self) -> bool:
        """Check if playlist is currently playing."""
        with self.state_lock:
            return (
                self.running
                and not self.system_paused
                and not self.user_paused
                and self.player.has_media()
                and not self.player.is_paused
                and self.current_playlist_file is not None
            )

    def has_active_clip(self) -> bool:
        """Check if a clip from the playlist is currently active."""
        with self.state_lock:
            return self.current_playlist_file is not None and self.player.has_media()

    def reload_active_playlist(self):
        """Reload the active playlist from the database."""
        active_playlist = self.db.get_active_playlist()
        old_current_file = self.current_playlist_file
        if active_playlist:
            folder_path = Path(active_playlist['folder_path'])
            current_files = self._scan_video_files(folder_path)
        else:
            current_files = self._scan_video_files(self.clips_path)

        stop_current = False
        with self.state_lock:
            self.current_playlist = active_playlist
            self.current_files = current_files
            self.pending_index_override = None
            self.pending_index_from_history = False
            self.shuffle_pool = []
            self._refill_shuffle_pool_locked(exclude_current=False)

            if old_current_file and old_current_file in current_files and self.player.has_media():
                self.current_playlist_file = old_current_file
                self.current_index = current_files.index(old_current_file)
            else:
                stop_current = old_current_file is not None and self.player.has_media()
                self.current_playlist_file = None
                if self.current_index >= len(current_files):
                    self.current_index = -1
                self.play_history = []
                self.history_cursor = -1

        if stop_current:
            self.player.stop()

        if active_playlist:
            logger.info("Loaded playlist '%s' with %s files", active_playlist['name'], len(current_files))
        elif current_files:
            logger.info("No active playlist, using default clips folder with %s files", len(current_files))
        else:
            logger.warning("No active playlist and no files in clips folder")

        self.control_event.set()

    def _scan_video_files(self, directory: Path) -> List[Path]:
        """Scan a directory for video files."""
        if not directory.exists() or not directory.is_dir():
            logger.warning("Directory does not exist: %s", directory)
            return []

        video_files = []
        try:
            for entry in directory.iterdir():
                if entry.is_file() and entry.suffix.lower() in self.VIDEO_EXTENSIONS:
                    video_files.append(entry)
        except Exception as exc:
            logger.error("Error scanning directory %s: %s", directory, exc)

        video_files.sort(key=lambda p: p.name.lower())
        return video_files

    def _playback_loop(self):
        """Continuously play clips when the playlist is active."""
        logger.info("Playlist playback loop started")

        while self.running:
            try:
                with self.state_lock:
                    paused = self.system_paused or self.user_paused
                    has_files = bool(self.current_files)
                    active_clip = self.current_playlist_file

                if active_clip and not self.player.has_media():
                    with self.state_lock:
                        self.current_playlist_file = None
                    self.control_event.set()
                    continue

                if paused or not has_files:
                    self.control_event.wait(0.5)
                    self.control_event.clear()
                    continue

                if self.player.has_media():
                    self.control_event.wait(0.2)
                    self.control_event.clear()
                    continue

                next_video = self._get_next_video()
                if not next_video:
                    self.control_event.wait(0.5)
                    self.control_event.clear()
                    continue

                logger.info("Playing from playlist: %s", next_video.name)
                success = self.player.play(str(next_video), fullscreen=True)
                if not success:
                    logger.error("Failed to play: %s", next_video.name)
                    with self.state_lock:
                        self.current_playlist_file = None
                    self.control_event.wait(1)
                    self.control_event.clear()
                    continue

                self.control_event.wait(0.2)
                self.control_event.clear()

            except Exception as exc:
                logger.error("Error in playlist playback loop: %s", exc, exc_info=True)
                self.control_event.wait(1)
                self.control_event.clear()

        logger.info("Playlist playback loop ended")

    def _get_next_video(self) -> Optional[Path]:
        """Resolve the next video file to play."""
        with self.state_lock:
            next_index = self._consume_next_index_locked()
            if next_index is None:
                return None
            self.current_index = next_index
            self.current_playlist_file = self.current_files[next_index]
            return self.current_playlist_file

    def get_active_playlist_name(self) -> Optional[str]:
        """Get the active playlist name."""
        with self.state_lock:
            return self.current_playlist['name'] if self.current_playlist else None

    def get_current_file(self) -> Optional[str]:
        """Get the currently active clip path."""
        with self.state_lock:
            if self.current_playlist_file and self.player.has_media():
                return str(self.current_playlist_file)
            return None

    def get_current_filename(self) -> Optional[str]:
        """Get the current clip filename."""
        current_file = self.get_current_file()
        return Path(current_file).name if current_file else None

    def get_next_file(self) -> Optional[str]:
        """Preview the next clip path in sequential mode."""
        with self.state_lock:
            if not self.current_files or self.shuffle_enabled:
                return None
            next_index = self._next_sequential_index_locked()
            if next_index is None:
                return None
            return str(self.current_files[next_index])

    def get_next_filename(self) -> Optional[str]:
        """Preview the next clip filename in sequential mode."""
        next_file = self.get_next_file()
        return Path(next_file).name if next_file else None

    def get_transport_status(self) -> dict:
        """Return transport flags for the API."""
        with self.state_lock:
            can_previous = self.history_cursor > 0
            return {
                'active_playlist': self.current_playlist['name'] if self.current_playlist else None,
                'user_paused': self.user_paused,
                'system_paused': self.system_paused,
                'paused': self.paused,
                'shuffle_enabled': self.shuffle_enabled,
                'loop_enabled': self.loop_enabled,
                'current_index': self.current_index,
                'has_files': bool(self.current_files),
                'can_previous': can_previous,
                'has_active_clip': self.current_playlist_file is not None and self.player.has_media(),
            }

    def toggle_play_pause(self) -> bool:
        """Toggle pause or playback for playlist clips."""
        with self.state_lock:
            if self.system_paused or not self.current_files:
                return False

        if self.player.has_media() and self.player.is_paused:
            return self.resume_playback()
        if self.player.has_media():
            return self.pause_playback()
        return self.start_playback()

    def start_playback(self) -> bool:
        """Start playback or resume a paused clip."""
        with self.state_lock:
            if self.system_paused or not self.current_files:
                return False
            if self.player.has_media() and self.player.is_paused:
                resume_active = True
            else:
                resume_active = False
                if self.pending_index_override is None:
                    if self.current_index >= 0:
                        self.pending_index_override = self.current_index
                        self.pending_index_from_history = True
                    else:
                        self.pending_index_override = 0
                        self.pending_index_from_history = False
            self.user_paused = False
            self._update_paused_flag_locked()

        if resume_active:
            success = self.player.resume()
            if not success:
                return False
        self.control_event.set()
        return True

    def pause_playback(self) -> bool:
        """Pause the current clip."""
        with self.state_lock:
            if not self.player.has_media() or self.player.is_paused:
                return False

        success = self.player.pause()
        if success:
            with self.state_lock:
                self.user_paused = True
                self._update_paused_flag_locked()
            self.control_event.set()
        return success

    def resume_playback(self) -> bool:
        """Resume the paused clip."""
        with self.state_lock:
            if self.system_paused or not self.current_files:
                return False
            has_paused_clip = self.current_playlist_file is not None and self.player.has_media() and self.player.is_paused
            self.user_paused = False
            self._update_paused_flag_locked()

        if has_paused_clip:
            success = self.player.resume()
            if not success:
                return False
        self.control_event.set()
        return True

    def stop_playback(self) -> bool:
        """Stop the current clip and stay paused until resumed."""
        with self.state_lock:
            if not self.current_files:
                return False
            if self.current_index >= 0:
                self.pending_index_override = self.current_index
                self.pending_index_from_history = True
            self.user_paused = True
            self._update_paused_flag_locked()
            if self.current_playlist_file is None and 0 <= self.current_index < len(self.current_files):
                self.current_playlist_file = self.current_files[self.current_index]

        if self.player.has_media():
            self.player.stop()
        with self.state_lock:
            self.current_playlist_file = None
        self.control_event.set()
        return True

    def play_next(self) -> bool:
        """Skip to the next clip and start it immediately."""
        with self.state_lock:
            if self.system_paused or not self.current_files:
                return False
            target = self._resolve_explicit_next_index_locked()
            if target is None:
                return False
            self.pending_index_override = target
            self.pending_index_from_history = False
            self.user_paused = False
            self._update_paused_flag_locked()
            self.current_playlist_file = None

        if self.player.has_media():
            self.player.stop()
        self.control_event.set()
        return True

    def play_playlist_file(self, filename: str) -> bool:
        """Play the requested file immediately, outside the normal queue order."""
        target_name = Path(filename).name
        with self.state_lock:
            if self.system_paused or not self.current_files:
                return False

            target = next((index for index, path in enumerate(self.current_files) if path.name == target_name), None)
            if target is None:
                return False

            self.pending_index_override = target
            self.pending_index_from_history = False
            self.user_paused = False
            self._update_paused_flag_locked()
            self.current_playlist_file = None
            if self.shuffle_enabled and target in self.shuffle_pool:
                self.shuffle_pool.remove(target)

        if self.player.has_media():
            self.player.stop()
        self.control_event.set()
        return True

    def play_previous(self) -> bool:
        """Return to the previous clip in playback history."""
        with self.state_lock:
            if self.system_paused or not self.current_files:
                return False
            target = self._previous_history_index_locked()
            if target is None:
                return False
            self.pending_index_override = target
            self.pending_index_from_history = True
            self.user_paused = False
            self._update_paused_flag_locked()
            self.current_playlist_file = None

        if self.player.has_media():
            self.player.stop()
        self.control_event.set()
        return True

    def toggle_shuffle(self) -> bool:
        """Toggle random playback mode."""
        with self.state_lock:
            self.shuffle_enabled = not self.shuffle_enabled
            self._refill_shuffle_pool_locked(exclude_current=True)
            enabled = self.shuffle_enabled
        self.control_event.set()
        return enabled

    def toggle_loop(self) -> bool:
        """Toggle playlist loop mode."""
        with self.state_lock:
            self.loop_enabled = not self.loop_enabled
            enabled = self.loop_enabled
        self.control_event.set()
        return enabled

    def _consume_next_index_locked(self) -> Optional[int]:
        """Resolve the next clip index and update history."""
        if not self.current_files:
            return None

        if self.pending_index_override is not None:
            target = self.pending_index_override
            from_history = self.pending_index_from_history
            self.pending_index_override = None
            self.pending_index_from_history = False
            if from_history:
                if self.history_cursor == -1 and self.play_history:
                    try:
                        self.history_cursor = len(self.play_history) - 1 - self.play_history[::-1].index(target)
                    except ValueError:
                        self.history_cursor = len(self.play_history) - 1
            else:
                self._record_history_locked(target)
            return target

        if self.shuffle_enabled:
            target = self._random_next_index_locked()
        else:
            target = self._next_sequential_index_locked()

        if target is None:
            self.user_paused = True
            self._update_paused_flag_locked()
            return None

        self._record_history_locked(target)
        return target

    def _resolve_explicit_next_index_locked(self) -> Optional[int]:
        """Compute the next index for a manual skip."""
        if self.shuffle_enabled:
            return self._random_next_index_locked(avoid_index=self._next_sequential_index_locked())
        return self._next_sequential_index_locked()

    def _next_sequential_index_locked(self) -> Optional[int]:
        """Compute the next sequential index."""
        if not self.current_files:
            return None

        if self.current_index < 0:
            return 0

        next_index = self.current_index + 1
        if next_index < len(self.current_files):
            return next_index
        if self.loop_enabled:
            return 0
        return None

    def _random_next_index_locked(self, avoid_index: Optional[int] = None) -> Optional[int]:
        """Pick the next random index."""
        if not self.current_files:
            return None

        if len(self.current_files) == 1:
            if self.current_index < 0:
                return 0
            return 0 if self.loop_enabled else None

        if not self.shuffle_pool:
            if not self.loop_enabled and self.current_index >= 0:
                return None
            self._refill_shuffle_pool_locked(exclude_current=True)

        if not self.shuffle_pool:
            return None

        candidates = list(self.shuffle_pool)
        if (
            avoid_index is not None
            and len(candidates) > 1
            and avoid_index in candidates
        ):
            candidates.remove(avoid_index)

        target = random.choice(candidates)
        self.shuffle_pool.remove(target)
        return target

    def _previous_history_index_locked(self) -> Optional[int]:
        """Move backwards through the actual playback history."""
        if not self.play_history:
            return None

        if self.history_cursor == -1:
            self.history_cursor = len(self.play_history) - 1

        if self.history_cursor <= 0:
            return None

        self.history_cursor -= 1
        return self.play_history[self.history_cursor]

    def _record_history_locked(self, index: int):
        """Append a new real playback event to history."""
        if self.history_cursor < len(self.play_history) - 1:
            self.play_history = self.play_history[:self.history_cursor + 1]
        self.play_history.append(index)
        self.history_cursor = len(self.play_history) - 1

    def _refill_shuffle_pool_locked(self, exclude_current: bool):
        """Rebuild the remaining random-order pool."""
        self.shuffle_pool = list(range(len(self.current_files)))
        if exclude_current and len(self.shuffle_pool) > 1 and self.current_index in self.shuffle_pool:
            self.shuffle_pool.remove(self.current_index)

    def _update_paused_flag_locked(self):
        """Keep the legacy paused attribute in sync."""
        self.paused = self.system_paused or self.user_paused


# Test functionality
if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    
    from storage.database import Database
    from player import Player
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create test database in memory
    db = Database(':memory:')
    
    # Create test playlist
    playlist_id = db.create_playlist('Test Playlist', '/opt/ktv/media/clips')
    db.set_active_playlist(playlist_id)
    
    # Create player
    player = Player()
    
    # Create playlist manager
    pm = PlaylistManager(db, player)
    
    print("Starting playlist manager...")
    pm.start()
    
    print("Playlist manager running. Press Ctrl+C to stop...")
    print(f"Active playlist: {pm.get_active_playlist_name()}")
    print(f"Files in playlist: {len(pm.current_files)}")
    
    try:
        while True:
            time.sleep(5)
            status = "Playing" if pm.is_playing() else "Paused" if pm.paused else "Idle"
            print(f"Status: {status}, Current: {pm.get_current_file() or 'None'}")
    except KeyboardInterrupt:
        print("\nStopping...")
        pm.stop()

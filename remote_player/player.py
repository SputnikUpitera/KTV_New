"""
Media player wrapper built on top of libVLC.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import vlc

logger = logging.getLogger(__name__)


class Player:
    """VLC media player wrapper using libVLC/python-vlc."""
    
    def __init__(
        self,
        vlc_path: str = '/usr/bin/vlc',
        display: str = ':0',
        avcodec_hw: str = 'any',
        video_output: str = 'xcb_x11',
        avcodec_threads: int = 2,
        file_caching_ms: int = 1000,
        network_caching_ms: int = 1500,
        enable_frame_skip: bool = True,
        extra_vlc_args: Optional[List[str]] = None,
    ):
        self.vlc_path = vlc_path
        self.display = display
        self.avcodec_hw = (avcodec_hw or '').strip()
        self.video_output = (video_output or '').strip()
        self.avcodec_threads = max(0, int(avcodec_threads))
        self.file_caching_ms = max(0, int(file_caching_ms))
        self.network_caching_ms = max(0, int(network_caching_ms))
        self.enable_frame_skip = enable_frame_skip
        self.extra_vlc_args = list(extra_vlc_args or [])
        self.instance: Optional[vlc.Instance] = None
        self.media_player: Optional[vlc.MediaPlayer] = None
        self._fallback_profile_active = False
        self.current_media = None
        self.current_file: Optional[str] = None
        self.is_playing = False
        self.is_paused = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.playback_ended_callback: Optional[Callable] = None
        self.callback_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.playback_generation = 0
        self.stop_requested_generation: Optional[int] = None
    
    def set_playback_ended_callback(self, callback: Optional[Callable[[str], None]] = None):
        """Set callback to be called when playback ends"""
        with self.callback_lock:
            self.playback_ended_callback = callback
    
    def play(self, filepath: str, fullscreen: bool = True) -> bool:
        """
        Play a video file
        
        Args:
            filepath: Path to video file
            fullscreen: Whether to play in fullscreen mode
            
        Returns:
            True if playback started successfully
        """
        # Stop current playback if any
        if self.is_playing:
            logger.info("Stopping current playback before starting new one")
            self.stop()
        
        # Check if file exists
        if not Path(filepath).exists():
            logger.error(f"File not found: {filepath}")
            return False
        
        logger.info("Starting VLC playback: %s", filepath)
        if self._start_playback(filepath, fullscreen):
            return True

        if not self._fallback_profile_active:
            logger.warning(
                "Configured libVLC profile failed for %s; retrying with legacy compatibility profile",
                filepath,
            )
            self._fallback_profile_active = True
            self._reset_backend()
            if self._start_playback(filepath, fullscreen):
                logger.warning("Playback recovered with legacy libVLC profile")
                return True

        return False
    
    def stop(self) -> bool:
        """Stop current playback"""
        if not self.has_media():
            return False
        
        try:
            logger.info("Stopping playback")
            with self.state_lock:
                generation = self.playback_generation
                stopped_file = self.current_file
                self.stop_requested_generation = generation

            if self.media_player:
                self.media_player.stop()

            self._finalize_playback(generation, invoke_callback=False)
            logger.info("Playback stopped: %s", Path(stopped_file).name if stopped_file else 'unknown')
            return True
            
        except Exception as e:
            logger.error("Error stopping playback: %s", e, exc_info=True)
            return False
    
    def _monitor_playback(self, generation: int, filepath: str):
        """Monitor libVLC state changes until playback completes."""
        while True:
            with self.state_lock:
                if generation != self.playback_generation or self.current_file != filepath:
                    return
                active = self.current_file is not None
            if not active or not self.media_player:
                return

            try:
                state = self.media_player.get_state()
            except Exception as exc:
                logger.error("Could not query VLC state for %s: %s", filepath, exc)
                self._finalize_playback(generation, invoke_callback=True)
                return

            if state == vlc.State.Ended:
                logger.info("Playback finished normally: %s", Path(filepath).name)
                self._finalize_playback(generation, invoke_callback=True)
                return
            if state == vlc.State.Error:
                logger.error("Playback failed during runtime: %s", Path(filepath).name)
                self._finalize_playback(generation, invoke_callback=True)
                return
            if state == vlc.State.Stopped:
                with self.state_lock:
                    invoke_callback = self.stop_requested_generation != generation
                self._finalize_playback(generation, invoke_callback=invoke_callback)
                return

            with self.state_lock:
                if generation == self.playback_generation:
                    self.is_paused = state == vlc.State.Paused
                    self.is_playing = state not in (
                        vlc.State.NothingSpecial,
                        vlc.State.Stopped,
                        vlc.State.Ended,
                        vlc.State.Error,
                    ) and not self.is_paused

            time.sleep(0.2)
    
    def get_status(self) -> dict:
        """Get current player status"""
        with self.state_lock:
            current_file = self.current_file
            return {
                'is_playing': self.is_playing,
                'is_paused': self.is_paused,
                'can_pause': current_file is not None,
                'current_file': current_file,
                'filename': Path(current_file).name if current_file else None
            }
    
    def is_busy(self) -> bool:
        """Check if player is currently playing"""
        return self.has_media()

    def has_media(self) -> bool:
        """Check whether a media item is currently loaded."""
        with self.state_lock:
            return self.current_file is not None

    def pause(self) -> bool:
        """Pause the current playback without losing position."""
        with self.state_lock:
            if not self.current_file or self.is_paused:
                return False
        if not self.media_player:
            return False
        self.media_player.set_pause(1)
        with self.state_lock:
            self.is_paused = True
            self.is_playing = False
        logger.info("Playback paused")
        return True

    def resume(self) -> bool:
        """Resume the current playback from the paused position."""
        with self.state_lock:
            if not self.current_file or not self.is_paused:
                return False
        if not self.media_player:
            return False
        self.media_player.set_pause(0)
        with self.state_lock:
            self.is_paused = False
            self.is_playing = True
        logger.info("Playback resumed")
        return True

    def _start_playback(self, filepath: str, fullscreen: bool) -> bool:
        """Try to start playback using the currently selected libVLC profile."""
        generation = None
        try:
            self._ensure_player()
            media = self.instance.media_new(str(filepath))

            with self.state_lock:
                self.playback_generation += 1
                generation = self.playback_generation
                self.stop_requested_generation = None
                self.current_media = media
                self.current_file = filepath
                self.is_playing = False
                self.is_paused = False

            self.media_player.set_media(media)
            result = self.media_player.play()
            if result == -1:
                logger.error("libVLC rejected playback start for %s", filepath)
                self._finalize_playback(generation, invoke_callback=False)
                self._reset_backend()
                return False

            time.sleep(0.25)
            state = self.media_player.get_state()
            if state == vlc.State.Error:
                logger.error("libVLC entered error state during startup for %s", filepath)
                self._finalize_playback(generation, invoke_callback=False)
                self._reset_backend()
                return False

            if fullscreen:
                try:
                    self.media_player.set_fullscreen(True)
                except Exception as exc:
                    logger.debug("Could not enable fullscreen for %s: %s", filepath, exc)

            with self.state_lock:
                if generation == self.playback_generation and self.current_file == filepath:
                    self.is_paused = state == vlc.State.Paused
                    self.is_playing = not self.is_paused

            self.monitor_thread = threading.Thread(
                target=self._monitor_playback,
                args=(generation, filepath),
                daemon=True
            )
            self.monitor_thread.start()

            profile_name = 'legacy' if self._fallback_profile_active else 'configured'
            logger.info("Playback started via libVLC (%s profile): %s", profile_name, Path(filepath).name)
            return True

        except Exception as e:
            logger.error("Failed to start playback: %s", e, exc_info=True)
            if generation is not None:
                self._finalize_playback(generation, invoke_callback=False)
            else:
                self._clear_state()
            self._reset_backend()
            return False

    def _ensure_player(self):
        """Create libVLC objects lazily."""
        if self.instance and self.media_player:
            return

        os.environ['DISPLAY'] = self.display
        if not os.environ.get('XDG_RUNTIME_DIR'):
            runtime_dir = f"/run/user/{os.getuid()}"
            if Path(runtime_dir).exists():
                os.environ['XDG_RUNTIME_DIR'] = runtime_dir
        instance_args = self._build_instance_args()
        logger.info("Initializing libVLC with options: %s", instance_args)
        self.instance = vlc.Instance(*instance_args)
        if self.instance is None:
            raise RuntimeError(f"libVLC initialization failed for options: {instance_args}")

        self.media_player = self.instance.media_player_new()
        if self.media_player is None:
            raise RuntimeError("libVLC created no media player instance")

    def _build_instance_args(self) -> List[str]:
        """Build VLC options with a performance-oriented default profile."""
        if self._fallback_profile_active:
            return [
                '--quiet',
                '--no-video-title-show',
                '--no-osd',
                '--no-playlist-enqueue',
            ]

        args = [
            '--quiet',
            '--no-dbus',
            '--no-snapshot-preview',
            '--no-sub-autodetect-file',
            '--no-video-title-show',
            '--no-osd',
            '--no-playlist-enqueue',
            f'--file-caching={self.file_caching_ms}',
            f'--network-caching={self.network_caching_ms}',
        ]

        avcodec_hw = self.avcodec_hw.lower()
        if avcodec_hw in {'none', 'off', 'disabled', 'false', 'software'}:
            args.append('--avcodec-hw=none')
        elif avcodec_hw:
            args.append(f'--avcodec-hw={self.avcodec_hw}')

        if self.video_output:
            args.append(f'--vout={self.video_output}')

        if self.avcodec_threads > 0:
            args.append(f'--avcodec-threads={self.avcodec_threads}')

        if self.enable_frame_skip:
            args.extend(['--drop-late-frames', '--skip-frames'])

        args.extend(self.extra_vlc_args)
        return args

    def _reset_backend(self):
        """Release libVLC objects so the next attempt starts cleanly."""
        media_player = self.media_player
        instance = self.instance
        self.media_player = None
        self.instance = None

        if media_player is not None:
            try:
                media_player.release()
            except Exception:
                pass

        if instance is not None:
            try:
                instance.release()
            except Exception:
                pass

    def _finalize_playback(self, generation: int, invoke_callback: bool):
        """Clear state for a finished playback session."""
        with self.state_lock:
            if generation != self.playback_generation:
                return
            filepath = self.current_file
            self.current_file = None
            self.current_media = None
            self.is_playing = False
            self.is_paused = False
            self.stop_requested_generation = None

        if invoke_callback and filepath:
            with self.callback_lock:
                callback = self.playback_ended_callback
            if callback:
                try:
                    callback(filepath)
                except Exception as exc:
                    logger.error("Error in playback ended callback: %s", exc, exc_info=True)

    def _clear_state(self):
        """Reset in-memory playback state."""
        with self.state_lock:
            self.current_file = None
            self.current_media = None
            self.is_playing = False
            self.is_paused = False
            self.stop_requested_generation = None


# Test functionality
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    player = Player()
    
    def on_playback_ended(filepath):
        print(f"Callback: Playback ended for {filepath}")
    
    player.set_playback_ended_callback(on_playback_ended)
    
    # Test with a sample file (if it exists)
    test_file = "/opt/ktv/media/test.mp4"
    if Path(test_file).exists():
        print(f"Testing playback with {test_file}")
        player.play(test_file)
        
        # Wait for playback
        time.sleep(5)
        
        # Stop playback
        player.stop()
    else:
        print(f"Test file not found: {test_file}")
    
    print(f"Status: {player.get_status()}")

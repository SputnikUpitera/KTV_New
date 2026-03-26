"""
Media player wrapper built on top of libVLC.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import vlc

logger = logging.getLogger(__name__)


class Player:
    """VLC media player wrapper using libVLC/python-vlc."""
    
    def __init__(self, vlc_path: str = '/usr/bin/vlc', display: str = ':0'):
        self.vlc_path = vlc_path
        self.display = display
        self.instance: Optional[vlc.Instance] = None
        self.media_player: Optional[vlc.MediaPlayer] = None
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
        
        try:
            logger.info("Starting VLC playback: %s", filepath)
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
                return False

            time.sleep(0.25)
            state = self.media_player.get_state()
            if state == vlc.State.Error:
                logger.error("libVLC entered error state during startup for %s", filepath)
                self._finalize_playback(generation, invoke_callback=False)
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

            logger.info("Playback started via libVLC: %s", Path(filepath).name)
            return True

        except Exception as e:
            logger.error("Failed to start playback: %s", e, exc_info=True)
            self._clear_state()
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
        return {
            'is_playing': self.is_playing,
            'is_paused': self.is_paused,
            'can_pause': self.has_media(),
            'current_file': self.current_file,
            'filename': Path(self.current_file).name if self.current_file else None
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

    def _ensure_player(self):
        """Create libVLC objects lazily."""
        if self.instance and self.media_player:
            return

        os.environ['DISPLAY'] = self.display
        self.instance = vlc.Instance(
            '--quiet',
            '--no-video-title-show',
            '--no-osd',
            '--no-playlist-enqueue',
        )
        self.media_player = self.instance.media_player_new()

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

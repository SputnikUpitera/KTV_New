"""
Media player wrapper for VLC
Handles video playback with process management
"""

import subprocess
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable
import signal
import os

logger = logging.getLogger(__name__)


class Player:
    """VLC media player wrapper"""
    
    def __init__(self, vlc_path: str = '/usr/bin/vlc', display: str = ':0'):
        self.vlc_path = vlc_path
        self.display = display  # X11 display for VLC
        self.current_process: Optional[subprocess.Popen] = None
        self.current_file: Optional[str] = None
        self.is_playing = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.playback_ended_callback: Optional[Callable] = None
        self.callback_lock = threading.Lock()
    
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
        
        # Build VLC command
        cmd = [
            self.vlc_path,
            '--play-and-exit',      # Exit after playback
            '--no-video-title-show', # Don't show filename overlay
            '--quiet',               # Minimal output
        ]
        
        if fullscreen:
            cmd.append('--fullscreen')  # Fullscreen
        
        # Additional options for reliable playback
        cmd.extend([
            '--no-osd',              # No on-screen display
            '--no-playlist-enqueue', # Don't enqueue in playlist
            '--one-instance',        # Use single instance
        ])
        
        cmd.append(filepath)
        
        # Set up environment with DISPLAY
        env = os.environ.copy()
        env['DISPLAY'] = self.display
        
        try:
            logger.info(f"Starting VLC playback: {filepath}")
            
            # Start VLC process with DISPLAY set
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                env=env
            )
            
            self.current_file = filepath
            self.is_playing = True
            
            # Start monitoring thread
            self.monitor_thread = threading.Thread(
                target=self._monitor_playback,
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info(f"Playback started: {Path(filepath).name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start playback: {e}")
            self.is_playing = False
            self.current_file = None
            return False
    
    def stop(self) -> bool:
        """Stop current playback"""
        if not self.is_playing or not self.current_process:
            return False
        
        try:
            logger.info("Stopping playback")
            
            # Try graceful termination first
            self.current_process.terminate()
            
            # Wait up to 2 seconds for process to end
            try:
                self.current_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate
                logger.warning("Force killing VLC process")
                self.current_process.kill()
                self.current_process.wait()
            
            self.is_playing = False
            stopped_file = self.current_file
            self.current_file = None
            self.current_process = None
            
            logger.info(f"Playback stopped: {Path(stopped_file).name if stopped_file else 'unknown'}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping playback: {e}")
            return False
    
    def _monitor_playback(self):
        """Monitor playback process and detect when it ends"""
        if not self.current_process:
            return
        
        filepath = self.current_file
        
        # Wait for process to end
        return_code = self.current_process.wait()
        
        # Update state
        self.is_playing = False
        self.current_file = None
        self.current_process = None
        
        if return_code == 0:
            logger.info(f"Playback finished normally: {Path(filepath).name if filepath else 'unknown'}")
        else:
            logger.warning(f"Playback ended with code {return_code}: {Path(filepath).name if filepath else 'unknown'}")
        
        # Call callback if set
        with self.callback_lock:
            callback = self.playback_ended_callback

        if callback and filepath:
            try:
                callback(filepath)
            except Exception as e:
                logger.error(f"Error in playback ended callback: {e}")
    
    def get_status(self) -> dict:
        """Get current player status"""
        return {
            'is_playing': self.is_playing,
            'current_file': self.current_file,
            'filename': Path(self.current_file).name if self.current_file else None
        }
    
    def is_busy(self) -> bool:
        """Check if player is currently playing"""
        return self.is_playing


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

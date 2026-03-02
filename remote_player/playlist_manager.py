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
    Manages continuous playlist playback
    Plays videos from a playlist when no scheduled content is playing
    """
    
    # Supported video formats
    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv', '.wmv', '.m4v'}
    
    def __init__(self, database, player, clips_path: str = '~/clips'):
        """
        Initialize playlist manager
        
        Args:
            database: Database instance
            player: Player instance
            clips_path: Path to clips folder
        """
        self.db = database
        self.player = player
        self.clips_path = Path(os.path.expanduser(clips_path))
        
        self.running = False
        self.paused = False
        self.playlist_thread: Optional[threading.Thread] = None
        
        self.current_playlist: Optional[dict] = None
        self.current_files: List[Path] = []
        self.current_index = 0
        
        # Ensure media directories exist
        self.clips_path.mkdir(parents=True, exist_ok=True)
        
        logger.info("PlaylistManager initialized")
    
    def start(self):
        """Start the playlist manager"""
        if self.running:
            logger.warning("PlaylistManager already running")
            return
        
        self.running = True
        
        # Load active playlist
        self.reload_active_playlist()
        
        # Start playback thread
        self.playlist_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playlist_thread.start()
        
        logger.info("PlaylistManager started")
    
    def stop(self):
        """Stop the playlist manager"""
        if not self.running:
            return
        
        self.running = False
        
        # Wait for thread to finish
        if self.playlist_thread and self.playlist_thread.is_alive():
            self.playlist_thread.join(timeout=2)
        
        logger.info("PlaylistManager stopped")
    
    def pause(self):
        """Pause playlist playback (for scheduled content)"""
        if not self.running:
            return
        
        logger.info("Pausing playlist playback")
        self.paused = True
        
        # Stop current playback if it's from the playlist
        if self.player.is_playing:
            self.player.stop()
    
    def resume(self):
        """Resume playlist playback (after scheduled content)"""
        if not self.running:
            return
        
        logger.info("Resuming playlist playback")
        self.paused = False
    
    def is_playing(self) -> bool:
        """Check if playlist is currently playing"""
        return self.running and not self.paused and self.player.is_playing
    
    def reload_active_playlist(self):
        """Reload the active playlist from database"""
        self.current_playlist = self.db.get_active_playlist()
        
        if self.current_playlist:
            folder_path = Path(self.current_playlist['folder_path'])
            self.current_files = self._scan_video_files(folder_path)
            self.current_index = 0
            
            logger.info(f"Loaded playlist '{self.current_playlist['name']}' with {len(self.current_files)} files")
        else:
            # No active playlist, scan default clips folder
            self.current_files = self._scan_video_files(self.clips_path)
            self.current_index = 0
            
            if self.current_files:
                logger.info(f"No active playlist, using default clips folder with {len(self.current_files)} files")
            else:
                logger.warning("No active playlist and no files in clips folder")
    
    def _scan_video_files(self, directory: Path) -> List[Path]:
        """
        Scan directory for video files
        
        Args:
            directory: Directory to scan
            
        Returns:
            List of video file paths
        """
        if not directory.exists() or not directory.is_dir():
            logger.warning(f"Directory does not exist: {directory}")
            return []
        
        video_files = []
        
        try:
            for entry in directory.iterdir():
                if entry.is_file() and entry.suffix.lower() in self.VIDEO_EXTENSIONS:
                    video_files.append(entry)
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
        
        # Sort files alphabetically
        video_files.sort(key=lambda p: p.name.lower())
        
        return video_files
    
    def _playback_loop(self):
        """
        Main playback loop
        Continuously plays videos from the playlist
        """
        logger.info("Playlist playback loop started")
        
        while self.running:
            try:
                # Check if we should be playing
                if self.paused or not self.current_files:
                    time.sleep(1)
                    continue
                
                # Check if player is already playing something
                if self.player.is_playing:
                    time.sleep(1)
                    continue
                
                # Get next video to play
                video_file = self._get_next_video()
                
                if video_file and video_file.exists():
                    logger.info(f"Playing from playlist: {video_file.name}")
                    
                    # Play the video
                    success = self.player.play(str(video_file), fullscreen=True)
                    
                    if success:
                        # Wait for playback to complete
                        while self.player.is_playing and self.running and not self.paused:
                            time.sleep(1)
                    else:
                        logger.error(f"Failed to play: {video_file.name}")
                        time.sleep(2)
                else:
                    # No valid video file, wait and retry
                    logger.warning("No valid video file to play")
                    time.sleep(5)
                    
                    # Try reloading playlist
                    self.reload_active_playlist()
                
            except Exception as e:
                logger.error(f"Error in playlist playback loop: {e}", exc_info=True)
                time.sleep(5)
        
        logger.info("Playlist playback loop ended")
    
    def _get_next_video(self) -> Optional[Path]:
        """
        Get the next video file to play
        
        Returns:
            Path to next video file or None
        """
        if not self.current_files:
            return None
        
        # Get current file
        video_file = self.current_files[self.current_index]
        
        # Move to next index (loop around)
        self.current_index = (self.current_index + 1) % len(self.current_files)
        
        return video_file
    
    def get_active_playlist_name(self) -> Optional[str]:
        """Get the name of the active playlist"""
        if self.current_playlist:
            return self.current_playlist['name']
        return None
    
    def get_current_file(self) -> Optional[str]:
        """Get the currently playing file from playlist"""
        if self.player.is_playing and not self.paused:
            return self.player.current_file
        return None


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

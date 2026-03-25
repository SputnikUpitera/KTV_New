#!/usr/bin/env python3
"""
KTV Media Player Daemon
Main daemon process that coordinates all components
"""

import sys
import signal
import logging
import json
import time
import shutil
from pathlib import Path
from typing import Dict, Any, List

import os

from storage.database import Database
from api_server import APIServer
from player import Player
from scheduler import Scheduler
from playlist_manager import PlaylistManager
from time_controller import TimeController
from ktv_paths import (
    build_movie_file_path,
    build_playlist_directory,
    parse_movie_path,
)


class KTVDaemon:
    """Main daemon class"""
    
    def __init__(self, config_path: str = '/etc/ktv/config.json'):
        self.config = self._load_config(config_path)
        self.running = False
        
        # Expand ~ in paths before using them
        for key in ('media_base_path', 'clips_folder', 'database_path', 'log_path'):
            if key in self.config and '~' in str(self.config[key]):
                self.config[key] = os.path.expanduser(self.config[key])
        
        # Initialize logging (after path expansion)
        self._setup_logging()
        
        # Initialize components
        self.db = Database(self.config['database_path'])
        self.player = Player(
            vlc_path=self.config.get('vlc_path', '/usr/bin/vlc'),
            display=self.config.get('display', ':0')
        )
        self.api_server = APIServer(port=self.config['api_port'])
        
        # These will be initialized in start()
        self.scheduler = None
        self.playlist_manager = None
        self.time_controller = None
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("KTV Daemon initialized")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from file"""
        default_config = {
            'api_port': 8888,
            'media_base_path': '~/oktv',
            'clips_folder': '~/oktv/clips',
            'database_path': '/var/lib/ktv/schedule.db',
            'log_path': '/var/log/ktv/daemon.log',
            'broadcast_start': '06:00',
            'broadcast_end': '22:00',
            'vlc_path': '/usr/bin/vlc',
            'display': ':0'
        }
        
        try:
            if Path(config_path).exists():
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
            print("Using default configuration")
        
        return default_config
    
    def _setup_logging(self):
        """Setup logging configuration.
        Systemd captures stdout/stderr to the log file via StandardOutput/StandardError,
        so we only need a StreamHandler here. This avoids PermissionError when the
        log file is owned by root but daemon runs as ktv user.
        """
        handlers = [logging.StreamHandler()]
        
        # Try to add file handler, but don't fail if permissions deny it
        log_path = Path(self.config['log_path'])
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_path))
        except (PermissionError, OSError) as e:
            print(f"Warning: Cannot write to log file {log_path}: {e}")
            print("Logging to stdout only (captured by systemd)")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=handlers
        )
        
        global logger
        logger = logging.getLogger(__name__)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)
    
    def _register_api_handlers(self):
        """Register API command handlers"""
        
        # Schedule commands
        self.api_server.register_handler('add_schedule', self._handle_add_schedule)
        self.api_server.register_handler('remove_schedule', self._handle_remove_schedule)
        self.api_server.register_handler('toggle_schedule', self._handle_toggle_schedule)
        self.api_server.register_handler('list_schedules', self._handle_list_schedules)
        self.api_server.register_handler('get_schedule', self._handle_get_schedule)
        self.api_server.register_handler('update_schedule', self._handle_update_schedule)
        self.api_server.register_handler('sync_schedules', self._handle_sync_schedules)
        
        # Playlist commands
        self.api_server.register_handler('create_playlist', self._handle_create_playlist)
        self.api_server.register_handler('delete_playlist', self._handle_delete_playlist)
        self.api_server.register_handler('set_active_playlist', self._handle_set_active_playlist)
        self.api_server.register_handler('list_playlists', self._handle_list_playlists)
        self.api_server.register_handler('sync_playlists', self._handle_sync_playlists)
        
        # Status commands
        self.api_server.register_handler('get_status', self._handle_get_status)
        self.api_server.register_handler('ping', self._handle_ping)
        
        logger.info("API handlers registered")
    
    # API Handler Methods
    
    def _handle_add_schedule(self, params: Dict) -> Dict:
        """Handle add_schedule command"""
        schedule_id = self.db.add_schedule(
            month=params['month'],
            day=params['day'],
            hour=params['hour'],
            minute=params['minute'],
            filepath=params['filepath'],
            filename=params['filename'],
            category=params.get('category', 'movies')
        )
        
        # Reload scheduler if it exists
        if self.scheduler:
            self.scheduler.reload_schedules()
        
        return {'schedule_id': schedule_id}
    
    def _handle_remove_schedule(self, params: Dict) -> Dict:
        """Handle remove_schedule command"""
        success = self.db.remove_schedule(params['schedule_id'])
        
        # Reload scheduler if it exists
        if self.scheduler:
            self.scheduler.reload_schedules()
        
        return {'success': success}
    
    def _handle_toggle_schedule(self, params: Dict) -> Dict:
        """Handle toggle_schedule command"""
        success = self.db.toggle_schedule(
            params['schedule_id'],
            params['enabled']
        )
        
        # Reload scheduler if it exists
        if self.scheduler:
            self.scheduler.reload_schedules()
        
        return {'success': success}
    
    def _handle_list_schedules(self, params: Dict) -> Dict:
        """Handle list_schedules command"""
        schedules = self.db.list_schedules(
            enabled_only=params.get('enabled_only', False),
            category=params.get('category')
        )
        return {'schedules': schedules}
    
    def _handle_get_schedule(self, params: Dict) -> Dict:
        """Handle get_schedule command"""
        schedule = self.db.get_schedule(params['schedule_id'])
        return {'schedule': schedule}

    def _handle_update_schedule(self, params: Dict) -> Dict:
        """Handle update_schedule command."""
        schedule = self.db.get_schedule(params['schedule_id'])
        if not schedule:
            raise ValueError('Schedule not found')

        filename = schedule['filename']
        source_path = Path(schedule['filepath'])
        target_path = Path(
            build_movie_file_path(
                str(self.media_root.parent),
                params['month'],
                params['day'],
                params['hour'],
                params['minute'],
                filename
            )
        )

        move_result = self._move_media_file(source_path, target_path)
        if not move_result['success']:
            raise RuntimeError(move_result['error'])

        success = self.db.update_schedule(
            schedule_id=params['schedule_id'],
            month=params['month'],
            day=params['day'],
            hour=params['hour'],
            minute=params['minute'],
            filepath=str(target_path),
            filename=filename
        )
        self._reload_runtime_state()
        return {'success': success, 'filepath': str(target_path)}
    
    def _handle_create_playlist(self, params: Dict) -> Dict:
        """Handle create_playlist command"""
        playlist_id = self.db.create_playlist(
            name=params['name'],
            folder_path=params['folder_path']
        )
        if not self.db.get_active_playlist():
            self.db.set_active_playlist(playlist_id)
        self._reload_playlist_state()
        return {'playlist_id': playlist_id}
    
    def _handle_delete_playlist(self, params: Dict) -> Dict:
        """Handle delete_playlist command"""
        success = self.db.delete_playlist(params['playlist_id'])
        self._reload_playlist_state()
        return {'success': success}
    
    def _handle_set_active_playlist(self, params: Dict) -> Dict:
        """Handle set_active_playlist command"""
        success = self.db.set_active_playlist(params['playlist_id'])
        self._reload_playlist_state()
        return {'success': success}
    
    def _handle_list_playlists(self, params: Dict) -> Dict:
        """Handle list_playlists command"""
        playlists = self.db.list_playlists()
        return {'playlists': playlists}

    def _handle_sync_schedules(self, params: Dict) -> Dict:
        """Handle schedule/database synchronization."""
        result = self.sync_schedules()
        self._reload_runtime_state()
        return result

    def _handle_sync_playlists(self, params: Dict) -> Dict:
        """Handle playlist/database synchronization."""
        result = self.sync_playlists()
        self._reload_playlist_state()
        return result
    
    def _handle_get_status(self, params: Dict) -> Dict:
        """Handle get_status command"""
        player_status = self.player.get_status()
        
        status = {
            'daemon_running': True,
            'player': player_status,
            'api_server_port': self.config['api_port'],
            'broadcast_hours': {
                'start': self.config['broadcast_start'],
                'end': self.config['broadcast_end']
            }
        }
        
        if self.time_controller:
            status['broadcasting_active'] = self.time_controller.is_broadcast_time()
        
        current_scheduled = self.scheduler.get_current_scheduled_playback() if self.scheduler else None

        if self.playlist_manager:
            status['playlist'] = {
                'active': self.playlist_manager.get_active_playlist_name(),
                'playing': self.playlist_manager.is_playing(),
                'current_file': self.playlist_manager.get_current_file(),
                'current_filename': self.playlist_manager.get_current_filename(),
                'next_file': self.playlist_manager.get_next_file(),
                'next_filename': self.playlist_manager.get_next_filename(),
            }

        if current_scheduled:
            status['current_playback'] = {
                'source': 'movie',
                'filename': current_scheduled['filename'],
                'filepath': current_scheduled['filepath'],
            }
        elif self.playlist_manager and self.playlist_manager.is_playing():
            status['current_playback'] = {
                'source': 'clip',
                'filename': self.playlist_manager.get_current_filename(),
                'filepath': self.playlist_manager.get_current_file(),
            }
        else:
            status['current_playback'] = {
                'source': None,
                'filename': None,
                'filepath': None,
            }

        status['next_clip'] = {
            'filename': self.playlist_manager.get_next_filename() if self.playlist_manager else None,
            'filepath': self.playlist_manager.get_next_file() if self.playlist_manager else None,
        }
        
        return status
    
    def _handle_ping(self, params: Dict) -> Dict:
        """Handle ping command"""
        return {
            'pong': True,
            'timestamp': time.time(),
            'version': '1.0.0'
        }
    
    def start(self):
        """Start the daemon"""
        logger.info("Starting KTV Daemon...")

        self.media_root = Path(self.config.get('media_base_path', os.path.expanduser('~/oktv')))
        self.clips_root = Path(self.config.get('clips_folder', os.path.expanduser('~/oktv/clips')))
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.clips_root.mkdir(parents=True, exist_ok=True)
        
        # Register API handlers
        self._register_api_handlers()

        self.sync_schedules()
        self.sync_playlists()
        
        # Start API server
        self.api_server.start()
        
        # Initialize playlist manager with clips folder
        clips_folder = self.config.get('clips_folder', os.path.expanduser('~/oktv/clips'))
        self.playlist_manager = PlaylistManager(self.db, self.player, clips_folder)
        self.playlist_manager.start()
        
        # Initialize scheduler
        self.scheduler = Scheduler(self.db, self.player, self.playlist_manager)
        self.scheduler.start()
        
        # Initialize time controller
        self.time_controller = TimeController(
            self.scheduler, self.playlist_manager,
            self.config['broadcast_start'], self.config['broadcast_end']
        )
        self.scheduler.set_broadcast_time_check(self.time_controller.is_broadcast_time)
        self.time_controller.start()
        
        self.running = True
        logger.info("KTV Daemon started successfully")
    
    def shutdown(self):
        """Shutdown the daemon"""
        if not self.running:
            return
        
        logger.info("Shutting down KTV Daemon...")
        self.running = False
        
        # Stop components in reverse order
        if self.time_controller:
            self.time_controller.stop()
        
        if self.playlist_manager:
            self.playlist_manager.stop()
        
        if self.scheduler:
            self.scheduler.stop()
        
        # Stop player
        if self.player.is_playing:
            self.player.stop()
        
        # Stop API server
        self.api_server.stop()
        
        logger.info("KTV Daemon shutdown complete")

    def _reload_runtime_state(self):
        """Reload scheduler and playlist state after backend changes."""
        if self.scheduler:
            self.scheduler.reload_schedules()
        self._reload_playlist_state()

    def _reload_playlist_state(self):
        """Reload playlist state after playlist changes."""
        if self.playlist_manager:
            self.playlist_manager.reload_active_playlist()

    def _move_media_file(self, source_path: Path, target_path: Path) -> Dict:
        """Move a media file to a canonical target path."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path == target_path:
            if not target_path.exists():
                return {'success': False, 'error': f'File not found: {target_path}'}
            return {'success': True}

        if source_path.exists():
            try:
                shutil.move(str(source_path), str(target_path))
                logger.info("Moved media file: %s -> %s", source_path, target_path)
                return {'success': True}
            except Exception as exc:
                return {'success': False, 'error': f'Could not move file: {exc}'}

        if target_path.exists():
            return {'success': True}

        return {'success': False, 'error': f'File not found: {source_path}'}

    def _is_video_file(self, path: Path) -> bool:
        """Check whether a path is a supported media file."""
        return path.is_file() and path.suffix.lower() in PlaylistManager.VIDEO_EXTENSIONS

    def _iter_movie_files(self) -> List[Path]:
        """Collect movie files under the canonical schedule root."""
        movie_files: List[Path] = []
        for file_path in self.media_root.rglob('*'):
            if self._is_video_file(file_path):
                movie_files.append(file_path)
        movie_files.sort(key=lambda item: str(item))
        return movie_files

    def sync_schedules(self) -> Dict:
        """Synchronize schedule rows with canonical movie directories."""
        self.media_root.mkdir(parents=True, exist_ok=True)

        imported = 0
        moved = 0
        ensured_dirs = 0

        schedules = self.db.list_schedules(category='movies')
        known_paths = {}
        home_dir = str(self.media_root.parent)

        for schedule in schedules:
            expected_path = Path(
                build_movie_file_path(
                    home_dir,
                    schedule['month'],
                    schedule['day'],
                    schedule['hour'],
                    schedule['minute'],
                    schedule['filename']
                )
            )
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            ensured_dirs += 1

            current_path = Path(schedule['filepath'])
            if current_path != expected_path:
                move_result = self._move_media_file(current_path, expected_path)
                if move_result.get('success'):
                    if current_path != expected_path and (current_path.exists() or expected_path.exists()):
                        moved += 1
                else:
                    logger.warning("Could not align schedule file %s: %s", current_path, move_result['error'])

            self.db.update_schedule(
                schedule_id=schedule['id'],
                month=schedule['month'],
                day=schedule['day'],
                hour=schedule['hour'],
                minute=schedule['minute'],
                filepath=str(expected_path),
                filename=expected_path.name
            )
            known_paths[str(expected_path)] = schedule['id']

        for file_path in self._iter_movie_files():
            file_key = str(file_path)
            if file_key in known_paths:
                continue

            parsed = parse_movie_path(file_key)
            if not parsed:
                continue

            month, day, hour, minute, filename = parsed
            schedule_id = self.db.add_schedule(
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                filepath=file_key,
                filename=filename,
                category='movies'
            )
            known_paths[file_key] = schedule_id
            imported += 1

        return {
            'success': True,
            'imported': imported,
            'moved': moved,
            'ensured_dirs': ensured_dirs,
        }

    def _migrate_default_clips(self) -> int:
        """Move loose clip files into a visible default playlist."""
        default_name = 'Основной'
        default_dir = Path(build_playlist_directory(str(self.clips_root.parent), default_name))
        default_dir.mkdir(parents=True, exist_ok=True)

        moved_files = 0
        for entry in self.clips_root.iterdir():
            if not self._is_video_file(entry):
                continue
            target_path = default_dir / entry.name
            if entry != target_path:
                shutil.move(str(entry), str(target_path))
                moved_files += 1

        if moved_files:
            self.db.ensure_playlist(default_name, str(default_dir))

        return moved_files

    def sync_playlists(self) -> Dict:
        """Synchronize playlist rows with canonical clip directories."""
        self.clips_root.mkdir(parents=True, exist_ok=True)

        created = 0
        updated = 0
        imported = 0
        moved_root_files = self._migrate_default_clips()

        playlists = self.db.list_playlists()
        known_names = {playlist['name'] for playlist in playlists}
        home_dir = str(self.clips_root.parent.parent)

        for playlist in playlists:
            current_dir = Path(playlist['folder_path'])
            expected_dir = Path(build_playlist_directory(home_dir, playlist['name']))
            should_move = current_dir != expected_dir and current_dir.exists() and not expected_dir.exists()
            if should_move:
                shutil.move(str(current_dir), str(expected_dir))
            expected_dir.mkdir(parents=True, exist_ok=True)

            if playlist['folder_path'] != str(expected_dir):
                self.db.update_playlist_folder(playlist['id'], str(expected_dir))
                updated += 1

        for entry in sorted(self.clips_root.iterdir(), key=lambda item: item.name.lower()):
            if not entry.is_dir():
                continue

            _, was_created = self.db.ensure_playlist(entry.name, str(entry))
            if was_created:
                created += 1
                known_names.add(entry.name)
            elif entry.name not in known_names:
                imported += 1

        refreshed_playlists = self.db.list_playlists()
        if refreshed_playlists and not self.db.get_active_playlist():
            self.db.set_active_playlist(refreshed_playlists[0]['id'])

        return {
            'success': True,
            'created': created,
            'updated': updated,
            'imported': imported,
            'moved_root_files': moved_root_files,
        }
    
    def run(self):
        """Main run loop"""
        self.start()
        
        try:
            # Keep the daemon running
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.shutdown()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='KTV Media Player Daemon')
    parser.add_argument('--config', default='/etc/ktv/config.json',
                       help='Path to configuration file')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    daemon = KTVDaemon(config_path=args.config)
    daemon.run()


if __name__ == '__main__':
    main()

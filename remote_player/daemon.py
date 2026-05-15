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
from datetime import datetime
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
    WEEKLY_MOVIES_DIR_NAME,
    is_supported_video_file,
    parse_movie_path,
    validate_clip_filename,
    validate_movie_filename,
    validate_time,
    validate_weekday,
)

logger = logging.getLogger(__name__)


def get_linux_time_status(now: datetime = None) -> Dict[str, Any]:
    """Return the daemon host's local time in a stable status shape."""
    if now:
        current_time = now if now.tzinfo else now.astimezone()
    else:
        current_time = datetime.now().astimezone()
    display_time = current_time.strftime('%Y-%m-%d %H:%M:%S %Z').strip()
    return {
        'iso': current_time.isoformat(timespec='seconds'),
        'epoch': int(current_time.timestamp()),
        'timezone': current_time.tzname() or '',
        'display': display_time,
    }


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
            display=self.config.get('display', ':0'),
            avcodec_hw=self.config.get('vlc_avcodec_hw', 'any'),
            video_output=self.config.get('vlc_video_output', 'xcb_x11'),
            avcodec_threads=self.config.get('vlc_avcodec_threads', 2),
            file_caching_ms=self.config.get('vlc_file_caching_ms', 1000),
            network_caching_ms=self.config.get('vlc_network_caching_ms', 1500),
            enable_frame_skip=bool(self.config.get('vlc_enable_frame_skip', True)),
            extra_vlc_args=self.config.get('vlc_extra_args', []),
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
            'aggressive_normalization': False,
            'database_path': '/var/lib/ktv/schedule.db',
            'log_path': '/var/log/ktv/daemon.log',
            'broadcast_start': '06:00',
            'broadcast_end': '22:00',
            'vlc_path': '/usr/bin/vlc',
            'display': ':0',
            'vlc_avcodec_hw': 'none',
            'vlc_video_output': 'xcb_x11',
            'vlc_avcodec_threads': 2,
            'vlc_file_caching_ms': 1000,
            'vlc_network_caching_ms': 1500,
            'vlc_enable_frame_skip': True,
            'vlc_extra_args': []
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
        
        # Playback transport commands
        self.api_server.register_handler('toggle_play_pause', self._handle_toggle_play_pause)
        self.api_server.register_handler('stop_playback', self._handle_stop_playback)
        self.api_server.register_handler('next_clip', self._handle_next_clip)
        self.api_server.register_handler('play_clip_file', self._handle_play_clip_file)
        self.api_server.register_handler('previous_clip', self._handle_previous_clip)
        self.api_server.register_handler('toggle_loop', self._handle_toggle_loop)
        self.api_server.register_handler('toggle_shuffle', self._handle_toggle_shuffle)
        self.api_server.register_handler('sync_playlists', self._handle_sync_playlists)
        
        # Status commands
        self.api_server.register_handler('get_status', self._handle_get_status)
        self.api_server.register_handler('ping', self._handle_ping)
        
        logger.info("API handlers registered")
    
    # API Handler Methods
    
    def _handle_add_schedule(self, params: Dict) -> Dict:
        """Handle add_schedule command"""
        weekday, hour, minute, filename = self._validate_schedule_params(params)
        target_path = self._build_schedule_target_path(
            weekday,
            hour,
            minute,
            filename
        )
        source_path = self._validate_schedule_source_path(params.get('filepath'))
        actual_path = source_path
        actual_filename = filename

        if source_path != target_path:
            move_result = self._safe_move(source_path, target_path)
            if not move_result['success']:
                raise RuntimeError(move_result['error'])
            actual_path = move_result['target_path']
            actual_filename = move_result['target_path'].name

        schedule_id = self.db.add_schedule(
            weekday=weekday,
            hour=hour,
            minute=minute,
            filepath=str(actual_path),
            filename=actual_filename,
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

        weekday, hour, minute, filename = self._validate_schedule_params(
            {
                'weekday': params.get('weekday'),
                'hour': params.get('hour'),
                'minute': params.get('minute'),
                'filename': schedule['filename'],
            }
        )
        source_path = Path(schedule['filepath'])
        target_path = self._build_schedule_target_path(
            weekday,
            hour,
            minute,
            filename
        )

        move_result = self._safe_move(source_path, target_path)
        if not move_result['success']:
            raise RuntimeError(move_result['error'])

        success = self.db.update_schedule(
            schedule_id=params['schedule_id'],
            weekday=weekday,
            hour=hour,
            minute=minute,
            filepath=str(move_result['target_path']),
            filename=move_result['target_path'].name
        )
        self._reload_runtime_state()
        return {'success': success, 'filepath': str(move_result['target_path'])}
    
    def _handle_sync_schedules(self, params: Dict) -> Dict:
        """Handle schedule/database synchronization."""
        result = self.sync_schedules()
        self._reload_runtime_state()
        return result

    def _handle_toggle_play_pause(self, params: Dict) -> Dict:
        """Handle play/pause toggle for clip playback."""
        playlist_manager = self._require_clip_transport()
        success = playlist_manager.toggle_play_pause()
        if not success:
            raise RuntimeError('Could not toggle clip playback')
        return self._transport_response()

    def _handle_stop_playback(self, params: Dict) -> Dict:
        """Handle stop for clip playback."""
        playlist_manager = self._require_clip_transport()
        success = playlist_manager.stop_playback()
        if not success:
            raise RuntimeError('Could not stop clip playback')
        return self._transport_response()

    def _handle_next_clip(self, params: Dict) -> Dict:
        """Handle skipping to the next clip."""
        playlist_manager = self._require_clip_transport()
        success = playlist_manager.play_next()
        if not success:
            raise RuntimeError('Could not start the next clip')
        return self._transport_response()

    def _handle_play_clip_file(self, params: Dict) -> Dict:
        """Handle immediate playback of a specific clip file."""
        playlist_manager = self._require_clip_transport()
        filename = params.get('filename')
        if not filename:
            raise ValueError('filename is required')
        filename = validate_clip_filename(filename)
        playlist_manager.reload_clips()
        success = playlist_manager.play_clip_file(filename)
        if not success:
            raise RuntimeError('Could not start the requested clip')
        return self._transport_response()

    def _handle_sync_playlists(self, params: Dict) -> Dict:
        """Handle clip list synchronization after GUI uploads or deletes files."""
        result = self.sync_playlists()
        self._reload_playlist_state()
        return result

    def _handle_previous_clip(self, params: Dict) -> Dict:
        """Handle going back to the previous clip."""
        playlist_manager = self._require_clip_transport()
        success = playlist_manager.play_previous()
        if not success:
            raise RuntimeError('Could not start the previous clip')
        return self._transport_response()

    def _handle_toggle_loop(self, params: Dict) -> Dict:
        """Handle loop mode toggle."""
        playlist_manager = self._require_playlist_manager()
        enabled = playlist_manager.toggle_loop()
        return {'loop_enabled': enabled, **self._transport_response()}

    def _handle_toggle_shuffle(self, params: Dict) -> Dict:
        """Handle shuffle mode toggle."""
        playlist_manager = self._require_playlist_manager()
        enabled = playlist_manager.toggle_shuffle()
        return {'shuffle_enabled': enabled, **self._transport_response()}
    
    def _handle_get_status(self, params: Dict) -> Dict:
        """Handle get_status command"""
        player_status = self.player.get_status()
        
        status = {
            'daemon_running': True,
            'player': player_status,
            'api_server_port': self.config['api_port'],
            'linux_time': get_linux_time_status(),
            'broadcast_hours': {
                'start': self.config['broadcast_start'],
                'end': self.config['broadcast_end']
            }
        }
        
        if self.time_controller:
            status['broadcasting_active'] = self.time_controller.is_broadcast_time()
        
        current_scheduled = self.scheduler.get_current_scheduled_playback() if self.scheduler else None
        playlist_snapshot = self.playlist_manager.get_status_snapshot() if self.playlist_manager else None

        if playlist_snapshot:
            status['playlist'] = {
                **playlist_snapshot,
                'transport_available': current_scheduled is None and playlist_snapshot['has_files'],
            }

        if current_scheduled:
            status['current_playback'] = {
                'source': 'movie',
                'filename': current_scheduled['filename'],
                'filepath': current_scheduled['filepath'],
            }
        elif playlist_snapshot and playlist_snapshot.get('current_filename'):
            status['current_playback'] = {
                'source': 'clip',
                'filename': playlist_snapshot['current_filename'],
                'filepath': playlist_snapshot['current_file'],
            }
        else:
            status['current_playback'] = {
                'source': None,
                'filename': None,
                'filepath': None,
            }

        next_clip_filename = None
        next_clip_file = None
        if playlist_snapshot and not playlist_snapshot['shuffle_enabled']:
            next_clip_filename = playlist_snapshot['next_filename']
            next_clip_file = playlist_snapshot['next_file']

        status['next_clip'] = {
            'filename': next_clip_filename,
            'filepath': next_clip_file,
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

        self.media_base_path = Path(self.config.get('media_base_path', os.path.expanduser('~/oktv')))
        self.clips_root = Path(self.config.get('clips_folder') or (self.media_base_path / 'clips'))
        self.config['media_base_path'] = str(self.media_base_path)
        self.config['clips_folder'] = str(self.clips_root)
        self.media_base_path.mkdir(parents=True, exist_ok=True)
        self.clips_root.mkdir(parents=True, exist_ok=True)
        
        # Register API handlers
        self._register_api_handlers()

        self.sync_schedules()
        # Start API server
        self.api_server.start()
        
        # Initialize playlist manager with clips folder
        self.playlist_manager = PlaylistManager(self.db, self.player, str(self.clips_root))
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
            self.playlist_manager.reload_clips()

    def _require_playlist_manager(self) -> PlaylistManager:
        """Ensure playlist manager is available."""
        if not self.playlist_manager:
            raise RuntimeError('Playlist manager is not available')
        return self.playlist_manager

    def _require_clip_transport(self) -> PlaylistManager:
        """Ensure clip transport controls may be used now."""
        if self.scheduler and self.scheduler.get_current_scheduled_playback():
            raise RuntimeError('Clip transport is unavailable while a scheduled movie is playing')
        return self._require_playlist_manager()

    def _transport_response(self) -> Dict:
        """Return the latest transport-related status."""
        status = self._handle_get_status({})
        return {
            'playlist': status.get('playlist', {}),
            'current_playback': status.get('current_playback', {}),
            'next_clip': status.get('next_clip', {}),
            'linux_time': status.get('linux_time'),
        }

    def _validate_schedule_params(self, params: Dict) -> tuple:
        """Validate weekly schedule parameters from an API request."""
        try:
            weekday = validate_weekday(self._coerce_int_param(params, 'weekday'))
            hour, minute = validate_time(
                self._coerce_int_param(params, 'hour'),
                self._coerce_int_param(params, 'minute')
            )
        except KeyError as exc:
            raise ValueError(f"{exc.args[0]} is required") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        filename = validate_movie_filename(params.get('filename'))
        return weekday, hour, minute, filename

    def _coerce_int_param(self, params: Dict, key: str) -> int:
        value = params[key]
        if isinstance(value, bool):
            raise ValueError(f"{key} must be an integer")
        return int(value)

    def _validate_schedule_source_path(self, filepath: str) -> Path:
        """Validate a source path accepted by schedule add/update handlers."""
        if not filepath:
            raise ValueError('filepath is required')
        raw_path = str(filepath)
        if "\x00" in raw_path:
            raise ValueError('filepath contains unsafe characters')
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            raise ValueError('filepath must be absolute')
        if '..' in source_path.parts:
            raise ValueError('filepath must not contain parent directory references')
        if not is_supported_video_file(source_path):
            raise ValueError('filepath must point to a supported video file')
        return source_path

    def _build_schedule_target_path(self, weekday: int, hour: int, minute: int,
                                    filename: str) -> Path:
        """Build the canonical target path for a weekly scheduled movie."""
        weekday = validate_weekday(weekday)
        hour, minute = validate_time(hour, minute)
        filename = validate_movie_filename(filename)
        return (
            self.media_base_path
            / WEEKLY_MOVIES_DIR_NAME
            / f"{weekday}"
            / f"{hour:02d}-{minute:02d}"
            / filename
        )

    def _build_conflict_path(self, target_path: Path) -> Path:
        """Build a conflict-safe target path."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        suffix = target_path.suffix
        stem = target_path.stem
        return target_path.with_name(f"{stem}_{timestamp}{suffix}")

    def _safe_move(self, source_path: Path, target_path: Path) -> Dict:
        """Safely move a file and avoid overwriting an existing target."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path == target_path:
            if not target_path.exists():
                return {'success': False, 'error': f'File not found: {target_path}'}
            return {'success': True, 'target_path': target_path}

        if source_path.exists():
            try:
                actual_target = target_path
                if actual_target.exists():
                    actual_target = self._build_conflict_path(actual_target)

                shutil.move(str(source_path), str(actual_target))
                logger.info("Moved media file: %s -> %s", source_path, actual_target)
                return {'success': True, 'target_path': actual_target}
            except Exception as exc:
                return {'success': False, 'error': f'Could not move file: {exc}'}

        if target_path.exists():
            return {'success': True, 'target_path': target_path}

        return {'success': False, 'error': f'File not found: {source_path}'}

    def _is_video_file(self, path: Path) -> bool:
        """Check whether a path is a supported media file."""
        return path.is_file() and is_supported_video_file(path)

    def _is_under_clips_root(self, path: Path) -> bool:
        """Check whether a path belongs to the clips subtree."""
        try:
            path.relative_to(self.clips_root)
            return True
        except ValueError:
            return False

    def _is_aggressive_normalization_enabled(self) -> bool:
        """Check whether sync is allowed to move operator files automatically."""
        return bool(self.config.get('aggressive_normalization', False))

    def _iter_movie_files(self) -> List[Path]:
        """Collect movie files from canonical `weekly/<weekday>/HH-MM/` directories."""
        movie_files: List[Path] = []
        weekly_root = self.media_base_path / WEEKLY_MOVIES_DIR_NAME
        if not weekly_root.exists():
            return movie_files

        for weekday_dir in sorted(weekly_root.iterdir(), key=lambda item: item.name):
            if not weekday_dir.is_dir():
                continue
            try:
                validate_weekday(int(weekday_dir.name))
            except ValueError:
                continue
            for slot_dir in sorted(weekday_dir.iterdir(), key=lambda item: item.name):
                if not slot_dir.is_dir() or '-' not in slot_dir.name:
                    continue
                hour_part, minute_part = slot_dir.name.split('-', 1)
                try:
                    validate_time(int(hour_part), int(minute_part))
                except ValueError:
                    continue
                for file_path in sorted(slot_dir.iterdir(), key=lambda item: item.name):
                    if self._is_video_file(file_path):
                        movie_files.append(file_path)
        movie_files.sort(key=lambda item: str(item))
        return movie_files

    def sync_schedules(self) -> Dict:
        """Synchronize schedule rows with canonical movie directories."""
        self.media_base_path.mkdir(parents=True, exist_ok=True)

        imported = 0
        moved = 0
        ensured_dirs = 0

        schedules = self.db.list_schedules(category='movies')
        known_paths = {}
        aggressive = self._is_aggressive_normalization_enabled()

        for schedule in schedules:
            expected_path = self._build_schedule_target_path(
                schedule['weekday'],
                schedule['hour'],
                schedule['minute'],
                schedule['filename']
            )
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            ensured_dirs += 1

            current_path = Path(schedule['filepath'])
            actual_path = current_path
            actual_filename = schedule['filename']

            if current_path == expected_path:
                known_paths[str(current_path)] = schedule['id']
                continue

            if current_path.exists():
                if aggressive:
                    move_result = self._safe_move(current_path, expected_path)
                    if move_result.get('success'):
                        actual_path = move_result['target_path']
                        actual_filename = move_result['target_path'].name
                        moved += 1
                        self.db.update_schedule(
                            schedule_id=schedule['id'],
                            weekday=schedule['weekday'],
                            hour=schedule['hour'],
                            minute=schedule['minute'],
                            filepath=str(actual_path),
                            filename=actual_filename
                        )
                    else:
                        logger.error("Fixed: could not align schedule file %s: %s", current_path, move_result['error'])
                else:
                    logger.warning(
                        "Fixed: leaving non-canonical schedule path unchanged (aggressive_normalization disabled): %s",
                        current_path
                    )
            elif expected_path.exists():
                actual_path = expected_path
                actual_filename = expected_path.name
                self.db.update_schedule(
                    schedule_id=schedule['id'],
                    weekday=schedule['weekday'],
                    hour=schedule['hour'],
                    minute=schedule['minute'],
                    filepath=str(actual_path),
                    filename=actual_filename
                )
            else:
                logger.error("Fixed: schedule file missing, keeping DB row unchanged: %s", current_path)

            known_paths[str(actual_path)] = schedule['id']

        for file_path in self._iter_movie_files():
            file_key = str(file_path)
            if file_key in known_paths:
                continue

            parsed = parse_movie_path(file_key)
            if not parsed:
                continue

            weekday, hour, minute, filename = parsed
            schedule_id = self.db.add_schedule(
                weekday=weekday,
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

    def sync_playlists(self) -> Dict:
        """Keep the default clips folder present without touching playlist rows."""
        self.clips_root.mkdir(parents=True, exist_ok=True)
        return {
            'success': True,
            'created': 0,
            'updated': 0,
            'imported': 0,
            'moved_root_files': 0,
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

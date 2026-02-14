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
from pathlib import Path
from typing import Dict, Any

from storage.database import Database
from api_server import APIServer
from player import Player
from scheduler import Scheduler
from playlist_manager import PlaylistManager
from time_controller import TimeController


class KTVDaemon:
    """Main daemon class"""
    
    def __init__(self, config_path: str = '/etc/ktv/config.json'):
        self.config = self._load_config(config_path)
        self.running = False
        
        # Initialize logging
        self._setup_logging()
        
        # Initialize components
        self.db = Database(self.config['database_path'])
        self.player = Player(self.config['mpv_path'])
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
            'api_port': 9999,
            'media_base_path': '/opt/ktv/media',
            'database_path': '/var/lib/ktv/schedule.db',
            'log_path': '/var/log/ktv/daemon.log',
            'broadcast_start': '06:00',
            'broadcast_end': '22:00',
            'mpv_path': '/usr/bin/mpv'
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
        """Setup logging configuration"""
        log_path = Path(self.config['log_path'])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler()
            ]
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
        
        # Playlist commands
        self.api_server.register_handler('create_playlist', self._handle_create_playlist)
        self.api_server.register_handler('delete_playlist', self._handle_delete_playlist)
        self.api_server.register_handler('set_active_playlist', self._handle_set_active_playlist)
        self.api_server.register_handler('list_playlists', self._handle_list_playlists)
        
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
    
    def _handle_create_playlist(self, params: Dict) -> Dict:
        """Handle create_playlist command"""
        playlist_id = self.db.create_playlist(
            name=params['name'],
            folder_path=params['folder_path']
        )
        return {'playlist_id': playlist_id}
    
    def _handle_delete_playlist(self, params: Dict) -> Dict:
        """Handle delete_playlist command"""
        success = self.db.delete_playlist(params['playlist_id'])
        return {'success': success}
    
    def _handle_set_active_playlist(self, params: Dict) -> Dict:
        """Handle set_active_playlist command"""
        success = self.db.set_active_playlist(params['playlist_id'])
        
        # Reload playlist manager if it exists
        if self.playlist_manager:
            self.playlist_manager.reload_active_playlist()
        
        return {'success': success}
    
    def _handle_list_playlists(self, params: Dict) -> Dict:
        """Handle list_playlists command"""
        playlists = self.db.list_playlists()
        return {'playlists': playlists}
    
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
        
        if self.playlist_manager:
            status['playlist'] = {
                'active': self.playlist_manager.get_active_playlist_name(),
                'playing': self.playlist_manager.is_playing()
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
        
        # Register API handlers
        self._register_api_handlers()
        
        # Start API server
        self.api_server.start()
        
        # Initialize playlist manager
        self.playlist_manager = PlaylistManager(self.db, self.player, self.config['media_base_path'])
        self.playlist_manager.start()
        
        # Initialize scheduler
        self.scheduler = Scheduler(self.db, self.player, self.playlist_manager)
        self.scheduler.start()
        
        # Initialize time controller
        self.time_controller = TimeController(
            self.scheduler, self.playlist_manager,
            self.config['broadcast_start'], self.config['broadcast_end']
        )
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

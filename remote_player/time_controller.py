"""
Time Controller for KTV daemon
Controls broadcast hours (6:00 - 22:00)
"""

import logging
from datetime import datetime, time as dt_time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class TimeController:
    """
    Controls when the system is broadcasting
    Starts at 6:00 AM and stops at 22:00 (10:00 PM)
    """
    
    def __init__(self, scheduler, playlist_manager, start_time: str = '06:00', end_time: str = '22:00'):
        """
        Initialize time controller
        
        Args:
            scheduler: Scheduler instance
            playlist_manager: PlaylistManager instance
            start_time: Broadcast start time (HH:MM format)
            end_time: Broadcast end time (HH:MM format)
        """
        self.scheduler = scheduler
        self.playlist_manager = playlist_manager
        
        # Parse times
        self.start_time = self._parse_time(start_time)
        self.end_time = self._parse_time(end_time)
        
        self.time_scheduler = BackgroundScheduler()
        self.running = False
        self.broadcasting = False
        
        logger.info(f"TimeController initialized: {start_time} - {end_time}")
    
    def _parse_time(self, time_str: str) -> dt_time:
        """Parse time string in HH:MM format"""
        hour, minute = map(int, time_str.split(':'))
        return dt_time(hour, minute)
    
    def start(self):
        """Start the time controller"""
        if self.running:
            logger.warning("TimeController already running")
            return
        
        # Schedule start broadcast job (daily at start_time)
        self.time_scheduler.add_job(
            func=self._start_broadcasting,
            trigger=CronTrigger(hour=self.start_time.hour, minute=self.start_time.minute),
            id='start_broadcast',
            name=f'Start broadcast at {self.start_time}',
            replace_existing=True
        )
        
        # Schedule stop broadcast job (daily at end_time)
        self.time_scheduler.add_job(
            func=self._stop_broadcasting,
            trigger=CronTrigger(hour=self.end_time.hour, minute=self.end_time.minute),
            id='stop_broadcast',
            name=f'Stop broadcast at {self.end_time}',
            replace_existing=True
        )
        
        self.time_scheduler.start()
        self.running = True
        
        # Check if we should be broadcasting now
        if self.is_broadcast_time():
            self._start_broadcasting()
        else:
            self._stop_broadcasting()
        
        logger.info("TimeController started")
    
    def stop(self):
        """Stop the time controller"""
        if not self.running:
            return
        
        self.time_scheduler.shutdown(wait=False)
        self.running = False
        
        logger.info("TimeController stopped")
    
    def is_broadcast_time(self) -> bool:
        """
        Check if current time is within broadcast hours
        
        Returns:
            True if currently in broadcast hours
        """
        now = datetime.now().time()
        
        if self.start_time < self.end_time:
            # Normal case: e.g., 6:00 - 22:00
            return self.start_time <= now < self.end_time
        else:
            # Overnight case: e.g., 22:00 - 6:00 (not typical for this app)
            return now >= self.start_time or now < self.end_time
    
    def _start_broadcasting(self):
        """Start broadcasting (called at start_time)"""
        if self.broadcasting:
            return
        
        logger.info("Starting broadcast")
        self.broadcasting = True
        
        # Resume playlist playback
        if self.playlist_manager:
            self.playlist_manager.resume()
        
        logger.info("Broadcast started")
    
    def _stop_broadcasting(self):
        """Stop broadcasting (called at end_time)"""
        if not self.broadcasting:
            return
        
        logger.info("Stopping broadcast")
        self.broadcasting = False
        
        # Pause playlist playback
        if self.playlist_manager:
            self.playlist_manager.pause()
        
        # Note: We don't stop scheduled playback - if there's a scheduled item
        # during off-hours, it will still play. This is by design.
        # If you want to prevent any playback during off-hours, uncomment:
        # if self.scheduler:
        #     self.scheduler.stop()
        
        logger.info("Broadcast stopped")
    
    def get_status(self) -> dict:
        """Get current status"""
        return {
            'broadcasting': self.broadcasting,
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M'),
            'is_broadcast_time': self.is_broadcast_time()
        }


# Test functionality
if __name__ == '__main__':
    import sys
    import time as time_module
    sys.path.insert(0, str(Path(__file__).parent))
    
    from pathlib import Path
    from storage.database import Database
    from player import Player
    from playlist_manager import PlaylistManager
    from scheduler import Scheduler
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create test instances
    db = Database(':memory:')
    player = Player()
    scheduler = Scheduler(db, player)
    pm = PlaylistManager(db, player)
    
    # Test with immediate start/stop (current time + 1 minute, + 2 minutes)
    now = datetime.now()
    start_minute = (now.minute + 1) % 60
    end_minute = (now.minute + 2) % 60
    
    start_time_str = f"{now.hour}:{start_minute:02d}"
    end_time_str = f"{now.hour}:{end_minute:02d}"
    
    print(f"Testing TimeController: {start_time_str} - {end_time_str}")
    
    # Create time controller
    tc = TimeController(scheduler, pm, start_time=start_time_str, end_time=end_time_str)
    
    print("Starting time controller...")
    tc.start()
    
    print("Time controller running. Will start at", start_time_str, "and stop at", end_time_str)
    print("Press Ctrl+C to stop...")
    
    try:
        while True:
            status = tc.get_status()
            print(f"Status: Broadcasting={status['broadcasting']}, InBroadcastTime={status['is_broadcast_time']}")
            time_module.sleep(10)
    except KeyboardInterrupt:
        print("\nStopping...")
        tc.stop()

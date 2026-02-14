"""
Scheduler for KTV daemon
Manages scheduled video playback using APScheduler
"""

import logging
from datetime import datetime
from typing import Optional, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pathlib import Path

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Manages scheduled video playback
    Handles priority over continuous playlist playback
    """
    
    def __init__(self, database, player, playlist_manager=None):
        """
        Initialize scheduler
        
        Args:
            database: Database instance
            player: Player instance
            playlist_manager: Optional PlaylistManager instance for coordination
        """
        self.db = database
        self.player = player
        self.playlist_manager = playlist_manager
        
        self.scheduler = BackgroundScheduler()
        self.job_ids = {}  # Map schedule_id to job_id
        self.running = False
        
        logger.info("Scheduler initialized")
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        self.scheduler.start()
        self.running = True
        
        # Load all schedules from database
        self.reload_schedules()
        
        logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        if not self.running:
            return
        
        self.scheduler.shutdown(wait=False)
        self.running = False
        self.job_ids.clear()
        
        logger.info("Scheduler stopped")
    
    def reload_schedules(self):
        """Reload all schedules from database"""
        logger.info("Reloading schedules...")
        
        # Remove all existing jobs
        self.scheduler.remove_all_jobs()
        self.job_ids.clear()
        
        # Load enabled schedules from database
        schedules = self.db.list_schedules(enabled_only=True)
        
        for schedule in schedules:
            self._add_schedule_job(schedule)
        
        logger.info(f"Loaded {len(schedules)} schedules")
    
    def _add_schedule_job(self, schedule: dict):
        """
        Add a scheduled job for a video
        
        Args:
            schedule: Schedule dictionary from database
        """
        schedule_id = schedule['id']
        month = schedule['month']
        day = schedule['day']
        hour = schedule['hour']
        minute = schedule['minute']
        filepath = schedule['filepath']
        filename = schedule['filename']
        
        # Create cron trigger for the specific time
        # This will trigger every year on the specified month/day/time
        trigger = CronTrigger(
            month=month,
            day=day,
            hour=hour,
            minute=minute
        )
        
        # Create job
        job = self.scheduler.add_job(
            func=self._execute_scheduled_playback,
            trigger=trigger,
            args=[schedule_id, filepath, filename],
            id=f'schedule_{schedule_id}',
            name=f'Play {filename} at {month}/{day} {hour}:{minute:02d}',
            replace_existing=True
        )
        
        self.job_ids[schedule_id] = job.id
        
        logger.debug(f"Added schedule job: {filename} at {month}/{day} {hour}:{minute:02d}")
    
    def _execute_scheduled_playback(self, schedule_id: int, filepath: str, filename: str):
        """
        Execute scheduled playback
        This is called by APScheduler at the scheduled time
        
        Args:
            schedule_id: Schedule ID
            filepath: Path to video file
            filename: Filename for logging
        """
        logger.info(f"Executing scheduled playback: {filename}")
        
        # Check if file exists
        if not Path(filepath).exists():
            logger.error(f"Scheduled file not found: {filepath}")
            return
        
        # Stop playlist if it's playing
        if self.playlist_manager and self.playlist_manager.is_playing():
            logger.info("Pausing playlist for scheduled playback")
            self.playlist_manager.pause()
        
        # Play the scheduled video
        success = self.player.play(filepath, fullscreen=True)
        
        if success:
            logger.info(f"Started scheduled playback: {filename}")
            
            # Set callback to resume playlist when playback ends
            def on_playback_ended(completed_file):
                logger.info(f"Scheduled playback ended: {filename}")
                
                # Resume playlist if available
                if self.playlist_manager:
                    logger.info("Resuming playlist after scheduled playback")
                    self.playlist_manager.resume()
            
            self.player.set_playback_ended_callback(on_playback_ended)
        else:
            logger.error(f"Failed to start scheduled playback: {filename}")
            
            # Resume playlist immediately if playback failed
            if self.playlist_manager:
                self.playlist_manager.resume()
    
    def get_next_scheduled_playback(self) -> Optional[dict]:
        """
        Get information about the next scheduled playback
        
        Returns:
            Dictionary with next schedule info or None
        """
        jobs = self.scheduler.get_jobs()
        
        if not jobs:
            return None
        
        # Find job with nearest next run time
        next_job = min(jobs, key=lambda j: j.next_run_time)
        
        if next_job:
            return {
                'job_id': next_job.id,
                'name': next_job.name,
                'next_run_time': next_job.next_run_time.isoformat() if next_job.next_run_time else None
            }
        
        return None
    
    def get_scheduled_count(self) -> int:
        """Get number of active scheduled jobs"""
        return len(self.scheduler.get_jobs())


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
    
    # Create player
    player = Player()
    
    # Create scheduler
    scheduler = Scheduler(db, player)
    
    # Add a test schedule (today, in 1 minute)
    now = datetime.now()
    next_minute = (now.minute + 1) % 60
    
    schedule_id = db.add_schedule(
        month=now.month,
        day=now.day,
        hour=now.hour,
        minute=next_minute,
        filepath='/opt/ktv/media/test.mp4',
        filename='test.mp4',
        category='movies'
    )
    
    print(f"Added test schedule: ID={schedule_id}, will trigger at {now.hour}:{next_minute:02d}")
    
    # Start scheduler
    scheduler.start()
    
    print("Scheduler running. Press Ctrl+C to stop...")
    print(f"Next scheduled playback: {scheduler.get_next_scheduled_playback()}")
    
    try:
        import time
        while True:
            time.sleep(10)
            info = scheduler.get_next_scheduled_playback()
            if info:
                print(f"Next: {info['name']} at {info['next_run_time']}")
    except KeyboardInterrupt:
        print("\nStopping...")
        scheduler.stop()

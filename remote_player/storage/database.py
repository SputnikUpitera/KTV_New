"""
Database module for KTV daemon
Handles schedule and playlist storage using SQLite
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from ktv_paths import validate_movie_filename, validate_time, validate_weekday

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for KTV daemon"""
    
    def __init__(self, db_path: str = "/var/lib/ktv/schedule.db"):
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_database()
    
    def _ensure_db_directory(self):
        """Create database directory if it doesn't exist"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            self._ensure_schedule_schema(cursor)
            
            # Playlists table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    folder_path TEXT NOT NULL,
                    active INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Create indexes
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_schedule_time
                ON schedule(weekday, hour, minute)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_schedule_enabled 
                ON schedule(enabled)
            ''')
            
            conn.commit()
            logger.info("Database initialized")

    def _ensure_schedule_schema(self, cursor):
        """Create weekly schedule schema, dropping old annual rows if needed."""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schedule'"
        )
        table_exists = cursor.fetchone() is not None
        if table_exists:
            columns = {
                row["name"]
                for row in cursor.execute("PRAGMA table_info(schedule)").fetchall()
            }
            if "weekday" not in columns or {"month", "day"} & columns:
                cursor.execute("DROP TABLE schedule")
                table_exists = False

        if not table_exists:
            # Weekday convention is 0=Monday through 6=Sunday.
            cursor.execute('''
                CREATE TABLE schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    weekday INTEGER NOT NULL CHECK(weekday >= 0 AND weekday <= 6),
                    hour INTEGER NOT NULL CHECK(hour >= 0 AND hour <= 23),
                    minute INTEGER NOT NULL CHECK(minute >= 0 AND minute <= 59),
                    filepath TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    category TEXT DEFAULT 'movies',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # Schedule operations
    
    def add_schedule(self, weekday: int, hour: int, minute: int,
                    filepath: str, filename: str, category: str = 'movies') -> int:
        """Add a new weekly schedule entry."""
        weekday = validate_weekday(weekday)
        hour, minute = validate_time(hour, minute)
        filename = validate_movie_filename(filename)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO schedule (weekday, hour, minute, filepath, filename, category)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (weekday, hour, minute, filepath, filename, category))
            conn.commit()
            schedule_id = cursor.lastrowid
            logger.info(f"Added schedule: {filename} at weekday {weekday} {hour}:{minute}")
            return schedule_id
    
    def remove_schedule(self, schedule_id: int) -> bool:
        """Remove a schedule entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM schedule WHERE id = ?', (schedule_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Removed schedule ID: {schedule_id}")
            return deleted
    
    def toggle_schedule(self, schedule_id: int, enabled: bool) -> bool:
        """Enable or disable a schedule entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE schedule SET enabled = ? WHERE id = ?
            ''', (1 if enabled else 0, schedule_id))
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Toggled schedule ID {schedule_id}: enabled={enabled}")
            return updated
    
    def get_schedule(self, schedule_id: int) -> Optional[Dict]:
        """Get a specific schedule entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM schedule WHERE id = ?', (schedule_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_schedule(self, schedule_id: int, weekday: int, hour: int, minute: int,
                        filepath: str, filename: str) -> bool:
        """Update a weekly schedule entry and its file location."""
        weekday = validate_weekday(weekday)
        hour, minute = validate_time(hour, minute)
        filename = validate_movie_filename(filename)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE schedule
                SET weekday = ?, hour = ?, minute = ?, filepath = ?, filename = ?
                WHERE id = ?
            ''', (weekday, hour, minute, filepath, filename, schedule_id))
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(
                    "Updated schedule ID %s to weekday %d %02d:%02d",
                    schedule_id,
                    weekday,
                    hour,
                    minute
                )
            return updated
    
    def list_schedules(self, enabled_only: bool = False, category: Optional[str] = None) -> List[Dict]:
        """List all schedule entries"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM schedule WHERE 1=1'
            params = []
            
            if enabled_only:
                query += ' AND enabled = 1'
            
            if category:
                query += ' AND category = ?'
                params.append(category)
            
            query += ' ORDER BY weekday, hour, minute'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_schedules_for_time(self, weekday: int, hour: int, minute: int) -> List[Dict]:
        """Get enabled schedules for a weekly weekday/time slot."""
        weekday = validate_weekday(weekday)
        hour, minute = validate_time(hour, minute)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM schedule
                WHERE weekday = ? AND hour = ? AND minute = ? AND enabled = 1
            ''', (weekday, hour, minute))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # Playlist operations
    
    def create_playlist(self, name: str, folder_path: str) -> int:
        """Create a new playlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO playlists (name, folder_path)
                VALUES (?, ?)
            ''', (name, folder_path))
            conn.commit()
            playlist_id = cursor.lastrowid
            logger.info(f"Created playlist: {name} at {folder_path}")
            return playlist_id

    def get_playlist(self, playlist_id: int) -> Optional[Dict]:
        """Get a playlist by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM playlists WHERE id = ?', (playlist_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_playlist_by_name(self, name: str) -> Optional[Dict]:
        """Get a playlist by its unique name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM playlists WHERE name = ?', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_playlist_folder(self, playlist_id: int, folder_path: str) -> bool:
        """Update the storage folder for an existing playlist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE playlists
                SET folder_path = ?
                WHERE id = ?
            ''', (folder_path, playlist_id))
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info("Updated playlist ID %s folder to %s", playlist_id, folder_path)
            return updated

    def ensure_playlist(self, name: str, folder_path: str, folder_aligned: bool = False) -> Tuple[int, bool]:
        """Create a playlist or update its path only after a confirmed filesystem move."""
        existing = self.get_playlist_by_name(name)
        if existing:
            if existing['folder_path'] != folder_path:
                if not folder_aligned:
                    raise ValueError(
                        f"Playlist folder mismatch for '{name}': "
                        f"{existing['folder_path']} -> {folder_path}"
                    )
                self.update_playlist_folder(existing['id'], folder_path)
            return existing['id'], False

        playlist_id = self.create_playlist(name, folder_path)
        return playlist_id, True
    
    def delete_playlist(self, playlist_id: int) -> bool:
        """Delete a playlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM playlists WHERE id = ?', (playlist_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted playlist ID: {playlist_id}")
            return deleted
    
    def set_active_playlist(self, playlist_id: int) -> bool:
        """Set a playlist as active (deactivates others)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Deactivate all
            cursor.execute('UPDATE playlists SET active = 0')
            # Activate the selected one
            cursor.execute('UPDATE playlists SET active = 1 WHERE id = ?', (playlist_id,))
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Set active playlist ID: {playlist_id}")
            return updated
    
    def get_active_playlist(self) -> Optional[Dict]:
        """Get the currently active playlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM playlists WHERE active = 1 LIMIT 1')
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def list_playlists(self) -> List[Dict]:
        """List all playlists"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM playlists ORDER BY name')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # Settings operations
    
    def set_setting(self, key: str, value: str) -> None:
        """Set a configuration setting"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?)
            ''', (key, value))
            conn.commit()
    
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a configuration setting"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
    
    def get_all_settings(self) -> Dict[str, str]:
        """Get all settings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value FROM settings')
            rows = cursor.fetchall()
            return {row['key']: row['value'] for row in rows}

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
            
            # Schedule table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month INTEGER NOT NULL CHECK(month >= 1 AND month <= 12),
                    day INTEGER NOT NULL CHECK(day >= 1 AND day <= 31),
                    hour INTEGER NOT NULL CHECK(hour >= 0 AND hour <= 23),
                    minute INTEGER NOT NULL CHECK(minute >= 0 AND minute <= 59),
                    filepath TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    category TEXT DEFAULT 'movies',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
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
                ON schedule(month, day, hour, minute)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_schedule_enabled 
                ON schedule(enabled)
            ''')
            
            conn.commit()
            logger.info("Database initialized")
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # Schedule operations
    
    def add_schedule(self, month: int, day: int, hour: int, minute: int,
                    filepath: str, filename: str, category: str = 'movies') -> int:
        """Add a new schedule entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO schedule (month, day, hour, minute, filepath, filename, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (month, day, hour, minute, filepath, filename, category))
            conn.commit()
            schedule_id = cursor.lastrowid
            logger.info(f"Added schedule: {filename} at {month}/{day} {hour}:{minute}")
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

    def update_schedule(self, schedule_id: int, month: int, day: int, hour: int, minute: int,
                        filepath: str, filename: str) -> bool:
        """Update a schedule entry and its file location."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE schedule
                SET month = ?, day = ?, hour = ?, minute = ?, filepath = ?, filename = ?
                WHERE id = ?
            ''', (month, day, hour, minute, filepath, filename, schedule_id))
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(
                    "Updated schedule ID %s to %02d/%02d %02d:%02d",
                    schedule_id,
                    month,
                    day,
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
            
            query += ' ORDER BY month, day, hour, minute'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_schedules_for_time(self, month: int, day: int, hour: int, minute: int) -> List[Dict]:
        """Get schedules for specific time"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM schedule 
                WHERE month = ? AND day = ? AND hour = ? AND minute = ? AND enabled = 1
            ''', (month, day, hour, minute))
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

    def ensure_playlist(self, name: str, folder_path: str) -> Tuple[int, bool]:
        """Create a playlist if it does not exist, otherwise keep its folder path aligned."""
        existing = self.get_playlist_by_name(name)
        if existing:
            if existing['folder_path'] != folder_path:
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

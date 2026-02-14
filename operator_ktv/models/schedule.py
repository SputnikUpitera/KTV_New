"""
Schedule data models
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ScheduleItem:
    """Represents a scheduled video playback"""
    id: int
    month: int
    day: int
    hour: int
    minute: int
    filepath: str
    filename: str
    enabled: bool
    category: str
    created_at: Optional[str] = None
    
    def get_time_string(self) -> str:
        """Get formatted time string"""
        return f"{self.hour:02d}:{self.minute:02d}"
    
    def get_date_string(self) -> str:
        """Get formatted date string"""
        months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
        month_name = months[self.month - 1] if 1 <= self.month <= 12 else f"Month {self.month}"
        return f"{self.day} {month_name}"
    
    def __str__(self) -> str:
        status = "✓" if self.enabled else "✗"
        return f"{status} {self.get_time_string()} - {self.filename}"

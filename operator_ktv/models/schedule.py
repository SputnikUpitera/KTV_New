"""
Schedule data models.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ScheduleItem:
    """Represents a weekly scheduled video playback."""

    id: int
    weekday: int
    hour: int
    minute: int
    filepath: str
    filename: str
    enabled: bool
    category: str
    created_at: Optional[str] = None

    def get_time_string(self) -> str:
        """Get formatted time string."""
        return f"{self.hour:02d}:{self.minute:02d}"

    def get_weekday_string(self) -> str:
        """Get formatted weekday string. Weekday is 0=Monday through 6=Sunday."""
        weekdays = [
            "Понедельник",
            "Вторник",
            "Среда",
            "Четверг",
            "Пятница",
            "Суббота",
            "Воскресенье",
        ]
        if 0 <= self.weekday <= 6:
            return weekdays[self.weekday]
        return f"День {self.weekday}"

    def get_date_string(self) -> str:
        """Backward-compatible display helper for schedule grouping."""
        return self.get_weekday_string()

    def __str__(self) -> str:
        status = "вкл" if self.enabled else "выкл"
        return f"{status} {self.get_weekday_string()} {self.get_time_string()} - {self.filename}"

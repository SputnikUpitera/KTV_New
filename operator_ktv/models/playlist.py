"""
Playlist data models
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Playlist:
    """Represents a media playlist"""
    id: int
    name: str
    folder_path: str
    active: bool
    created_at: Optional[str] = None
    
    def __str__(self) -> str:
        status = "●" if self.active else "○"
        return f"{status} {self.name}"

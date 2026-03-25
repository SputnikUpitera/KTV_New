"""
Schedule dialog for selecting playback time
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QTimeEdit, QPushButton, QWidget)
from PyQt6.QtCore import QTime, Qt
from pathlib import Path


class ScheduleDialog(QDialog):
    """Dialog for scheduling video playback time"""
    
    def __init__(self, filename: str, month: int, day: int, parent=None,
                 initial_hour: int = 12, initial_minute: int = 0,
                 dialog_title: str = "Выбор времени воспроизведения",
                 action_text: str = "Подтвердить"):
        super().__init__(parent)
        
        self.filename = filename
        self.month = month
        self.day = day
        self.selected_time = None
        self.initial_hour = initial_hour
        self.initial_minute = initial_minute
        self.dialog_title = dialog_title
        self.action_text = action_text
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle(self.dialog_title)
        self.setModal(True)
        self.setFixedSize(400, 200)
        
        layout = QVBoxLayout()
        
        # File info
        file_label = QLabel(f"Файл: {Path(self.filename).name}")
        file_label.setWordWrap(True)
        layout.addWidget(file_label)
        
        # Date info
        months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
        month_name = months[self.month - 1] if 1 <= self.month <= 12 else f"Month {self.month}"
        date_label = QLabel(f"Дата: {self.day} {month_name}")
        layout.addWidget(date_label)
        
        layout.addSpacing(20)
        
        # Time selection
        time_layout = QHBoxLayout()
        time_label = QLabel("Время воспроизведения:")
        time_layout.addWidget(time_label)
        
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(self.initial_hour, self.initial_minute))
        time_layout.addWidget(self.time_edit)
        
        layout.addLayout(time_layout)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton(self.action_text)
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def get_time(self) -> tuple:
        """
        Get selected time
        
        Returns:
            Tuple of (hour, minute)
        """
        time = self.time_edit.time()
        return time.hour(), time.minute()

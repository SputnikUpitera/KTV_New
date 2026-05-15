"""
Schedule dialog for selecting weekly playback time.
"""

from pathlib import Path

from PyQt6.QtCore import QEvent, QTime, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
)

from .time_input_logic import (
    HOUR_FIELD,
    MINUTE_FIELD,
    TimeField,
    adjust_time_parts,
    apply_numeric_time_input,
    next_time_field,
    normalize_time_parts,
)


class ScheduleTimeEdit(QTimeEdit):
    """Time editor that replaces the selected HH:mm field directly."""

    _SECTION_BY_FIELD = {
        HOUR_FIELD: QDateTimeEdit.Section.HourSection,
        MINUTE_FIELD: QDateTimeEdit.Section.MinuteSection,
    }
    _FIELD_BY_SECTION = {
        QDateTimeEdit.Section.HourSection: HOUR_FIELD,
        QDateTimeEdit.Section.MinuteSection: MINUTE_FIELD,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_field: TimeField = HOUR_FIELD
        self._pending_digits = ""

    def setTime(self, time: QTime):
        """Set the time and keep the visible field selection stable."""
        super().setTime(time)
        selected_field = getattr(self, "_selected_field", HOUR_FIELD)
        if hasattr(self, "_pending_digits"):
            self._select_field(selected_field, reset_digits=False)

    def event(self, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        ):
            reverse = event.key() == Qt.Key.Key_Backtab or bool(
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            )
            self._select_field(next_time_field(self._selected_field, reverse=reverse))
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._select_field(
                next_time_field(
                    self._selected_field,
                    reverse=key == Qt.Key.Key_Left,
                )
            )
            return

        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._adjust_selected_field(1 if key == Qt.Key.Key_Up else -1)
            return

        text = event.text()
        if len(text) == 1 and text.isdigit():
            self._replace_selected_field(text)
            return

        self._pending_digits = ""
        super().keyPressEvent(event)
        self._sync_field_from_section()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._sync_field_from_section()
        self._select_field(self._selected_field)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._sync_field_from_section()
        self._select_field(self._selected_field)

    def _select_field(self, field: TimeField, reset_digits: bool = True):
        self._selected_field = field
        if reset_digits:
            self._pending_digits = ""
        section = self._SECTION_BY_FIELD[field]
        self.setCurrentSection(section)
        self.setSelectedSection(section)

    def _sync_field_from_section(self):
        self._selected_field = self._FIELD_BY_SECTION.get(
            self.currentSection(),
            self._selected_field,
        )
        self._pending_digits = ""

    def _adjust_selected_field(self, delta: int):
        time = self.time()
        hour, minute = adjust_time_parts(
            time.hour(),
            time.minute(),
            self._selected_field,
            delta,
        )
        self._pending_digits = ""
        self.setTime(QTime(hour, minute))

    def _replace_selected_field(self, digit: str):
        time = self.time()
        hour, minute, self._pending_digits = apply_numeric_time_input(
            time.hour(),
            time.minute(),
            self._selected_field,
            self._pending_digits,
            digit,
        )
        self.setTime(QTime(hour, minute))


class ScheduleDialog(QDialog):
    """Dialog for weekly video playback scheduling."""

    WEEKDAY_NAMES = [
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    ]

    def __init__(self, filename: str, weekday: int, parent=None,
                 initial_hour: int = 12, initial_minute: int = 0,
                 dialog_title: str = "Выбор времени воспроизведения",
                 action_text: str = "Подтвердить",
                 allow_weekday_selection: bool = False):
        super().__init__(parent)

        self.filename = filename
        self.weekday = weekday
        self.initial_hour = initial_hour
        self.initial_minute = initial_minute
        self.dialog_title = dialog_title
        self.action_text = action_text
        self.allow_weekday_selection = allow_weekday_selection

        self.setup_ui()

    def setup_ui(self):
        """Setup the user interface."""
        self.setWindowTitle(self.dialog_title)
        self.setModal(True)
        self.setFixedSize(420, 220)

        layout = QVBoxLayout()

        file_label = QLabel(f"Файл: {Path(self.filename).name}")
        file_label.setWordWrap(True)
        layout.addWidget(file_label)

        if self.allow_weekday_selection:
            weekday_layout = QHBoxLayout()
            weekday_layout.addWidget(QLabel("День недели:"))

            self.weekday_combo = QComboBox()
            self.weekday_combo.addItems(self.WEEKDAY_NAMES)
            if 0 <= self.weekday <= 6:
                self.weekday_combo.setCurrentIndex(self.weekday)
            weekday_layout.addWidget(self.weekday_combo)
            weekday_layout.addStretch()
            layout.addLayout(weekday_layout)
        else:
            weekday_name = self.WEEKDAY_NAMES[self.weekday] if 0 <= self.weekday <= 6 else f"День {self.weekday}"
            layout.addWidget(QLabel(f"День недели: {weekday_name}"))

        layout.addSpacing(20)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Время воспроизведения:"))

        self.time_edit = ScheduleTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        hour, minute = normalize_time_parts(self.initial_hour, self.initial_minute)
        self.time_edit.setTime(QTime(hour, minute))
        time_layout.addWidget(self.time_edit)

        layout.addLayout(time_layout)
        layout.addStretch()

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
        """Get selected time as (hour, minute)."""
        time = self.time_edit.time()
        return time.hour(), time.minute()

    def get_schedule_slot(self) -> tuple:
        """Get selected weekly slot as (weekday, hour, minute)."""
        hour, minute = self.get_time()
        weekday = self.weekday_combo.currentIndex() if self.allow_weekday_selection else self.weekday
        return weekday, hour, minute

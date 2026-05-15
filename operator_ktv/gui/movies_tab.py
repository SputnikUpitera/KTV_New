"""
Movies tab for weekly schedule management.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ktv_paths import VIDEO_FILE_DIALOG_FILTER, build_movie_file_path, is_supported_video_file
from .movie_schedule_logic import format_schedule_item_label, group_schedules_by_weekday
from .schedule_dialog import ScheduleDialog
from .upload_helpers import upload_file_with_progress
from ..models.schedule import ScheduleItem

logger = logging.getLogger(__name__)


def schedule_item_from_payload(payload):
    """Build a weekly ScheduleItem from daemon data, ignoring legacy annual rows."""
    if not isinstance(payload, dict):
        logger.warning("Skipping invalid schedule payload: %r", payload)
        return None

    if 'weekday' not in payload:
        logger.warning(
            "Skipping legacy annual schedule row without weekday: id=%s filename=%s",
            payload.get('id'),
            payload.get('filename'),
        )
        return None

    allowed_keys = {
        'id',
        'weekday',
        'hour',
        'minute',
        'filepath',
        'filename',
        'enabled',
        'category',
        'created_at',
    }
    return ScheduleItem(**{key: value for key, value in payload.items() if key in allowed_keys})


class MoviesTab(QWidget):
    """Widget for managing weekly movie schedules."""

    schedule_changed = pyqtSignal()
    refresh_requested = pyqtSignal()

    # Weekday convention is 0=Monday through 6=Sunday.
    WEEKDAY_NAMES = [
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    ]

    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.schedules = []
        self.weekday_columns = {}
        self.weekday_lists = {}

        self.setup_ui()
        self.create_weekday_columns()
        self.set_cmd_client(cmd_client)

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(6)

        self.section_label = QLabel("Фильмы:")
        self.section_label.setObjectName("playlistSectionLabel")
        self.section_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.section_label)

        self.week_grid = QWidget()
        self.week_grid_layout = QHBoxLayout(self.week_grid)
        self.week_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.week_grid_layout.setSpacing(6)
        layout.addWidget(self.week_grid, 1)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.setProperty("compact", True)
        self.refresh_btn.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        button_layout.addWidget(self.refresh_btn)

        self.edit_btn = QPushButton("Изменить время")
        self.edit_btn.setProperty("compact", True)
        self.edit_btn.clicked.connect(self.edit_selected_schedule)
        button_layout.addWidget(self.edit_btn)

        self.toggle_btn = QPushButton("Вкл/выкл")
        self.toggle_btn.setProperty("compact", True)
        self.toggle_btn.clicked.connect(self.toggle_selected_schedule)
        button_layout.addWidget(self.toggle_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.setProperty("compact", True)
        self.delete_btn.clicked.connect(self.delete_selected)
        button_layout.addWidget(self.delete_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def create_weekday_columns(self):
        """Create one schedule list column per weekday."""
        self.weekday_columns.clear()
        self.weekday_lists.clear()

        for weekday, weekday_name in enumerate(self.WEEKDAY_NAMES):
            column = QFrame(self.week_grid)
            column.setObjectName("scheduleDayColumn")
            column.setFrameShape(QFrame.Shape.StyledPanel)
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(6, 6, 6, 6)
            column_layout.setSpacing(5)

            row_widget = QWidget(column)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)

            title_label = QLabel(weekday_name)
            title_label.setObjectName("weekdayHeaderLabel")
            row_layout.addWidget(title_label)

            add_btn = QToolButton(row_widget)
            add_btn.setText("+")
            add_btn.setObjectName("weekdayAddButton")
            add_btn.setToolTip(f"Добавить фильм на {weekday_name.lower()}")
            add_btn.setAccessibleName(f"Добавить фильм на {weekday_name.lower()}")
            add_btn.clicked.connect(lambda _, selected_weekday=weekday: self.add_movie_for_weekday(selected_weekday))
            row_layout.addWidget(add_btn)
            row_layout.addStretch()

            schedule_list = QListWidget(column)
            schedule_list.setObjectName("scheduleDayList")
            schedule_list.setAcceptDrops(True)
            schedule_list.setDragEnabled(False)
            schedule_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
            schedule_list.itemDoubleClicked.connect(self.on_item_double_clicked)
            schedule_list.itemSelectionChanged.connect(
                lambda selected_list=schedule_list: self._clear_other_day_selections(selected_list)
            )
            schedule_list.dragEnterEvent = self.drag_enter_event
            schedule_list.dragMoveEvent = self.drag_move_event
            schedule_list.dropEvent = lambda event, selected_weekday=weekday: self.drop_event(
                event,
                selected_weekday,
            )

            column_layout.addWidget(row_widget)
            column_layout.addWidget(schedule_list, 1)
            self.week_grid_layout.addWidget(column, 1)

            self.weekday_columns[weekday] = {
                'label': title_label,
                'button': add_btn,
                'column': column,
            }
            self.weekday_lists[weekday] = schedule_list

    def _clear_other_day_selections(self, selected_list):
        """Keep schedule selection single across all weekday columns."""
        if selected_list.currentItem() is None:
            return
        for schedule_list in self.weekday_lists.values():
            if schedule_list is not selected_list:
                schedule_list.clearSelection()
                schedule_list.setCurrentRow(-1)

    def _selected_schedule(self):
        for schedule_list in self.weekday_lists.values():
            item = schedule_list.currentItem()
            if not item or not item.isSelected():
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and data.get('type') == 'schedule':
                return data['schedule']
        return None

    def refresh_schedules(self, do_sync: bool = False):
        """Reload schedules from the remote system and sync only when requested."""
        if not self.cmd_client:
            QMessageBox.information(self, "Информация", "Нет подключения к daemon")
            return

        try:
            if do_sync:
                sync_success, _, sync_error = self.cmd_client.sync_schedules()
                if not sync_success:
                    if "Unknown command: sync_schedules" in sync_error:
                        logger.warning("Daemon does not support sync_schedules, loading schedules without sync")
                    else:
                        QMessageBox.warning(self, "Ошибка", f"Не удалось синхронизировать расписание:\n{sync_error}")
                        return

            success, schedules_data, error = self.cmd_client.list_schedules(category='movies')
            if not success:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить расписание:\n{error}")
                return

            self.schedules = [
                schedule
                for schedule in (schedule_item_from_payload(item) for item in schedules_data)
                if schedule is not None
            ]
            self.update_tree_with_schedules()
            logger.info("Loaded %s movie schedules", len(self.schedules))
        except Exception as exc:
            logger.error("Error refreshing schedules: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления:\n{exc}")

    def update_tree_with_schedules(self):
        """Render schedules and counters into the weekday columns."""
        schedules_by_weekday = group_schedules_by_weekday(self.schedules)

        for weekday, weekday_name in enumerate(self.WEEKDAY_NAMES):
            schedule_list = self.weekday_lists[weekday]
            schedule_list.clear()
            weekday_schedules = schedules_by_weekday.get(weekday, [])
            self._set_weekday_label(weekday, f"{weekday_name} ({len(weekday_schedules)})")

            for schedule in weekday_schedules:
                schedule_item = QListWidgetItem(
                    format_schedule_item_label(
                        schedule,
                        enabled_text="[вкл]",
                        disabled_text="[выкл]",
                    )
                )
                schedule_item.setData(Qt.ItemDataRole.UserRole, {
                    'type': 'schedule',
                    'schedule': schedule,
                })
                schedule_item.setToolTip(schedule.filepath)

                if schedule.enabled:
                    schedule_item.setForeground(QBrush(QColor(120, 220, 150)))
                else:
                    schedule_item.setForeground(QBrush(QColor(140, 140, 140)))
                schedule_list.addItem(schedule_item)

    def _set_weekday_label(self, weekday: int, text: str):
        """Update the visible label for a weekday column."""
        widgets = self.weekday_columns.get(weekday)
        if widgets:
            widgets['label'].setText(text)

    def drag_enter_event(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def drag_move_event(self, event):
        """Handle drag move event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def drop_event(self, event, weekday: int):
        """Handle drop event for file drops."""
        if not event.mimeData().hasUrls():
            return
        if not 0 <= weekday <= 6:
            return

        files = [url.toLocalFile() for url in event.mimeData().urls()]
        video_files = [path for path in files if is_supported_video_file(path)]
        if not video_files:
            QMessageBox.warning(self, "Ошибка", "Не найдено видеофайлов")
            return

        for file_path in video_files:
            self.add_file_to_schedule(file_path, weekday)

        event.acceptProposedAction()

    def add_movie_for_weekday(self, weekday: int):
        """Pick local movie files and add them to a selected weekday."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите фильмы",
            "",
            VIDEO_FILE_DIALOG_FILTER,
        )
        for file_path in files:
            self.add_file_to_schedule(file_path, weekday)

    def add_file_to_schedule(self, file_path: str, weekday: int):
        """Prompt for schedule slot and then upload a movie into the schedule."""
        dialog = ScheduleDialog(
            Path(file_path).name,
            weekday,
            self,
            allow_weekday_selection=False,
        )
        if dialog.exec():
            chosen_weekday, hour, minute = dialog.get_schedule_slot()
            self.upload_and_schedule(file_path, chosen_weekday, hour, minute)

    def upload_and_schedule(self, local_path: str, weekday: int, hour: int, minute: int):
        """Upload file and add it to the remote schedule."""
        if not self.ssh_client or not self.cmd_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удаленной системе")
            return

        filename = Path(local_path).name
        remote_path = build_movie_file_path(self.ssh_client.get_remote_home(), weekday, hour, minute, filename)

        try:
            success, error = upload_file_with_progress(self, self.ssh_client, local_path, remote_path)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{error}")
                return

            success, schedule_id, error = self.cmd_client.add_schedule(
                weekday=weekday,
                hour=hour,
                minute=minute,
                filepath=remote_path,
                filename=filename,
                category='movies',
            )

            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось добавить в расписание:\n{error}")
                return

            QMessageBox.information(self, "Успех", f"Фильм добавлен в расписание (ID: {schedule_id})")
            self.refresh_schedules()
            self.schedule_changed.emit()
        except Exception as exc:
            logger.error("Error uploading/scheduling file: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def edit_selected_schedule(self):
        """Change the weekly playback time of the selected movie."""
        schedule = self._selected_schedule()
        if not schedule:
            QMessageBox.information(self, "Информация", "Выберите фильм для изменения")
            return

        dialog = ScheduleDialog(
            schedule.filename,
            schedule.weekday,
            self,
            initial_hour=schedule.hour,
            initial_minute=schedule.minute,
            dialog_title="Изменение времени фильма",
            action_text="Сохранить",
            allow_weekday_selection=True,
        )
        if not dialog.exec():
            return

        weekday, hour, minute = dialog.get_schedule_slot()
        try:
            success, _, error = self.cmd_client.update_schedule(
                schedule.id,
                weekday,
                hour,
                minute,
            )
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось изменить время:\n{error}")
                return

            self.refresh_schedules()
            self.schedule_changed.emit()
        except Exception as exc:
            logger.error("Error updating schedule: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def toggle_selected_schedule(self):
        """Toggle enabled state for the selected schedule."""
        schedule = self._selected_schedule()
        if not schedule:
            QMessageBox.information(self, "Информация", "Выберите фильм для включения или отключения")
            return

        try:
            success, error = self.cmd_client.toggle_schedule(schedule.id, not schedule.enabled)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось изменить статус:\n{error}")
                return

            self.refresh_schedules()
            self.schedule_changed.emit()
        except Exception as exc:
            logger.error("Error toggling schedule: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def delete_selected(self):
        """Delete the selected schedule item."""
        schedule = self._selected_schedule()
        if not schedule:
            QMessageBox.information(self, "Информация", "Выберите запланированный фильм для удаления")
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить из расписания:\n{schedule.filename}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_schedule(schedule)

    def delete_schedule(self, schedule: ScheduleItem):
        """Delete a schedule and optionally the remote file."""
        if not self.cmd_client or not self.ssh_client:
            return

        try:
            reply = QMessageBox.question(
                self,
                "Удаление файла",
                "Удалить файл с удаленной системы?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            success, error = self.cmd_client.remove_schedule(schedule.id)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить из расписания:\n{error}")
                return

            if reply == QMessageBox.StandardButton.Yes:
                success, error = self.ssh_client.delete_file(schedule.filepath)
                if not success:
                    QMessageBox.warning(self, "Предупреждение", f"Файл не удален:\n{error}")

            QMessageBox.information(self, "Успех", "Удалено из расписания")
            self.refresh_schedules()
            self.schedule_changed.emit()
        except Exception as exc:
            logger.error("Error deleting schedule: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка удаления:\n{exc}")

    def on_item_double_clicked(self, item):
        """Double click edits a scheduled movie time."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'schedule':
            self.edit_selected_schedule()

    def set_clients(self, ssh_client, cmd_client):
        """Set the SSH and command clients."""
        self.ssh_client = ssh_client
        self.set_cmd_client(cmd_client)

    def set_cmd_client(self, client):
        """Set command client and update enabled state."""
        self.cmd_client = client
        enabled = client is not None
        self.week_grid.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.edit_btn.setEnabled(enabled)
        self.toggle_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        for widgets in self.weekday_columns.values():
            widgets['button'].setEnabled(enabled)
        if not enabled:
            self.schedules = []
            self.update_tree_with_schedules()

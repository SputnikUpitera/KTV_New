"""
Movies tab for schedule management.
"""

from pathlib import Path
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ktv_paths import VIDEO_FILE_DIALOG_FILTER, build_movie_file_path, is_supported_video_file
from .schedule_dialog import ScheduleDialog
from .upload_helpers import upload_file_with_progress
from ..models.schedule import ScheduleItem

logger = logging.getLogger(__name__)


class MoviesTab(QWidget):
    """Widget for managing movie schedules."""

    schedule_changed = pyqtSignal()
    refresh_requested = pyqtSignal()

    MONTH_NAMES = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]
    DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.schedules = []
        self.month_row_widgets = {}

        self.setup_ui()
        self.create_tree_structure()
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

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragEnabled(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.viewport().setAcceptDrops(True)
        self.tree.dragEnterEvent = self.drag_enter_event
        self.tree.dragMoveEvent = self.drag_move_event
        self.tree.dropEvent = self.drop_event
        layout.addWidget(self.tree, 1)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.setProperty("compact", True)
        self.refresh_btn.setToolTip("Обновить расписание и статус")
        self.refresh_btn.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        button_layout.addWidget(self.refresh_btn)

        self.edit_btn = QPushButton("Изменить время")
        self.edit_btn.setProperty("compact", True)
        self.edit_btn.setToolTip("Изменить время выбранного фильма")
        self.edit_btn.clicked.connect(self.edit_selected_schedule)
        button_layout.addWidget(self.edit_btn)

        self.toggle_btn = QPushButton("Вкл/выкл")
        self.toggle_btn.setProperty("compact", True)
        self.toggle_btn.setToolTip("Включить или выключить выбранный фильм")
        self.toggle_btn.clicked.connect(self.toggle_selected_schedule)
        button_layout.addWidget(self.toggle_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.setProperty("compact", True)
        self.delete_btn.setToolTip("Удалить выбранный фильм из расписания")
        self.delete_btn.clicked.connect(self.delete_selected)
        button_layout.addWidget(self.delete_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def create_tree_structure(self):
        """Create the month/day tree structure once and then update counts."""
        self.tree.clear()
        self.month_row_widgets.clear()

        for month_num, month_name in enumerate(self.MONTH_NAMES, 1):
            month_item = QTreeWidgetItem(self.tree)
            month_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'month', 'month': month_num})
            month_item.setExpanded(True)

            row_widget = QWidget(self.tree)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 1, 4, 1)
            row_layout.setSpacing(3)

            title_label = QLabel(month_name)
            title_label.setObjectName("monthHeaderLabel")
            row_layout.addWidget(title_label)

            add_btn = QToolButton(row_widget)
            add_btn.setText("+")
            add_btn.setObjectName("monthAddButton")
            add_btn.setToolTip(f"Добавить фильм в {month_name.lower()}")
            add_btn.setAccessibleName(f"Добавить фильм в {month_name.lower()}")
            add_btn.clicked.connect(lambda _, month=month_num: self.add_movie_for_month(month))
            row_layout.addWidget(add_btn)
            row_layout.addStretch()

            self.tree.setItemWidget(month_item, 0, row_widget)
            self.month_row_widgets[month_num] = {
                'label': title_label,
                'button': add_btn,
            }

    def _month_item(self, month: int) -> QTreeWidgetItem:
        return self.tree.invisibleRootItem().child(month - 1)

    def _day_item(self, month: int, day: int) -> QTreeWidgetItem:
        month_item = self._month_item(month)
        if not month_item:
            return None
        for index in range(month_item.childCount()):
            child = month_item.child(index)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get('type') == 'day' and data.get('day') == day:
                return child
        return None

    def _selected_schedule(self):
        item = self.tree.currentItem()
        if not item:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'schedule':
            return None
        return data['schedule']

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
                        # Fixed: allow older daemon versions to keep working without sync support.
                        logger.warning("Daemon does not support sync_schedules, loading schedules without sync")
                    else:
                        QMessageBox.warning(self, "Ошибка", f"Не удалось синхронизировать расписание:\n{sync_error}")
                        return

            success, schedules_data, error = self.cmd_client.list_schedules(category='movies')
            if not success:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить расписание:\n{error}")
                return

            self.schedules = [ScheduleItem(**schedule) for schedule in schedules_data]
            self.update_tree_with_schedules()
            logger.info("Loaded %s movie schedules", len(self.schedules))
        except Exception as exc:
            logger.error("Error refreshing schedules: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления:\n{exc}")

    def update_tree_with_schedules(self):
        """Render schedules and counters into the month tree."""
        schedules_by_day = {}
        month_counts = {month: 0 for month in range(1, 13)}

        for schedule in sorted(self.schedules, key=lambda item: (item.month, item.day, item.hour, item.minute, item.filename.lower())):
            schedules_by_day.setdefault((schedule.month, schedule.day), []).append(schedule)
            month_counts[schedule.month] += 1

        for month_index, month_name in enumerate(self.MONTH_NAMES, start=1):
            month_item = self._month_item(month_index)
            month_item.takeChildren()
            self._set_month_label(month_index, f"{month_name} ({month_counts.get(month_index, 0)})")

            used_days = sorted(day for (month, day) in schedules_by_day if month == month_index)
            for day in used_days:
                day_schedules = schedules_by_day[(month_index, day)]
                day_item = QTreeWidgetItem(month_item, [f"{day:02d} ({len(day_schedules)})"])
                day_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'day',
                    'month': month_index,
                    'day': day,
                })

                for schedule in day_schedules:
                    label = f"{schedule.get_time_string()}  {schedule.filename}"
                    state_prefix = "[вкл]" if schedule.enabled else "[выкл]"
                    schedule_item = QTreeWidgetItem(day_item, [f"{state_prefix} {label}"])
                    schedule_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'schedule',
                        'schedule': schedule,
                    })
                    schedule_item.setToolTip(0, schedule.filepath)

                    if schedule.enabled:
                        schedule_item.setForeground(0, QBrush(QColor(120, 220, 150)))
                    else:
                        schedule_item.setForeground(0, QBrush(QColor(140, 140, 140)))

                day_item.setExpanded(True)

            month_item.setExpanded(bool(used_days))

    def _set_month_label(self, month: int, text: str):
        """Update the visible label for a month row."""
        widgets = self.month_row_widgets.get(month)
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

    def drop_event(self, event):
        """Handle drop event for file drops."""
        if not event.mimeData().hasUrls():
            return

        item = self.tree.itemAt(event.position().toPoint())
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') not in {'day', 'month'}:
            QMessageBox.information(self, "Информация", "Перетащите файл на месяц или день")
            return

        files = [url.toLocalFile() for url in event.mimeData().urls()]
        video_files = [path for path in files if is_supported_video_file(path)]
        if not video_files:
            QMessageBox.warning(self, "Ошибка", "Не найдено видеофайлов")
            return

        for file_path in video_files:
            if data.get('type') == 'month':
                self.add_file_to_schedule(file_path, data['month'])
            else:
                self.add_file_to_schedule(file_path, data['month'], data['day'])

        event.acceptProposedAction()

    def add_movie_for_month(self, month: int):
        """Pick local movie files and add them to a selected day within the month."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите фильмы",
            "",
            VIDEO_FILE_DIALOG_FILTER,
        )
        for file_path in files:
            self.add_file_to_schedule(file_path, month)

    def add_file_to_schedule(self, file_path: str, month: int, day: int = None):
        """Prompt for schedule slot and then upload a movie into the schedule."""
        selected_day = day or 1
        dialog = ScheduleDialog(
            Path(file_path).name,
            month,
            selected_day,
            self,
            allow_day_selection=day is None,
            days_in_month=self.DAYS_IN_MONTH[month - 1],
        )
        if dialog.exec():
            chosen_day, hour, minute = dialog.get_schedule_slot()
            self.upload_and_schedule(file_path, month, chosen_day, hour, minute)

    def upload_and_schedule(self, local_path: str, month: int, day: int, hour: int, minute: int):
        """Upload file and add it to the remote schedule."""
        if not self.ssh_client or not self.cmd_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return

        filename = Path(local_path).name
        remote_path = build_movie_file_path(self.ssh_client.get_remote_home(), month, day, hour, minute, filename)

        try:
            success, error = upload_file_with_progress(self, self.ssh_client, local_path, remote_path)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{error}")
                return

            success, schedule_id, error = self.cmd_client.add_schedule(
                month=month,
                day=day,
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
        """Change the playback time of the selected movie."""
        schedule = self._selected_schedule()
        if not schedule:
            QMessageBox.information(self, "Информация", "Выберите фильм для изменения времени")
            return

        dialog = ScheduleDialog(
            schedule.filename,
            schedule.month,
            schedule.day,
            self,
            initial_hour=schedule.hour,
            initial_minute=schedule.minute,
            dialog_title="Изменение времени фильма",
            action_text="Сохранить",
        )
        if not dialog.exec():
            return

        hour, minute = dialog.get_time()
        try:
            success, _, error = self.cmd_client.update_schedule(
                schedule.id,
                schedule.month,
                schedule.day,
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
                "Удалить файл с удалённой системы?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            success, error = self.cmd_client.remove_schedule(schedule.id)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить из расписания:\n{error}")
                return

            if reply == QMessageBox.StandardButton.Yes:
                success, error = self.ssh_client.delete_file(schedule.filepath)
                if not success:
                    QMessageBox.warning(self, "Предупреждение", f"Файл не удалён:\n{error}")

            QMessageBox.information(self, "Успех", "Удалено из расписания")
            self.refresh_schedules()
            self.schedule_changed.emit()
        except Exception as exc:
            logger.error("Error deleting schedule: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка удаления:\n{exc}")

    def on_item_double_clicked(self, item, column):
        """Double click edits a scheduled movie time."""
        del column
        data = item.data(0, Qt.ItemDataRole.UserRole)
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
        self.tree.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.edit_btn.setEnabled(enabled)
        self.toggle_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        for widgets in self.month_row_widgets.values():
            widgets['button'].setEnabled(enabled)
        if not enabled:
            self.schedules = []
            self.update_tree_with_schedules()

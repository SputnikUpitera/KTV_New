"""
Movies tab for schedule management.
"""

from pathlib import Path
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ktv_paths import build_movie_file_path
from .schedule_dialog import ScheduleDialog
from ..models.schedule import ScheduleItem

logger = logging.getLogger(__name__)


class MoviesTab(QWidget):
    """Widget for managing movie schedules."""

    schedule_changed = pyqtSignal()

    MONTH_NAMES = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]
    DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv', '.wmv', '.m4v'}

    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.schedules = []

        self.setup_ui()
        self.create_tree_structure()

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.info_label = QLabel(
            "Фильмы можно перетаскивать прямо на конкретный день. "
            "При обновлении список синхронизируется с каталогами на Linux."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #aaaaaa; padding: 4px 0 8px 0;")
        layout.addWidget(self.info_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Расписание фильмов")
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

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh_schedules)
        button_layout.addWidget(refresh_btn)

        edit_btn = QPushButton("Изменить время")
        edit_btn.clicked.connect(self.edit_selected_schedule)
        button_layout.addWidget(edit_btn)

        toggle_btn = QPushButton("Вкл/выкл")
        toggle_btn.clicked.connect(self.toggle_selected_schedule)
        button_layout.addWidget(toggle_btn)

        button_layout.addStretch()

        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self.delete_selected)
        button_layout.addWidget(delete_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def create_tree_structure(self):
        """Create the month/day tree structure once and then update counts."""
        self.tree.clear()

        for month_num, (month_name, days) in enumerate(zip(self.MONTH_NAMES, self.DAYS_IN_MONTH), 1):
            month_item = QTreeWidgetItem(self.tree, [month_name])
            month_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'month', 'month': month_num})

            for day in range(1, days + 1):
                day_item = QTreeWidgetItem(month_item, [str(day)])
                day_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'day',
                    'month': month_num,
                    'day': day,
                })

    def _month_item(self, month: int) -> QTreeWidgetItem:
        return self.tree.invisibleRootItem().child(month - 1)

    def _day_item(self, month: int, day: int) -> QTreeWidgetItem:
        month_item = self._month_item(month)
        return month_item.child(day - 1) if month_item else None

    def _selected_schedule(self):
        item = self.tree.currentItem()
        if not item:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'schedule':
            return None
        return data['schedule']

    def refresh_schedules(self):
        """Reload schedules from the remote system after daemon-side sync."""
        if not self.cmd_client:
            return

        try:
            sync_success, _, sync_error = self.cmd_client.sync_schedules()
            if not sync_success:
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
        """Render schedules and counters into the static month/day tree."""
        for month_index, month_name in enumerate(self.MONTH_NAMES, start=1):
            month_item = self._month_item(month_index)
            month_item.takeChildren()
            month_item.setText(0, f"{month_name} (0)")

            for day in range(1, self.DAYS_IN_MONTH[month_index - 1] + 1):
                day_item = QTreeWidgetItem(month_item, [f"{day:02d} (0)"])
                day_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'day',
                    'month': month_index,
                    'day': day,
                })

        month_counts = {month: 0 for month in range(1, 13)}
        day_counts = {}

        for schedule in self.schedules:
            day_item = self._day_item(schedule.month, schedule.day)
            if not day_item:
                continue

            month_counts[schedule.month] += 1
            day_counts[(schedule.month, schedule.day)] = day_counts.get((schedule.month, schedule.day), 0) + 1

            label = f"{schedule.get_time_string()}  {schedule.filename}"
            schedule_item = QTreeWidgetItem(day_item, [label])
            schedule_item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'schedule',
                'schedule': schedule,
            })
            schedule_item.setToolTip(0, schedule.filepath)

            if schedule.enabled:
                schedule_item.setForeground(0, QBrush(QColor(120, 220, 150)))
            else:
                schedule_item.setForeground(0, QBrush(QColor(140, 140, 140)))

        for month_index, month_name in enumerate(self.MONTH_NAMES, start=1):
            month_item = self._month_item(month_index)
            month_count = month_counts.get(month_index, 0)
            month_item.setText(0, f"{month_name} ({month_count})")

            used_days = 0
            for day in range(1, self.DAYS_IN_MONTH[month_index - 1] + 1):
                count = day_counts.get((month_index, day), 0)
                day_item = self._day_item(month_index, day)
                day_item.setText(0, f"{day:02d} ({count})")
                day_item.setExpanded(count > 0)
                if count > 0:
                    used_days += 1

            month_item.setExpanded(used_days > 0)

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
        if not data or data.get('type') != 'day':
            QMessageBox.information(self, "Информация", "Перетащите файл на конкретный день")
            return

        files = [url.toLocalFile() for url in event.mimeData().urls()]
        video_files = [path for path in files if Path(path).suffix.lower() in self.VIDEO_EXTENSIONS]
        if not video_files:
            QMessageBox.warning(self, "Ошибка", "Не найдено видеофайлов")
            return

        for file_path in video_files:
            self.add_file_to_schedule(file_path, data['month'], data['day'])

        event.acceptProposedAction()

    def add_file_to_schedule(self, file_path: str, month: int, day: int):
        """Prompt for time and then upload a movie into the schedule."""
        dialog = ScheduleDialog(Path(file_path).name, month, day, self)
        if dialog.exec():
            hour, minute = dialog.get_time()
            self.upload_and_schedule(file_path, month, day, hour, minute)

    def _get_remote_home(self) -> str:
        """Get the remote user's home directory."""
        if self.ssh_client and self.ssh_client.is_connected():
            exit_code, stdout, _ = self.ssh_client.execute_command("echo $HOME")
            if exit_code == 0 and stdout.strip():
                return stdout.strip()
        return "/home/user"

    def upload_and_schedule(self, local_path: str, month: int, day: int, hour: int, minute: int):
        """Upload file and add it to the remote schedule."""
        if not self.ssh_client or not self.cmd_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return

        filename = Path(local_path).name
        remote_path = build_movie_file_path(self._get_remote_home(), month, day, hour, minute, filename)

        progress = QProgressDialog(f"Загрузка {filename}...", "Отмена", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        def upload_callback(transferred, total):
            percent = int((transferred / total) * 100) if total else 0
            progress.setValue(percent)

        try:
            success, error = self.ssh_client.upload_file(local_path, remote_path, callback=upload_callback)
            if not success:
                progress.close()
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{error}")
                return

            progress.setLabelText("Добавление в расписание...")
            progress.setValue(100)

            success, schedule_id, error = self.cmd_client.add_schedule(
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                filepath=remote_path,
                filename=filename,
                category='movies',
            )
            progress.close()

            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось добавить в расписание:\n{error}")
                return

            QMessageBox.information(self, "Успех", f"Фильм добавлен в расписание (ID: {schedule_id})")
            self.refresh_schedules()
            self.schedule_changed.emit()
        except Exception as exc:
            progress.close()
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
        self.cmd_client = cmd_client

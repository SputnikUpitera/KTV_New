"""
Movies tab for schedule management
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
                             QPushButton, QHBoxLayout, QMessageBox, QProgressDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from pathlib import Path
import logging

from .schedule_dialog import ScheduleDialog
from ..models.schedule import ScheduleItem

logger = logging.getLogger(__name__)


class MoviesTab(QWidget):
    """Tab for managing movie schedules"""
    
    schedule_changed = pyqtSignal()
    
    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.schedules = []
        
        self.setup_ui()
        self.create_tree_structure()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout()
        
        # Tree widget for month/day structure
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Расписание фильмов")
        self.tree.setAcceptDrops(True)
        self.tree.setDragEnabled(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        # Enable drag and drop from external sources
        self.tree.viewport().setAcceptDrops(True)
        self.tree.dragEnterEvent = self.drag_enter_event
        self.tree.dragMoveEvent = self.drag_move_event
        self.tree.dropEvent = self.drop_event
        
        layout.addWidget(self.tree)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh_schedules)
        button_layout.addWidget(refresh_btn)
        
        button_layout.addStretch()
        
        delete_btn = QPushButton("Удалить выбранное")
        delete_btn.clicked.connect(self.delete_selected)
        button_layout.addWidget(delete_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def create_tree_structure(self):
        """Create the month/day tree structure"""
        self.tree.clear()
        
        months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
        
        days_in_month = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        
        for month_num, (month_name, days) in enumerate(zip(months, days_in_month), 1):
            month_item = QTreeWidgetItem(self.tree, [month_name])
            month_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'month', 'month': month_num})
            
            for day in range(1, days + 1):
                day_item = QTreeWidgetItem(month_item, [f"{day}"])
                day_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'day',
                    'month': month_num,
                    'day': day
                })
    
    def refresh_schedules(self):
        """Reload schedules from remote system"""
        if not self.cmd_client:
            return
        
        try:
            success, schedules_data, error = self.cmd_client.list_schedules(category='movies')
            
            if success:
                self.schedules = [ScheduleItem(**s) for s in schedules_data]
                self.update_tree_with_schedules()
                logger.info(f"Loaded {len(self.schedules)} movie schedules")
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить расписание:\n{error}")
        except Exception as e:
            logger.error(f"Error refreshing schedules: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления:\n{str(e)}")
    
    def update_tree_with_schedules(self):
        """Update tree items with schedule information"""
        # Clear all schedule items first
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            month_item = root.child(i)
            for j in range(month_item.childCount()):
                day_item = month_item.child(j)
                # Remove all children (schedules)
                day_item.takeChildren()
        
        # Add schedule items
        for schedule in self.schedules:
            # Find the corresponding day item
            month_item = root.child(schedule.month - 1)
            if month_item:
                day_item = month_item.child(schedule.day - 1)
                if day_item:
                    schedule_item = QTreeWidgetItem(day_item, [str(schedule)])
                    schedule_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'schedule',
                        'schedule': schedule
                    })
                    
                    # Color code based on enabled status
                    if schedule.enabled:
                        schedule_item.setForeground(0, QBrush(QColor(0, 200, 0)))
                    else:
                        schedule_item.setForeground(0, QBrush(QColor(128, 128, 128)))
    
    def drag_enter_event(self, event):
        """Handle drag enter event"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def drag_move_event(self, event):
        """Handle drag move event"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def drop_event(self, event):
        """Handle drop event for file drops"""
        if not event.mimeData().hasUrls():
            return
        
        # Get the item at drop position
        item = self.tree.itemAt(event.position().toPoint())
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'day':
            QMessageBox.information(self, "Информация", "Перетащите файл на конкретный день")
            return
        
        month = data['month']
        day = data['day']
        
        # Get dropped files
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        
        # Filter for video files
        video_extensions = {'.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv'}
        video_files = [f for f in files if Path(f).suffix.lower() in video_extensions]
        
        if not video_files:
            QMessageBox.warning(self, "Ошибка", "Не найдено видеофайлов")
            return
        
        # Process each file
        for file_path in video_files:
            self.add_file_to_schedule(file_path, month, day)
        
        event.acceptProposedAction()
    
    def add_file_to_schedule(self, file_path: str, month: int, day: int):
        """Add a file to the schedule"""
        # Show time selection dialog
        filename = Path(file_path).name
        dialog = ScheduleDialog(filename, month, day, self)
        
        if dialog.exec():
            hour, minute = dialog.get_time()
            
            # Upload and schedule the file
            self.upload_and_schedule(file_path, month, day, hour, minute)
    
    def upload_and_schedule(self, local_path: str, month: int, day: int, hour: int, minute: int):
        """Upload file and add to schedule"""
        if not self.ssh_client or not self.cmd_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return
        
        filename = Path(local_path).name
        remote_path = f"/opt/ktv/media/movies/{filename}"
        
        # Progress dialog
        progress = QProgressDialog(f"Загрузка {filename}...", "Отмена", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        
        def upload_callback(transferred, total):
            percent = int((transferred / total) * 100)
            progress.setValue(percent)
        
        try:
            # Upload file
            success, error = self.ssh_client.upload_file(local_path, remote_path, callback=upload_callback)
            
            if not success:
                progress.close()
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{error}")
                return
            
            progress.setLabelText("Добавление в расписание...")
            progress.setValue(100)
            
            # Add to schedule
            success, schedule_id, error = self.cmd_client.add_schedule(
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                filepath=remote_path,
                filename=filename,
                category='movies'
            )
            
            progress.close()
            
            if success:
                QMessageBox.information(self, "Успех", f"Файл добавлен в расписание (ID: {schedule_id})")
                self.refresh_schedules()
                self.schedule_changed.emit()
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось добавить в расписание:\n{error}")
        
        except Exception as e:
            progress.close()
            logger.error(f"Error uploading/scheduling file: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{str(e)}")
    
    def delete_selected(self):
        """Delete the selected schedule item"""
        item = self.tree.currentItem()
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'schedule':
            QMessageBox.information(self, "Информация", "Выберите запланированный файл для удаления")
            return
        
        schedule = data['schedule']
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить из расписания:\n{schedule.filename}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_schedule(schedule)
    
    def delete_schedule(self, schedule: ScheduleItem):
        """Delete a schedule and optionally the file"""
        if not self.cmd_client or not self.ssh_client:
            return
        
        try:
            # Ask if file should also be deleted
            reply = QMessageBox.question(
                self, "Удаление файла",
                "Удалить файл с удалённой системы?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            # Remove from schedule
            success, error = self.cmd_client.remove_schedule(schedule.id)
            
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить из расписания:\n{error}")
                return
            
            # Delete file if requested
            if reply == QMessageBox.StandardButton.Yes:
                success, error = self.ssh_client.delete_file(schedule.filepath)
                if not success:
                    QMessageBox.warning(self, "Предупреждение", f"Файл не удалён:\n{error}")
            
            QMessageBox.information(self, "Успех", "Удалено из расписания")
            self.refresh_schedules()
            self.schedule_changed.emit()
        
        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка удаления:\n{str(e)}")
    
    def on_item_double_clicked(self, item, column):
        """Handle double-click on schedule item (toggle enabled)"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'schedule':
            return
        
        schedule = data['schedule']
        
        # Toggle enabled status
        new_status = not schedule.enabled
        
        try:
            success, error = self.cmd_client.toggle_schedule(schedule.id, new_status)
            
            if success:
                self.refresh_schedules()
                self.schedule_changed.emit()
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось изменить статус:\n{error}")
        
        except Exception as e:
            logger.error(f"Error toggling schedule: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{str(e)}")
    
    def set_clients(self, ssh_client, cmd_client):
        """Set the SSH and command clients"""
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client

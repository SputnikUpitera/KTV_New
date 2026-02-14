"""
Clips tab for playlist management
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QPushButton, QMessageBox, QInputDialog, QListWidgetItem,
                             QProgressDialog, QLabel)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from pathlib import Path
import logging

from ..models.playlist import Playlist

logger = logging.getLogger(__name__)


class ClipsTab(QWidget):
    """Tab for managing video playlists"""
    
    playlist_changed = pyqtSignal()
    
    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.playlists = []
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the user interface"""
        main_layout = QHBoxLayout()
        
        # Left side - playlists list
        left_layout = QVBoxLayout()
        
        left_layout.addWidget(QLabel("Плейлисты:"))
        
        self.playlist_list = QListWidget()
        self.playlist_list.setMaximumWidth(250)
        self.playlist_list.itemDoubleClicked.connect(self.toggle_active_playlist)
        left_layout.addWidget(self.playlist_list)
        
        # Playlist buttons
        playlist_btn_layout = QVBoxLayout()
        
        create_btn = QPushButton("Создать плейлист")
        create_btn.clicked.connect(self.create_playlist)
        playlist_btn_layout.addWidget(create_btn)
        
        delete_btn = QPushButton("Удалить плейлист")
        delete_btn.clicked.connect(self.delete_playlist)
        playlist_btn_layout.addWidget(delete_btn)
        
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh_playlists)
        playlist_btn_layout.addWidget(refresh_btn)
        
        playlist_btn_layout.addStretch()
        
        left_layout.addLayout(playlist_btn_layout)
        
        main_layout.addLayout(left_layout)
        
        # Right side - file management
        right_layout = QVBoxLayout()
        
        info_label = QLabel("Перетащите видеофайлы сюда для добавления в плейлист")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #888; padding: 20px;")
        right_layout.addWidget(info_label)
        
        # Drop area (simplified - just a widget that accepts drops)
        self.drop_area = QWidget()
        self.drop_area.setMinimumHeight(200)
        self.drop_area.setAcceptDrops(True)
        self.drop_area.dragEnterEvent = self.drag_enter_event
        self.drop_area.dropEvent = self.drop_event
        self.drop_area.setStyleSheet("""
            QWidget {
                border: 2px dashed #555;
                border-radius: 10px;
                background-color: #2a2a2a;
            }
        """)
        right_layout.addWidget(self.drop_area)
        
        right_layout.addStretch()
        
        main_layout.addLayout(right_layout, 1)
        
        self.setLayout(main_layout)
    
    def refresh_playlists(self):
        """Reload playlists from remote system"""
        if not self.cmd_client:
            return
        
        try:
            success, playlists_data, error = self.cmd_client.list_playlists()
            
            if success:
                self.playlists = [Playlist(**p) for p in playlists_data]
                self.update_playlist_list()
                logger.info(f"Loaded {len(self.playlists)} playlists")
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить плейлисты:\n{error}")
        except Exception as e:
            logger.error(f"Error refreshing playlists: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления:\n{str(e)}")
    
    def update_playlist_list(self):
        """Update the playlist list widget"""
        self.playlist_list.clear()
        
        for playlist in self.playlists:
            item = QListWidgetItem(str(playlist))
            item.setData(Qt.ItemDataRole.UserRole, playlist)
            
            # Color active playlist
            if playlist.active:
                item.setForeground(QBrush(QColor(0, 200, 0)))
                item.setBackground(QBrush(QColor(40, 60, 40)))
            
            self.playlist_list.addItem(item)
    
    def create_playlist(self):
        """Create a new playlist"""
        if not self.cmd_client or not self.ssh_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return
        
        # Get playlist name
        name, ok = QInputDialog.getText(
            self, "Новый плейлист",
            "Введите название плейлиста:"
        )
        
        if not ok or not name:
            return
        
        # Create folder path
        folder_path = f"/opt/ktv/media/clips/{name}"
        
        try:
            # Create directory on remote system
            success, error = self.ssh_client.create_directory(folder_path)
            
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать папку:\n{error}")
                return
            
            # Create playlist in database
            success, playlist_id, error = self.cmd_client.create_playlist(name, folder_path)
            
            if success:
                QMessageBox.information(self, "Успех", f"Плейлист создан (ID: {playlist_id})")
                self.refresh_playlists()
                self.playlist_changed.emit()
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать плейлист:\n{error}")
        
        except Exception as e:
            logger.error(f"Error creating playlist: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{str(e)}")
    
    def delete_playlist(self):
        """Delete the selected playlist"""
        item = self.playlist_list.currentItem()
        if not item:
            QMessageBox.information(self, "Информация", "Выберите плейлист для удаления")
            return
        
        playlist = item.data(Qt.ItemDataRole.UserRole)
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить плейлист '{playlist.name}'?\nФайлы останутся на удалённой системе.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                success, error = self.cmd_client.delete_playlist(playlist.id)
                
                if success:
                    QMessageBox.information(self, "Успех", "Плейлист удалён")
                    self.refresh_playlists()
                    self.playlist_changed.emit()
                else:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось удалить плейлист:\n{error}")
            
            except Exception as e:
                logger.error(f"Error deleting playlist: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{str(e)}")
    
    def toggle_active_playlist(self, item):
        """Toggle active status of playlist (double-click)"""
        playlist = item.data(Qt.ItemDataRole.UserRole)
        
        try:
            success, error = self.cmd_client.set_active_playlist(playlist.id)
            
            if success:
                self.refresh_playlists()
                self.playlist_changed.emit()
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось активировать плейлист:\n{error}")
        
        except Exception as e:
            logger.error(f"Error setting active playlist: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{str(e)}")
    
    def drag_enter_event(self, event):
        """Handle drag enter event"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def drop_event(self, event):
        """Handle drop event for file drops"""
        if not event.mimeData().hasUrls():
            return
        
        # Get selected playlist
        item = self.playlist_list.currentItem()
        if not item:
            QMessageBox.information(self, "Информация", "Выберите плейлист для добавления файлов")
            return
        
        playlist = item.data(Qt.ItemDataRole.UserRole)
        
        # Get dropped files
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        
        # Filter for video files
        video_extensions = {'.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv'}
        video_files = [f for f in files if Path(f).suffix.lower() in video_extensions]
        
        if not video_files:
            QMessageBox.warning(self, "Ошибка", "Не найдено видеофайлов")
            return
        
        # Upload files to playlist folder
        self.upload_files_to_playlist(video_files, playlist)
        
        event.acceptProposedAction()
    
    def upload_files_to_playlist(self, files, playlist):
        """Upload files to playlist folder"""
        if not self.ssh_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return
        
        for file_path in files:
            filename = Path(file_path).name
            remote_path = f"{playlist.folder_path}/{filename}"
            
            # Progress dialog
            progress = QProgressDialog(f"Загрузка {filename}...", "Отмена", 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()
            
            def upload_callback(transferred, total):
                percent = int((transferred / total) * 100)
                progress.setValue(percent)
            
            try:
                success, error = self.ssh_client.upload_file(file_path, remote_path, callback=upload_callback)
                
                progress.close()
                
                if not success:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить {filename}:\n{error}")
                    break
            
            except Exception as e:
                progress.close()
                logger.error(f"Error uploading file: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки {filename}:\n{str(e)}")
                break
        else:
            QMessageBox.information(self, "Успех", f"Загружено {len(files)} файлов в плейлист '{playlist.name}'")
    
    def set_clients(self, ssh_client, cmd_client):
        """Set the SSH and command clients"""
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client

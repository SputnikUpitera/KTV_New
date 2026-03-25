"""
Clips tab for playlist management.
"""

from pathlib import Path
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ktv_paths import build_playlist_directory
from ..models.playlist import Playlist

logger = logging.getLogger(__name__)


class ClipsTab(QWidget):
    """Widget for managing clip playlists."""

    playlist_changed = pyqtSignal()
    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv', '.wmv', '.m4v'}

    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.playlists = []

        self.setup_ui()
        self.set_cmd_client(cmd_client)

    def setup_ui(self):
        """Setup the user interface."""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Плейлисты:"))

        self.playlist_list = QListWidget()
        self.playlist_list.setMinimumWidth(240)
        self.playlist_list.currentItemChanged.connect(self.on_playlist_selected)
        self.playlist_list.itemDoubleClicked.connect(self.toggle_active_playlist)
        left_layout.addWidget(self.playlist_list, 1)

        playlist_btn_layout = QHBoxLayout()

        self.create_btn = QPushButton("Создать")
        self.create_btn.clicked.connect(self.create_playlist)
        playlist_btn_layout.addWidget(self.create_btn)

        self.activate_btn = QPushButton("Активировать")
        self.activate_btn.clicked.connect(self.activate_selected_playlist)
        playlist_btn_layout.addWidget(self.activate_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self.delete_playlist)
        playlist_btn_layout.addWidget(self.delete_btn)

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.refresh_playlists)
        playlist_btn_layout.addWidget(self.refresh_btn)

        left_layout.addLayout(playlist_btn_layout)
        main_layout.addLayout(left_layout, 4)

        right_layout = QVBoxLayout()

        self.selection_label = QLabel("Плейлист не выбран")
        self.selection_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        right_layout.addWidget(self.selection_label)

        self.path_label = QLabel("Каталог: —")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #999999;")
        right_layout.addWidget(self.path_label)

        self.drop_area = QFrame()
        self.drop_area.setAcceptDrops(True)
        self.drop_area.dragEnterEvent = self.drag_enter_event
        self.drop_area.dragMoveEvent = self.drag_move_event
        self.drop_area.dropEvent = self.drop_event
        self.drop_area.setStyleSheet("""
            QFrame {
                border: 1px dashed #666;
                border-radius: 10px;
                background-color: #2b2b2b;
            }
        """)
        drop_layout = QVBoxLayout(self.drop_area)
        drop_layout.setContentsMargins(14, 12, 14, 12)

        drop_title = QLabel("Добавление файлов")
        drop_title.setStyleSheet("font-weight: 600;")
        drop_layout.addWidget(drop_title)

        drop_hint = QLabel(
            "Перетащите видеофайлы сюда. Файлы будут загружены в выбранный плейлист "
            "в каталоге ~/oktv/clips."
        )
        drop_hint.setWordWrap(True)
        drop_hint.setStyleSheet("color: #aaaaaa;")
        drop_layout.addWidget(drop_hint)
        right_layout.addWidget(self.drop_area)

        right_layout.addWidget(QLabel("Файлы выбранного плейлиста:"))
        self.files_list = QListWidget()
        right_layout.addWidget(self.files_list, 1)

        main_layout.addLayout(right_layout, 6)
        self.setLayout(main_layout)

    def _selected_playlist(self):
        item = self.playlist_list.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def refresh_playlists(self):
        """Reload playlists from the remote system after daemon-side sync."""
        if not self.cmd_client:
            QMessageBox.information(self, "Информация", "Нет подключения к daemon")
            return

        current_name = self._selected_playlist().name if self._selected_playlist() else None

        try:
            sync_success, _, sync_error = self.cmd_client.sync_playlists()
            if not sync_success:
                QMessageBox.warning(self, "Ошибка", f"Не удалось синхронизировать плейлисты:\n{sync_error}")
                return

            success, playlists_data, error = self.cmd_client.list_playlists()
            if not success:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить плейлисты:\n{error}")
                return

            self.playlists = [Playlist(**playlist) for playlist in playlists_data]
            self.update_playlist_list(current_name=current_name)
            logger.info("Loaded %s playlists", len(self.playlists))
        except Exception as exc:
            logger.error("Error refreshing playlists: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления:\n{exc}")

    def update_playlist_list(self, current_name=None):
        """Update the playlist list widget."""
        self.playlist_list.clear()
        current_row = -1

        for index, playlist in enumerate(self.playlists):
            item = QListWidgetItem(str(playlist))
            item.setData(Qt.ItemDataRole.UserRole, playlist)
            item.setToolTip(playlist.folder_path)

            if playlist.active:
                item.setForeground(QBrush(QColor(120, 220, 150)))
                item.setBackground(QBrush(QColor(42, 62, 48)))

            self.playlist_list.addItem(item)

            if current_name and playlist.name == current_name:
                current_row = index
            elif current_row == -1 and playlist.active:
                current_row = index

        if current_row >= 0:
            self.playlist_list.setCurrentRow(current_row)
        elif self.playlist_list.count():
            self.playlist_list.setCurrentRow(0)
        else:
            self.files_list.clear()
            self.selection_label.setText("Плейлист не выбран")
            self.path_label.setText("Каталог: —")

    def create_playlist(self):
        """Create a new playlist."""
        if not self.cmd_client or not self.ssh_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return

        name, ok = QInputDialog.getText(self, "Новый плейлист", "Введите название плейлиста:")
        name = name.strip() if ok and name else ""
        if not name:
            return

        folder_path = build_playlist_directory(self._get_remote_home(), name)

        try:
            success, error = self.ssh_client.create_directory(folder_path)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать папку:\n{error}")
                return

            success, playlist_id, error = self.cmd_client.create_playlist(name, folder_path)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать плейлист:\n{error}")
                return

            QMessageBox.information(self, "Успех", f"Плейлист создан (ID: {playlist_id})")
            self.refresh_playlists()
            self.playlist_changed.emit()
        except Exception as exc:
            logger.error("Error creating playlist: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def delete_playlist(self):
        """Delete the selected playlist record."""
        playlist = self._selected_playlist()
        if not playlist:
            QMessageBox.information(self, "Информация", "Выберите плейлист для удаления")
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить плейлист '{playlist.name}'?\nФайлы останутся на удалённой системе.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            success, error = self.cmd_client.delete_playlist(playlist.id)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить плейлист:\n{error}")
                return

            QMessageBox.information(self, "Успех", "Плейлист удалён")
            self.refresh_playlists()
            self.playlist_changed.emit()
        except Exception as exc:
            logger.error("Error deleting playlist: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def activate_selected_playlist(self):
        """Make the selected playlist active."""
        item = self.playlist_list.currentItem()
        if item:
            self.toggle_active_playlist(item)

    def toggle_active_playlist(self, item):
        """Set playlist as active."""
        playlist = item.data(Qt.ItemDataRole.UserRole)
        try:
            success, error = self.cmd_client.set_active_playlist(playlist.id)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось активировать плейлист:\n{error}")
                return

            self.refresh_playlists()
            self.playlist_changed.emit()
        except Exception as exc:
            logger.error("Error setting active playlist: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def on_playlist_selected(self, current, previous):
        """Update the details panel when playlist selection changes."""
        del previous
        playlist = current.data(Qt.ItemDataRole.UserRole) if current else None
        if not playlist:
            self.files_list.clear()
            self.selection_label.setText("Плейлист не выбран")
            self.path_label.setText("Каталог: —")
            return

        title = playlist.name
        if playlist.active:
            title += "  [активный]"
        self.selection_label.setText(title)
        self.path_label.setText(f"Каталог: {playlist.folder_path}")
        self.refresh_playlist_files(playlist)

    def refresh_playlist_files(self, playlist):
        """List files from the selected playlist directory."""
        self.files_list.clear()

        if not self.ssh_client or not self.ssh_client.is_connected():
            return

        success, files, error = self.ssh_client.list_directory(playlist.folder_path)
        if not success:
            self.files_list.addItem(f"Не удалось прочитать каталог: {error}")
            return

        visible_files = sorted(
            [name for name in files if Path(name).suffix.lower() in self.VIDEO_EXTENSIONS],
            key=str.lower,
        )
        if not visible_files:
            self.files_list.addItem("Файлы пока не добавлены")
            return

        for filename in visible_files:
            self.files_list.addItem(filename)

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

        playlist = self._selected_playlist()
        if not playlist:
            QMessageBox.information(self, "Информация", "Выберите плейлист для добавления файлов")
            return

        files = [url.toLocalFile() for url in event.mimeData().urls()]
        video_files = [path for path in files if Path(path).suffix.lower() in self.VIDEO_EXTENSIONS]
        if not video_files:
            QMessageBox.warning(self, "Ошибка", "Не найдено видеофайлов")
            return

        self.upload_files_to_playlist(video_files, playlist)
        event.acceptProposedAction()

    def upload_files_to_playlist(self, files, playlist):
        """Upload files to the playlist folder."""
        if not self.ssh_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return

        for file_path in files:
            filename = Path(file_path).name
            remote_path = f"{playlist.folder_path}/{filename}"

            progress = QProgressDialog(f"Загрузка {filename}...", "Отмена", 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()

            def upload_callback(transferred, total):
                percent = int((transferred / total) * 100) if total else 0
                progress.setValue(percent)

            try:
                success, error = self.ssh_client.upload_file(file_path, remote_path, callback=upload_callback)
                progress.close()

                if not success:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить {filename}:\n{error}")
                    break
            except Exception as exc:
                progress.close()
                logger.error("Error uploading file: %s", exc)
                QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки {filename}:\n{exc}")
                break
        else:
            QMessageBox.information(self, "Успех", f"Загружено {len(files)} файлов в плейлист '{playlist.name}'")
            self.refresh_playlists()
            self.playlist_changed.emit()

    def _get_remote_home(self) -> str:
        """Get the remote user's home directory."""
        if self.ssh_client and self.ssh_client.is_connected():
            exit_code, stdout, _ = self.ssh_client.execute_command("echo $HOME")
            if exit_code == 0 and stdout.strip():
                return stdout.strip()
        return "/home/user"

    def set_clients(self, ssh_client, cmd_client):
        """Set the SSH and command clients."""
        self.ssh_client = ssh_client
        self.set_cmd_client(cmd_client)

    def set_cmd_client(self, client):
        """Set command client and update enabled state."""
        self.cmd_client = client
        enabled = client is not None
        self.playlist_list.setEnabled(enabled)
        self.files_list.setEnabled(enabled)
        self.drop_area.setEnabled(enabled)
        self.create_btn.setEnabled(enabled)
        self.activate_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)

        if not enabled:
            self.playlist_list.clear()
            self.files_list.clear()
            self.selection_label.setText("Плейлист не выбран")
            self.path_label.setText("Каталог: —")
        self.cmd_client = cmd_client

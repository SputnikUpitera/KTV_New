"""
Clips tab for playlist management.
"""

from pathlib import Path
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ktv_paths import VIDEO_FILE_DIALOG_FILTER, is_supported_video_file
from .upload_helpers import upload_file_with_progress
from ..models.playlist import Playlist

logger = logging.getLogger(__name__)


class ClipsTab(QWidget):
    """Widget for managing clip playlists."""

    playlist_changed = pyqtSignal()

    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.playlists = []

        self.setup_ui()
        self.set_cmd_client(cmd_client)

    def setup_ui(self):
        """Setup the user interface."""
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(10, 0, 0, 0)
        root_layout.setSpacing(6)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(28)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.section_label = QLabel("Плейлисты:")
        self.section_label.setObjectName("playlistSectionLabel")
        self.section_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        left_layout.addWidget(self.section_label)

        self.playlist_list = QListWidget()
        self.playlist_list.setMinimumWidth(240)
        self.playlist_list.currentItemChanged.connect(self.on_playlist_selected)
        self.playlist_list.itemDoubleClicked.connect(self.toggle_active_playlist)
        left_layout.addWidget(self.playlist_list, 1)

        playlist_btn_layout = QHBoxLayout()
        playlist_btn_layout.setContentsMargins(0, 0, 0, 0)
        playlist_btn_layout.setSpacing(8)

        self.create_btn = QPushButton("Создать")
        self.create_btn.setProperty("compact", True)
        self.create_btn.setToolTip("Создать новый плейлист")
        self.create_btn.clicked.connect(self.create_playlist)
        playlist_btn_layout.addWidget(self.create_btn)

        self.activate_btn = QPushButton("Вкл")
        self.activate_btn.setProperty("compact", True)
        self.activate_btn.setToolTip("Сделать выбранный плейлист активным")
        self.activate_btn.setAccessibleName("Сделать выбранный плейлист активным")
        self.activate_btn.clicked.connect(self.activate_selected_playlist)
        playlist_btn_layout.addWidget(self.activate_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.setProperty("compact", True)
        self.delete_btn.setToolTip("Удалить выбранный плейлист")
        self.delete_btn.clicked.connect(self.delete_playlist)
        playlist_btn_layout.addWidget(self.delete_btn)

        left_layout.addLayout(playlist_btn_layout)
        main_layout.addLayout(left_layout, 4)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(6)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.drop_area = QFrame()
        self.drop_area.setAcceptDrops(True)
        self.drop_area.dragEnterEvent = self.drag_enter_event
        self.drop_area.dragMoveEvent = self.drag_move_event
        self.drop_area.dropEvent = self.drop_event
        self.drop_area.setStyleSheet("""
            QFrame {
                border: 1px dashed #666;
                background-color: #2b2b2b;
            }
        """)
        drop_layout = QVBoxLayout(self.drop_area)
        drop_layout.setContentsMargins(0, 0, 0, 0)
        self.drop_area.setMinimumHeight(72)
        self.drop_area.hide()

        self.files_section_label = QLabel("Файлы выбранного плейлиста:")
        self.files_section_label.setObjectName("playlistSectionLabel")
        self.files_section_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        right_layout.addWidget(self.files_section_label)

        self.files_list = QListWidget()
        self.files_list.setAcceptDrops(True)
        self.files_list.dragEnterEvent = self.drag_enter_event
        self.files_list.dragMoveEvent = self.drag_move_event
        self.files_list.dropEvent = self.drop_event
        self.files_list.itemSelectionChanged.connect(self._update_file_buttons)
        right_layout.addWidget(self.files_list, 1)

        files_btn_layout = QHBoxLayout()
        files_btn_layout.setContentsMargins(0, 0, 0, 0)
        files_btn_layout.setSpacing(8)

        self.add_file_btn = QPushButton("Добавить")
        self.add_file_btn.setProperty("compact", True)
        self.add_file_btn.setToolTip("Добавить файлы в выбранный плейлист")
        self.add_file_btn.clicked.connect(self.add_files_to_selected_playlist)
        files_btn_layout.addWidget(self.add_file_btn)

        self.play_file_btn = QPushButton("Вкл")
        self.play_file_btn.setProperty("compact", True)
        self.play_file_btn.setToolTip("Воспроизвести выбранный файл")
        self.play_file_btn.setAccessibleName("Воспроизвести выбранный файл")
        self.play_file_btn.clicked.connect(self.play_selected_file)
        files_btn_layout.addWidget(self.play_file_btn)

        self.delete_file_btn = QPushButton("Удалить")
        self.delete_file_btn.setProperty("compact", True)
        self.delete_file_btn.setToolTip("Удалить выбранный файл из плейлиста")
        self.delete_file_btn.clicked.connect(self.delete_selected_file)
        files_btn_layout.addWidget(self.delete_file_btn)

        right_layout.addLayout(files_btn_layout)

        main_layout.addLayout(right_layout, 6)
        root_layout.addLayout(main_layout, 1)
        self.setLayout(root_layout)

    def _selected_playlist(self):
        item = self.playlist_list.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _selected_playlist_file(self):
        item = self.files_list.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _set_files_placeholder(self, text: str):
        self.files_list.clear()
        item = QListWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.files_list.addItem(item)
        self._update_file_buttons()

    def _update_file_buttons(self):
        has_playlist = self._selected_playlist() is not None
        has_file = self._selected_playlist_file() is not None
        enabled = self.cmd_client is not None
        self.add_file_btn.setEnabled(enabled and has_playlist)
        self.play_file_btn.setEnabled(enabled and has_file)
        self.delete_file_btn.setEnabled(enabled and has_file)

    def refresh_playlists(self, do_sync: bool = False):
        """Reload playlists from the remote system and sync only when requested."""
        if not self.cmd_client:
            QMessageBox.information(self, "Информация", "Нет подключения к daemon")
            return

        current_name = self._selected_playlist().name if self._selected_playlist() else None

        try:
            if do_sync:
                sync_success, _, sync_error = self.cmd_client.sync_playlists()
                if not sync_success:
                    if "Unknown command: sync_playlists" in sync_error:
                        # Fixed: allow older daemon versions to keep working without sync support.
                        logger.warning("Daemon does not support sync_playlists, loading playlists without sync")
                    else:
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
            label = str(playlist)
            if playlist.active:
                label = f"[активен] {label}"
            item = QListWidgetItem(label)
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
            self._set_files_placeholder("Плейлист не выбран")

    def create_playlist(self):
        """Create a new playlist."""
        if not self.cmd_client or not self.ssh_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return

        name, ok = QInputDialog.getText(self, "Новый плейлист", "Введите название плейлиста:")
        name = name.strip() if ok and name else ""
        if not name:
            return

        try:
            success, playlist_id, error = self.cmd_client.create_playlist(name)
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
            self._set_files_placeholder("Плейлист не выбран")
            return

        self.refresh_playlist_files(playlist)

    def refresh_playlist_files(self, playlist):
        """List files from the selected playlist directory."""
        current_file = self._selected_playlist_file()
        current_name = current_file['filename'] if current_file else None
        self.files_list.clear()

        if not self.ssh_client or not self.ssh_client.is_connected():
            self._update_file_buttons()
            return

        success, files, error = self.ssh_client.list_directory(playlist.folder_path)
        if not success:
            self._set_files_placeholder(f"Не удалось прочитать каталог: {error}")
            return

        visible_files = sorted(
            [name for name in files if is_supported_video_file(name)],
            key=str.lower,
        )
        if not visible_files:
            self._set_files_placeholder("Файлы пока не добавлены")
            return

        selected_row = -1
        for index, filename in enumerate(visible_files):
            item = QListWidgetItem(filename)
            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    'filename': filename,
                    'filepath': f"{playlist.folder_path.rstrip('/')}/{filename}",
                }
            )
            self.files_list.addItem(item)
            if current_name and filename == current_name:
                selected_row = index

        if selected_row >= 0:
            self.files_list.setCurrentRow(selected_row)
        elif self.files_list.count():
            self.files_list.setCurrentRow(0)
        self._update_file_buttons()

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
        video_files = [path for path in files if is_supported_video_file(path)]
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

            try:
                success, error = upload_file_with_progress(self, self.ssh_client, file_path, remote_path)

                if not success:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить {filename}:\n{error}")
                    break
            except Exception as exc:
                logger.error("Error uploading file: %s", exc)
                QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки {filename}:\n{exc}")
                break
        else:
            QMessageBox.information(self, "Успех", f"Загружено {len(files)} файлов в плейлист '{playlist.name}'")
            self.refresh_playlists()
            self.playlist_changed.emit()

    def add_files_to_selected_playlist(self):
        """Open a file dialog and upload files to the selected playlist."""
        playlist = self._selected_playlist()
        if not playlist:
            QMessageBox.information(self, "Информация", "Выберите плейлист для добавления файлов")
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Добавить файлы в плейлист",
            "",
            VIDEO_FILE_DIALOG_FILTER,
        )
        if not files:
            return

        self.upload_files_to_playlist(files, playlist)

    def play_selected_file(self):
        """Activate and immediately play the selected playlist file."""
        playlist = self._selected_playlist()
        file_info = self._selected_playlist_file()
        if not playlist or not file_info:
            QMessageBox.information(self, "Информация", "Выберите файл плейлиста")
            return

        try:
            if not playlist.active:
                success, error = self.cmd_client.set_active_playlist(playlist.id)
                if not success:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось активировать плейлист:\n{error}")
                    return

            success, _, error = self.cmd_client.play_playlist_file(file_info['filename'])
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось включить файл:\n{error}")
                return

            self.refresh_playlists()
            self.playlist_changed.emit()
        except Exception as exc:
            logger.error("Error playing playlist file: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def delete_selected_file(self):
        """Delete the selected file from the playlist directory."""
        playlist = self._selected_playlist()
        file_info = self._selected_playlist_file()
        if not playlist or not file_info:
            QMessageBox.information(self, "Информация", "Выберите файл для удаления")
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить файл '{file_info['filename']}' из плейлиста '{playlist.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            success, error = self.ssh_client.delete_file(file_info['filepath'])
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить файл:\n{error}")
                return

            self.refresh_playlists()
            self.playlist_changed.emit()
        except Exception as exc:
            logger.error("Error deleting playlist file: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

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
        self.create_btn.setEnabled(enabled)
        self.activate_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        self._update_file_buttons()

        if not enabled:
            self.playlist_list.clear()
            self._set_files_placeholder("Нет подключения")

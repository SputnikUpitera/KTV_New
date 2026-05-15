"""
Clips tab for single-list clip management.
"""

from pathlib import Path, PurePosixPath
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ktv_paths import (
    VIDEO_FILE_DIALOG_FILTER,
    get_clips_root,
    is_supported_video_file,
    validate_clip_filename,
)
from .upload_helpers import upload_file_with_progress

logger = logging.getLogger(__name__)


class ClipsTab(QWidget):
    """Widget for managing the single clip list."""

    playlist_changed = pyqtSignal()

    def __init__(self, ssh_client=None, cmd_client=None, parent=None):
        super().__init__(parent)
        self.ssh_client = ssh_client
        self.cmd_client = cmd_client
        self.clip_folder = None

        self.setup_ui()
        self.set_cmd_client(cmd_client)

    def setup_ui(self):
        """Setup the user interface."""
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(10, 0, 0, 0)
        root_layout.setSpacing(6)

        self.section_label = QLabel("Клипы:")
        self.section_label.setObjectName("playlistSectionLabel")
        self.section_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        root_layout.addWidget(self.section_label)

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
        self.drop_area.setMinimumHeight(72)
        self.drop_area.hide()

        self.files_list = QListWidget()
        self.files_list.setAcceptDrops(True)
        self.files_list.dragEnterEvent = self.drag_enter_event
        self.files_list.dragMoveEvent = self.drag_move_event
        self.files_list.dropEvent = self.drop_event
        self.files_list.itemSelectionChanged.connect(self._update_file_buttons)
        root_layout.addWidget(self.files_list, 1)

        files_btn_layout = QHBoxLayout()
        files_btn_layout.setContentsMargins(0, 0, 0, 0)
        files_btn_layout.setSpacing(8)

        self.add_file_btn = QPushButton("Добавить")
        self.add_file_btn.setProperty("compact", True)
        self.add_file_btn.setToolTip("Добавить файлы в список клипов")
        self.add_file_btn.clicked.connect(self.add_files_to_clip_list)
        files_btn_layout.addWidget(self.add_file_btn)

        self.play_file_btn = QPushButton("Вкл")
        self.play_file_btn.setProperty("compact", True)
        self.play_file_btn.setToolTip("Воспроизвести выбранный файл")
        self.play_file_btn.setAccessibleName("Воспроизвести выбранный файл")
        self.play_file_btn.clicked.connect(self.play_selected_file)
        files_btn_layout.addWidget(self.play_file_btn)

        self.delete_file_btn = QPushButton("Удалить")
        self.delete_file_btn.setProperty("compact", True)
        self.delete_file_btn.setToolTip("Удалить выбранный файл из списка клипов")
        self.delete_file_btn.clicked.connect(self.delete_selected_file)
        files_btn_layout.addWidget(self.delete_file_btn)

        root_layout.addLayout(files_btn_layout)
        self.setLayout(root_layout)

    def _selected_clip_file(self):
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
        has_file = self._selected_clip_file() is not None
        enabled = self.cmd_client is not None and self.ssh_client is not None
        self.add_file_btn.setEnabled(enabled)
        self.play_file_btn.setEnabled(enabled and has_file)
        self.delete_file_btn.setEnabled(enabled and has_file)

    def _resolve_clip_folder(self) -> str:
        """Resolve the daemon's configured default clips folder."""
        if not self.ssh_client:
            return ""

        config = self.ssh_client.get_remote_daemon_config()
        configured = str(config.get('clips_folder') or "").strip()
        if configured:
            if configured.startswith("~/"):
                return str(PurePosixPath(self.ssh_client.get_remote_home()) / configured[2:])
            if configured == "~":
                return self.ssh_client.get_remote_home()
            return configured

        return get_clips_root(self.ssh_client.get_remote_home())

    def _remote_path_for_filename(self, filename: str) -> str:
        safe_filename = validate_clip_filename(filename)
        if not self.clip_folder:
            self.clip_folder = self._resolve_clip_folder()
        return str(PurePosixPath(self.clip_folder) / safe_filename)

    def refresh_clips(self, do_sync: bool = False):
        """Reload clips from the daemon's default clips folder."""
        if not self.cmd_client or not self.ssh_client:
            QMessageBox.information(self, "Информация", "Нет подключения к daemon")
            return

        current_file = self._selected_clip_file()
        current_name = current_file['filename'] if current_file else None
        self.files_list.clear()

        try:
            if do_sync and hasattr(self.cmd_client, 'sync_playlists'):
                success, _, error = self.cmd_client.sync_playlists()
                if not success:
                    logger.warning("Could not sync daemon clip list: %s", error)

            self.clip_folder = self._resolve_clip_folder()
            success, files, error = self.ssh_client.list_directory(self.clip_folder)
            if not success:
                self._set_files_placeholder(f"Не удалось прочитать каталог: {error}")
                return

            visible_files = []
            for name in files:
                try:
                    safe_name = validate_clip_filename(name)
                except ValueError:
                    logger.warning("Ignoring unsafe clip filename from remote listing: %r", name)
                    continue
                if is_supported_video_file(safe_name):
                    visible_files.append(safe_name)

            visible_files = sorted(set(visible_files), key=str.lower)
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
                        'filepath': self._remote_path_for_filename(filename),
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
            logger.info("Loaded %s clips from %s", len(visible_files), self.clip_folder)
        except Exception as exc:
            logger.error("Error refreshing clips: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления:\n{exc}")

    def refresh_playlists(self, do_sync: bool = False):
        """Compatibility wrapper for callers that refresh the clips panel."""
        self.refresh_clips(do_sync=do_sync)

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

        files = [url.toLocalFile() for url in event.mimeData().urls()]
        video_files = [path for path in files if is_supported_video_file(path)]
        if not video_files:
            QMessageBox.warning(self, "Ошибка", "Не найдено видеофайлов")
            return

        self.upload_files_to_clip_list(video_files)
        event.acceptProposedAction()

    def upload_files_to_clip_list(self, files):
        """Upload files to the default clips folder."""
        if not self.ssh_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return

        uploaded = 0
        for file_path in files:
            try:
                filename = validate_clip_filename(Path(file_path).name)
                remote_path = self._remote_path_for_filename(filename)
                success, error = upload_file_with_progress(self, self.ssh_client, file_path, remote_path)

                if not success:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить {filename}:\n{error}")
                    break
                uploaded += 1
            except ValueError as exc:
                QMessageBox.warning(self, "Ошибка", f"Небезопасное имя файла:\n{exc}")
                break
            except Exception as exc:
                logger.error("Error uploading file: %s", exc)
                QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки:\n{exc}")
                break
        else:
            QMessageBox.information(self, "Успех", f"Загружено {uploaded} файлов")
            self.refresh_clips(do_sync=True)
            self.playlist_changed.emit()

    def add_files_to_clip_list(self):
        """Open a file dialog and upload files to the default clips folder."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Добавить файлы в клипы",
            "",
            VIDEO_FILE_DIALOG_FILTER,
        )
        if not files:
            return

        self.upload_files_to_clip_list(files)

    def play_selected_file(self):
        """Immediately play the selected clip file."""
        file_info = self._selected_clip_file()
        if not file_info:
            QMessageBox.information(self, "Информация", "Выберите файл клипа")
            return

        try:
            filename = validate_clip_filename(file_info['filename'])
            success, _, error = self.cmd_client.play_clip_file(filename)
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось включить файл:\n{error}")
                return

            self.refresh_clips(do_sync=True)
            self.playlist_changed.emit()
        except Exception as exc:
            logger.error("Error playing clip file: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def delete_selected_file(self):
        """Delete the selected file from the default clips folder."""
        file_info = self._selected_clip_file()
        if not file_info:
            QMessageBox.information(self, "Информация", "Выберите файл для удаления")
            return

        filename = file_info['filename']
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить файл '{filename}' из списка клипов?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            safe_filename = validate_clip_filename(filename)
            success, error = self.ssh_client.delete_file(self._remote_path_for_filename(safe_filename))
            if not success:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить файл:\n{error}")
                return

            self.refresh_clips(do_sync=True)
            self.playlist_changed.emit()
        except Exception as exc:
            logger.error("Error deleting clip file: %s", exc)
            QMessageBox.critical(self, "Ошибка", f"Ошибка:\n{exc}")

    def set_clients(self, ssh_client, cmd_client):
        """Set the SSH and command clients."""
        self.ssh_client = ssh_client
        self.clip_folder = None
        self.set_cmd_client(cmd_client)

    def set_cmd_client(self, client):
        """Set command client and update enabled state."""
        self.cmd_client = client
        enabled = client is not None
        self.files_list.setEnabled(enabled)
        self._update_file_buttons()

        if not enabled:
            self.clip_folder = None
            self._set_files_placeholder("Нет подключения")

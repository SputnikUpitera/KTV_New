"""
Main window for Operator KTV application.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressDialog,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QSize, Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QBrush, QIcon, QPainter, QPen, QPixmap, QKeySequence
import logging
from pathlib import Path

from .connection_dialog import ConnectionDialog
from .movies_tab import MoviesTab
from .clips_tab import ClipsTab
from .ssh_terminal import SSHTerminalWidget
from ..network.ssh_client import SSHClient
from ..network.commands import CommandClient
from ..installer.check_remote import RemoteChecker
from ..installer.deploy_package import PackageDeployer
from ..installer.verify_install import InstallationVerifier

logger = logging.getLogger(__name__)


class StatusFetchThread(QThread):
    """Fetch daemon playback status away from the UI thread."""

    status_ready = pyqtSignal(bool, object, str)

    def __init__(self, cmd_client):
        super().__init__()
        self.cmd_client = cmd_client

    def run(self):
        try:
            success, status, error = self.cmd_client.get_status()
            self.status_ready.emit(success, status, error)
        except Exception as exc:
            self.status_ready.emit(False, {}, str(exc))


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        self.ssh_client = SSHClient()
        self.cmd_client = None
        self.connected = False
        self.connection_info = {}
        self.status_thread = None
        self.status_request_pending = False
        
        self.setup_ui()
        self.setup_menu()

        self.movies_tab.refresh_requested.connect(self.manual_refresh_all_views)
        self.movies_tab.schedule_changed.connect(self.refresh_playback_status)
        self.clips_tab.playlist_changed.connect(self.refresh_playback_status)

        self.status_timer = QTimer(self)
        self.status_timer.setInterval(5000)
        self.status_timer.timeout.connect(self.refresh_playback_status)
        
        # Show connection dialog on startup
        QTimer.singleShot(100, self.show_connection_dialog)
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("OperatorKTV - Управление медиа")
        self.resize(1220, 690)
        self.setMinimumSize(1000, 620)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(14, 12, 14, 12)
        central_layout.setSpacing(12)

        status_frame = QFrame()
        status_frame.setObjectName("playbackStatusFrame")
        status_frame.setMaximumHeight(88)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        status_info = QWidget()
        info_layout = QVBoxLayout(status_info)
        info_layout.setContentsMargins(12, 8, 10, 8)
        info_layout.setSpacing(2)

        status_caption = QLabel("Сейчас воспроизводится")
        status_caption.setObjectName("playbackCaptionLabel")
        info_layout.addWidget(status_caption)

        self.current_playback_label = QLabel("Нет данных")
        self.current_playback_label.setObjectName("currentPlaybackLabel")
        self.current_playback_label.setWordWrap(True)
        info_layout.addWidget(self.current_playback_label)

        self.next_clip_label = QLabel("Следующий клип: —")
        self.next_clip_label.setObjectName("nextClipLabel")
        self.next_clip_label.setWordWrap(True)
        info_layout.addWidget(self.next_clip_label)

        status_layout.addWidget(status_info, 1)

        self.playback_controls_frame = QFrame()
        self.playback_controls_frame.setObjectName("playbackControlsFrame")
        controls_layout = QGridLayout(self.playback_controls_frame)
        controls_layout.setContentsMargins(8, 6, 8, 6)
        controls_layout.setHorizontalSpacing(4)
        controls_layout.setVerticalSpacing(4)
        self.shuffle_icon = self._build_dice_icon("#f0f0f0")
        self.shuffle_icon_checked = self._build_dice_icon("#000000")

        self.play_pause_btn = self._create_transport_button(
            icon=self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause),
            tooltip="Пауза/воспроизведение",
            handler=self.toggle_play_pause,
        )
        self.stop_btn = self._create_transport_button(
            icon=self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
            tooltip="Стоп",
            handler=self.stop_playback,
        )
        self.next_btn = self._create_transport_button(
            icon=self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward),
            tooltip="Следующий клип",
            handler=self.next_clip,
        )
        self.shuffle_btn = self._create_transport_button(
            icon=self.shuffle_icon,
            tooltip="Случайный порядок клипов",
            checkable=True,
            handler=self.toggle_shuffle,
        )

        controls_layout.addWidget(self.play_pause_btn, 0, 0)
        controls_layout.addWidget(self.stop_btn, 0, 1)
        controls_layout.addWidget(self.next_btn, 1, 0)
        controls_layout.addWidget(self.shuffle_btn, 1, 1)
        status_layout.addWidget(self.playback_controls_frame)

        central_layout.addWidget(status_frame)

        self.movies_tab = MoviesTab()
        self.clips_tab = ClipsTab()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.movies_tab)
        splitter.addWidget(self.clips_tab)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([640, 520])
        central_layout.addWidget(splitter, 1)

        self.setCentralWidget(central_widget)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status("Не подключено")
        self._reset_transport_controls()
    
    def setup_menu(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("Файл")
        
        connect_action = QAction("Подключиться...", self)
        connect_action.setShortcut(QKeySequence.StandardKey.Open)
        connect_action.triggered.connect(self.show_connection_dialog)
        file_menu.addAction(connect_action)
        
        disconnect_action = QAction("Отключиться", self)
        disconnect_action.setShortcut("Ctrl+D")
        disconnect_action.triggered.connect(self.disconnect)
        file_menu.addAction(disconnect_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Инструменты")
        
        terminal_action = QAction("SSH Консоль...", self)
        terminal_action.setShortcut("Ctrl+T")
        terminal_action.triggered.connect(self.show_terminal)
        tools_menu.addAction(terminal_action)
        
        check_action = QAction("Проверить систему...", self)
        check_action.triggered.connect(self.check_remote_system)
        tools_menu.addAction(check_action)
        
        install_action = QAction("Установить ПО...", self)
        install_action.triggered.connect(self.install_software)
        tools_menu.addAction(install_action)
        
        verify_action = QAction("Проверить установку...", self)
        verify_action.triggered.connect(self.verify_installation)
        tools_menu.addAction(verify_action)
        
        tools_menu.addSeparator()
        
        status_action = QAction("Статус daemon...", self)
        status_action.setShortcut("F6")
        status_action.triggered.connect(self.show_daemon_status)
        tools_menu.addAction(status_action)
        
        logs_action = QAction("Логи daemon...", self)
        logs_action.setShortcut("F7")
        logs_action.triggered.connect(self.show_daemon_logs)
        tools_menu.addAction(logs_action)
        
        # Help menu
        help_menu = menubar.addMenu("Справка")
        
        about_action = QAction("О программе...", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def show_connection_dialog(self):
        """Show connection dialog"""
        dialog = ConnectionDialog(self)
        
        # Set previous connection info if available
        if self.connection_info:
            dialog.set_connection_info(self.connection_info)
        
        if dialog.exec():
            self.connection_info = dialog.get_connection_info()
            self.connect_to_remote()
            if not self.connection_info.get('remember_password'):
                self.connection_info['password'] = ""
    
    def connect_to_remote(self, retry_count=2):
        """Connect to remote system with retry logic"""
        if not self.connection_info:
            return

        success = False
        for attempt in range(retry_count):
            if attempt > 0:
                self.update_status(f"Повторная попытка {attempt + 1}/{retry_count}...")
                # Wait a bit before retry
                from PyQt6.QtCore import QThread
                QThread.msleep(2000)
            else:
                self.update_status("Подключение...")
            
            logger.info(f"Connection attempt {attempt + 1}/{retry_count}")
            
            # Connect SSH
            success, error = self.ssh_client.connect(
                host=self.connection_info['host'],
                port=self.connection_info['port'],
                username=self.connection_info['username'],
                password=self.connection_info['password']
            )
            
            if success:
                break
            
            logger.warning(f"Connection attempt {attempt + 1} failed: {error}")
        
        if not success:
            QMessageBox.critical(self, "Ошибка подключения",
                               f"Не удалось подключиться после {retry_count} попыток:\n\n{error}")
            self.update_status("Не подключено")
            return
        
        # Create command client
        self.cmd_client = CommandClient(self.ssh_client)
        
        # Test daemon connection
        success, error = self.cmd_client.ping()
        
        if success:
            self.connected = True
            self.update_status(f"Подключено к {self.connection_info['host']}")
            
            # Update tabs with clients
            self.movies_tab.set_clients(self.ssh_client, self.cmd_client)
            self.clips_tab.set_clients(self.ssh_client, self.cmd_client)
            
            # Refresh data
            self.refresh_all_views(do_sync=True)
            self.status_timer.start()
            
            QMessageBox.information(self, "Успех", "Подключено к удалённой системе")
        else:
            # Connected but daemon not responding
            reply = QMessageBox.question(
                self, "Daemon не найден",
                "SSH подключение установлено, но daemon не отвечает.\n"
                "Хотите установить программное обеспечение?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.install_software()
            else:
                self.disconnect()
                self.update_status("Не подключено")
    
    def disconnect(self):
        """Disconnect from remote system"""
        self.status_timer.stop()
        self.status_request_pending = False
        if self.status_thread and self.status_thread.isRunning():
            self.status_thread.quit()
            self.status_thread.wait(1000)
        self.status_thread = None
        self.connected = False
        self.cmd_client = None

        self.movies_tab.set_cmd_client(None)
        self.clips_tab.set_cmd_client(None)

        if self.ssh_client:
            self.ssh_client.disconnect()

        self._reset_transport_controls()
        self.update_status("Не подключено")
    
    def update_status(self, message: str):
        """Update status bar message"""
        self.status_bar.showMessage(message)

    def _create_transport_button(self, icon=None, text: str = "", tooltip: str = "",
                                 checkable: bool = False, handler=None) -> QToolButton:
        """Create a transport button for the playback banner."""
        button = QToolButton()
        button.setObjectName("transportButton")
        button.setCheckable(checkable)
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip or text or "Кнопка управления воспроизведением")
        if icon is not None:
            button.setIcon(icon)
        if text:
            button.setText(text)
        if handler:
            button.clicked.connect(lambda _checked=False, callback=handler: callback())
        return button

    def _build_dice_icon(self, color: str) -> QIcon:
        """Create a dice icon for the random button."""
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.drawRoundedRect(2, 2, 7, 7, 1.6, 1.6)
        painter.drawRoundedRect(9, 9, 7, 7, 1.6, 1.6)

        pip_brush = QBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pip_brush)

        for x, y in ((4, 4), (6, 6), (11, 11), (11, 14), (14, 11), (14, 14)):
            painter.drawEllipse(x, y, 2, 2)
        painter.end()

        return QIcon(pixmap)

    def _reset_transport_controls(self, reset_text: bool = True):
        """Disable transport controls and reset their state."""
        if reset_text:
            self.current_playback_label.setText("Нет данных")
            self.next_clip_label.setText("Следующий клип: —")
            self.next_clip_label.setVisible(True)
        self.play_pause_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.shuffle_btn.setIcon(self.shuffle_icon)
        for button in (self.play_pause_btn, self.stop_btn, self.next_btn, self.shuffle_btn):
            button.setEnabled(False)
        self.shuffle_btn.setChecked(False)

    def _apply_playback_status(self, status: dict):
        """Render daemon playback status into the compact banner."""
        current = status.get('current_playback', {})
        source = current.get('source')
        filename = current.get('filename')
        player_status = status.get('player', {})
        playlist_status = status.get('playlist', {})
        transport_available = bool(playlist_status.get('transport_available'))
        has_playlist_files = bool(playlist_status.get('has_files'))
        has_active_clip = bool(playlist_status.get('has_active_clip'))
        paused = bool(player_status.get('is_paused')) or bool(playlist_status.get('paused'))
        shuffle_enabled = bool(playlist_status.get('shuffle_enabled'))

        if source == 'movie' and filename:
            self.current_playback_label.setText(f"Фильм: {filename}")
        elif source == 'clip' and filename:
            playlist_name = playlist_status.get('active') or "плейлист"
            prefix = "Клип на паузе" if paused else "Клип"
            self.current_playback_label.setText(f"{prefix}: {filename}  [{playlist_name}]")
        elif player_status.get('is_playing') and player_status.get('filename'):
            fallback_filename = player_status['filename']
            if playlist_status.get('playing') or paused:
                playlist_name = playlist_status.get('active') or "плейлист"
                prefix = "Клип на паузе" if paused else "Клип"
                self.current_playback_label.setText(f"{prefix}: {fallback_filename}  [{playlist_name}]")
            else:
                self.current_playback_label.setText(f"Воспроизводится: {fallback_filename}")
        else:
            self.current_playback_label.setText("Сейчас ничего не воспроизводится")

        next_clip = status.get('next_clip', {}).get('filename') or playlist_status.get('next_filename')
        self.next_clip_label.setVisible(not shuffle_enabled)
        if shuffle_enabled:
            self.next_clip_label.clear()
        elif next_clip:
            self.next_clip_label.setText(f"Следующий клип: {next_clip}")
        else:
            self.next_clip_label.setText("Следующий клип: —")

        self.shuffle_btn.setChecked(shuffle_enabled)
        self.shuffle_btn.setIcon(self.shuffle_icon_checked if shuffle_enabled else self.shuffle_icon)
        self.shuffle_btn.setEnabled(transport_available and has_playlist_files)
        self.next_btn.setEnabled(transport_available and has_playlist_files)
        self.stop_btn.setEnabled(transport_available and (has_active_clip or paused or source == 'clip'))
        can_use_play_pause = transport_available and has_playlist_files
        self.play_pause_btn.setEnabled(can_use_play_pause)
        play_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaPlay if paused or source != 'clip' else QStyle.StandardPixmap.SP_MediaPause
        )
        self.play_pause_btn.setIcon(play_icon)

    def _status_fetch_finished(self, success: bool, status: dict, error: str):
        """Handle completion of a background status fetch."""
        self.status_request_pending = False
        if self.status_thread:
            self.status_thread.deleteLater()
            self.status_thread = None

        if not self.cmd_client:
            return

        if not success:
            logger.warning("Could not refresh playback status: %s", error)
            self.current_playback_label.setText("Статус недоступен")
            self.next_clip_label.setText("Следующий клип: —")
            self.next_clip_label.setVisible(True)
            self._reset_transport_controls(reset_text=False)
            return

        self._apply_playback_status(status)

    def refresh_all_views(self, do_sync: bool = False):
        """Refresh movies, playlists and playback status together."""
        if self.movies_tab.cmd_client:
            self.movies_tab.refresh_schedules(do_sync=do_sync)
        if self.clips_tab.cmd_client:
            self.clips_tab.refresh_playlists(do_sync=do_sync)
        self.refresh_playback_status()

    def manual_refresh_all_views(self):
        """Refresh all views and run daemon-side synchronization."""
        self.refresh_all_views(do_sync=True)

    def _execute_transport_command(self, command_name: str, error_title: str):
        """Call a daemon transport command and refresh the banner."""
        if not self.cmd_client:
            return

        command = getattr(self.cmd_client, command_name)
        success, status, error = command()
        if not success:
            QMessageBox.warning(self, error_title, error)
            self.refresh_playback_status()
            return
        if status:
            self._apply_playback_status(status)
        else:
            self.refresh_playback_status()

    def toggle_play_pause(self):
        """Toggle play or pause for the active clip playlist."""
        self._execute_transport_command('toggle_play_pause', "Не удалось изменить состояние воспроизведения")

    def stop_playback(self):
        """Stop clip playback."""
        self._execute_transport_command('stop_playback', "Не удалось остановить воспроизведение")

    def next_clip(self):
        """Start the next clip."""
        self._execute_transport_command('next_clip', "Не удалось переключить на следующий клип")

    def toggle_shuffle(self):
        """Toggle random clip order."""
        self._execute_transport_command('toggle_shuffle', "Не удалось изменить случайный режим")

    def refresh_playback_status(self):
        """Refresh the compact playback banner in the main window."""
        if not self.cmd_client:
            self._reset_transport_controls()
            return
        if self.status_request_pending:
            return

        self.status_request_pending = True
        self.status_thread = StatusFetchThread(self.cmd_client)
        self.status_thread.status_ready.connect(self._status_fetch_finished)
        self.status_thread.start()
    
    def show_terminal(self):
        """Show SSH terminal window"""
        if not self.ssh_client.is_connected():
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return
        
        # Create terminal dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("SSH Терминал")
        dialog.resize(800, 600)
        
        layout = QVBoxLayout()
        
        terminal = SSHTerminalWidget(self.ssh_client)
        layout.addWidget(terminal)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    def check_remote_system(self):
        """Check remote system compatibility"""
        if not self.ssh_client.is_connected():
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return
        
        checker = RemoteChecker(self.ssh_client)
        success, results, error = checker.check_system()
        
        summary = checker.get_system_info_summary(results)
        
        # Show results
        msg = QMessageBox(self)
        msg.setWindowTitle("Информация о системе")
        msg.setText("Проверка удалённой системы завершена")
        msg.setDetailedText(summary)
        msg.setIcon(QMessageBox.Icon.Information if not results.get('has_errors') 
                   else QMessageBox.Icon.Warning)
        msg.exec()
    
    def install_software(self):
        """Install software on remote system"""
        if not self.ssh_client.is_connected():
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return
        
        # Check for package
        package_path = Path(__file__).parent.parent.parent / "offline_package" / "ktv_offline_package.tar.gz"
        
        if not package_path.exists():
            QMessageBox.critical(
                self, "Ошибка",
                f"Установочный пакет не найден:\n{package_path}\n\n"
                "Запустите build_offline_package.py для создания пакета."
            )
            return
        
        # Confirm installation
        reply = QMessageBox.question(
            self, "Подтверждение установки",
            "Установить KTV daemon на удалённую систему?\n"
            "Это может занять несколько минут.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Deploy package
        deployer = PackageDeployer(self.ssh_client)
        deployer.set_package_path(str(package_path))
        
        # Progress dialog
        progress = QProgressDialog("Установка...", "Отмена", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        
        def progress_callback(message, percent):
            progress.setLabelText(message)
            progress.setValue(percent)
        
        success, error = deployer.deploy(progress_callback=progress_callback)
        
        progress.close()
        
        if success:
            QMessageBox.information(self, "Успех", "Установка завершена успешно!")
            
            # Try to connect to daemon now
            self.connect_to_remote()
        else:
            QMessageBox.critical(self, "Ошибка установки", f"Установка не удалась:\n{error}")
    
    def verify_installation(self):
        """Verify daemon installation"""
        if not self.ssh_client.is_connected():
            QMessageBox.warning(self, "Ошибка", "Не подключено к удалённой системе")
            return
        
        verifier = InstallationVerifier(self.ssh_client)
        success, results, error = verifier.verify()
        
        summary = verifier.get_verification_summary(results)
        
        # Show results
        msg = QMessageBox(self)
        msg.setWindowTitle("Проверка установки")
        msg.setText("Проверка завершена")
        msg.setDetailedText(summary)
        msg.setIcon(QMessageBox.Icon.Information if success else QMessageBox.Icon.Warning)
        msg.exec()
    
    def show_daemon_status(self):
        """Show daemon status"""
        if not self.cmd_client:
            QMessageBox.warning(self, "Ошибка", "Не подключено к daemon")
            return
        
        success, status, error = self.cmd_client.get_status()
        
        if success:
            current_playback = status.get('current_playback', {})
            playlist_status = status.get('playlist', {})
            player_status = status.get('player', {})
            paused = bool(player_status.get('is_paused')) or bool(playlist_status.get('paused'))

            player_summary = "Остановлен"
            if current_playback.get('source') == 'movie':
                player_summary = "Воспроизводится фильм"
            elif current_playback.get('source') == 'clip':
                player_summary = "Клип на паузе" if paused else "Воспроизводится клип"
            elif player_status.get('is_playing'):
                player_summary = "Воспроизводится"

            # Format status info
            info_lines = [
                f"Daemon запущен: Да",
                f"Плеер: {player_summary}",
            ]
            
            if player_status.get('current_file'):
                info_lines.append(f"Текущий файл: {status['player']['filename']}")

            if current_playback.get('source'):
                info_lines.append(
                    f"Источник: {'Фильм' if current_playback['source'] == 'movie' else 'Клип'}"
                )

            next_clip = status.get('next_clip', {}).get('filename')
            if next_clip:
                info_lines.append(f"Следующий клип: {next_clip}")
            
            if 'broadcast_hours' in status:
                info_lines.append(f"Часы вещания: {status['broadcast_hours']['start']} - {status['broadcast_hours']['end']}")
            
            if 'broadcasting_active' in status:
                info_lines.append(f"Вещание активно: {'Да' if status['broadcasting_active'] else 'Нет'}")
            
            info_text = '\n'.join(info_lines)
            QMessageBox.information(self, "Статус Daemon", info_text)
        else:
            QMessageBox.critical(self, "Ошибка", f"Не удалось получить статус:\n{error}")
    
    def show_daemon_logs(self):
        """Show daemon logs"""
        if not self.ssh_client or not self.ssh_client.is_connected():
            QMessageBox.warning(self, "Ошибка", "SSH не подключён")
            return
        
        # Show progress dialog
        from PyQt6.QtWidgets import QProgressDialog
        progress = QProgressDialog("Получение логов...", "Отмена", 0, 0, self)
        progress.setWindowTitle("Загрузка логов")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        
        from PyQt6.QtCore import QThread, pyqtSignal
        
        class LogFetcher(QThread):
            finished = pyqtSignal(str)
            
            def __init__(self, ssh_client):
                super().__init__()
                self.ssh_client = ssh_client
            
            def run(self):
                try:
                    logs = []
                    
                    # Check systemd status (no sudo needed for status)
                    exit_code, stdout, stderr = self.ssh_client.execute_command(
                        "systemctl status ktv-daemon --no-pager"
                    )
                    systemd_status = stdout if stdout else f"Error: {stderr}"
                    logs.append(f"=== Systemd Status ===\n{systemd_status}\n")
                    
                    # Try to get daemon application logs (may need sudo)
                    exit_code, stdout, stderr = self.ssh_client.execute_command(
                        "cat /var/log/ktv/daemon.log 2>/dev/null | tail -100 || echo 'Log file not accessible'"
                    )
                    daemon_log = stdout if stdout else "No logs"
                    logs.append(f"=== Daemon Log (last 100 lines) ===\n{daemon_log}\n")
                    
                    # Get systemd journal (no sudo needed with --user-unit or for reading)
                    exit_code, stdout, stderr = self.ssh_client.execute_command(
                        "journalctl -u ktv-daemon -n 50 --no-pager 2>/dev/null || echo 'Journal not accessible'"
                    )
                    journal = stdout if stdout else "No journal"
                    logs.append(f"=== Systemd Journal (last 50 lines) ===\n{journal}")
                    
                    # Check if daemon files exist
                    exit_code, stdout, stderr = self.ssh_client.execute_command(
                        "ls -la /opt/ktv/ 2>&1"
                    )
                    file_list = stdout if stdout else stderr
                    logs.append(f"\n=== Daemon Files ===\n{file_list}")
                    
                    log_text = '\n'.join(logs)
                    self.finished.emit(log_text)
                    
                except Exception as e:
                    self.finished.emit(f"Error fetching logs: {str(e)}")
        
        def on_logs_fetched(log_text):
            progress.close()
            
            # Show in message box with scroll
            msg = QMessageBox(self)
            msg.setWindowTitle("Логи Daemon")
            msg.setText("Логи KTV Daemon:")
            msg.setDetailedText(log_text)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.exec()
        
        # Create and start worker thread
        self.log_fetcher = LogFetcher(self.ssh_client)
        self.log_fetcher.finished.connect(on_logs_fetched)
        self.log_fetcher.start()
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self, "О программе",
            "<h3>OperatorKTV v1.0</h3>"
            "<p>Система управления медиафайлами для удалённого воспроизведения.</p>"
            "<p>Windows GUI клиент для управления Linux медиа-сервером.</p>"
            "<p><br/>Разработано в 2026</p>"
        )
    
    def closeEvent(self, event):
        """Handle window close event"""
        if self.connected or self.cmd_client or self.ssh_client.is_connected():
            self.disconnect()
        event.accept()

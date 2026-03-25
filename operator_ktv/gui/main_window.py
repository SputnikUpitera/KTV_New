"""
Main window for Operator KTV application.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressDialog,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
import logging
import sys
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


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        self.ssh_client = SSHClient()
        self.cmd_client = None
        self.connected = False
        self.connection_info = {}
        
        self.setup_ui()
        self.setup_menu()

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
        self.resize(1100, 720)
        self.setMinimumSize(900, 620)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(12, 12, 12, 12)
        central_layout.setSpacing(12)

        status_frame = QFrame()
        status_frame.setObjectName("playbackStatusFrame")
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(6)

        status_caption = QLabel("Сейчас воспроизводится")
        status_caption.setStyleSheet("color: #9a9a9a; font-size: 11px; letter-spacing: 0.4px;")
        status_layout.addWidget(status_caption)

        self.current_playback_label = QLabel("Нет данных")
        self.current_playback_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.current_playback_label.setWordWrap(True)
        status_layout.addWidget(self.current_playback_label)

        self.next_clip_label = QLabel("Следующий клип: —")
        self.next_clip_label.setStyleSheet("color: #8a8a8a; font-size: 13px;")
        self.next_clip_label.setWordWrap(True)
        status_layout.addWidget(self.next_clip_label)

        central_layout.addWidget(status_frame)

        self.movies_tab = MoviesTab()
        self.clips_tab = ClipsTab()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.movies_tab)
        splitter.addWidget(self.clips_tab)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([620, 480])
        central_layout.addWidget(splitter, 1)

        self.setCentralWidget(central_widget)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status("Не подключено")
    
    def setup_menu(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("Файл")
        
        connect_action = QAction("Подключиться...", self)
        connect_action.triggered.connect(self.show_connection_dialog)
        file_menu.addAction(connect_action)
        
        disconnect_action = QAction("Отключиться", self)
        disconnect_action.triggered.connect(self.disconnect)
        file_menu.addAction(disconnect_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Инструменты")
        
        terminal_action = QAction("SSH Консоль...", self)
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
        status_action.triggered.connect(self.show_daemon_status)
        tools_menu.addAction(status_action)
        
        logs_action = QAction("Логи daemon...", self)
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
            self.movies_tab.refresh_schedules()
            self.clips_tab.refresh_playlists()
            self.refresh_playback_status()
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
        self.connected = False
        self.cmd_client = None

        self.movies_tab.set_cmd_client(None)
        self.clips_tab.set_cmd_client(None)

        if self.ssh_client:
            self.ssh_client.disconnect()

        self.current_playback_label.setText("Нет данных")
        self.next_clip_label.setText("Следующий клип: —")
        self.update_status("Не подключено")
    
    def update_status(self, message: str):
        """Update status bar message"""
        self.status_bar.showMessage(message)

    def refresh_playback_status(self):
        """Refresh the compact playback banner in the main window."""
        if not self.cmd_client:
            self.current_playback_label.setText("Нет данных")
            self.next_clip_label.setText("Следующий клип: —")
            return

        success, status, error = self.cmd_client.get_status()
        if not success:
            logger.warning("Could not refresh playback status: %s", error)
            self.current_playback_label.setText("Статус недоступен")
            self.next_clip_label.setText("Следующий клип: —")
            return

        current = status.get('current_playback', {})
        source = current.get('source')
        filename = current.get('filename')
        player_status = status.get('player', {})
        playlist_status = status.get('playlist', {})

        if source == 'movie' and filename:
            self.current_playback_label.setText(f"Фильм: {filename}")
        elif source == 'clip' and filename:
            playlist_name = playlist_status.get('active') or "плейлист"
            self.current_playback_label.setText(f"Клип: {filename}  [{playlist_name}]")
        elif player_status.get('is_playing') and player_status.get('filename'):
            fallback_filename = player_status['filename']
            if playlist_status.get('playing'):
                playlist_name = playlist_status.get('active') or "плейлист"
                self.current_playback_label.setText(f"Клип: {fallback_filename}  [{playlist_name}]")
            else:
                self.current_playback_label.setText(f"Воспроизводится: {fallback_filename}")
        else:
            self.current_playback_label.setText("Сейчас ничего не воспроизводится")

        next_clip = status.get('next_clip', {}).get('filename') or playlist_status.get('next_filename')
        if next_clip:
            self.next_clip_label.setText(f"Следующий клип: {next_clip}")
        else:
            self.next_clip_label.setText("Следующий клип: —")
    
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
            # Format status info
            info_lines = [
                f"Daemon запущен: Да",
                f"Плеер: {'Воспроизводится' if status.get('player', {}).get('is_playing') else 'Остановлен'}",
            ]
            
            if status.get('player', {}).get('current_file'):
                info_lines.append(f"Текущий файл: {status['player']['filename']}")

            current_playback = status.get('current_playback', {})
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

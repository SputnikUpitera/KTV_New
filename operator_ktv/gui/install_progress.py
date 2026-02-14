"""
Installation progress dialog
Shows detailed progress during daemon installation
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QProgressBar,
                             QTextEdit, QPushButton, QLabel)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont
import logging

logger = logging.getLogger(__name__)


class InstallProgressDialog(QDialog):
    """Dialog showing installation progress with detailed log"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("Установка KTV Daemon")
        self.setModal(True)
        self.resize(600, 400)
        
        layout = QVBoxLayout()
        
        # Status label
        self.status_label = QLabel("Подготовка к установке...")
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Detailed log area
        log_label = QLabel("Детальный лог:")
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont('Courier New', 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
        """)
        layout.addWidget(self.log_text)
        
        # Close button (initially disabled)
        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setEnabled(False)
        layout.addWidget(self.close_button)
        
        self.setLayout(layout)
    
    def update_progress(self, message: str, percent: int):
        """Update progress bar and status"""
        self.status_label.setText(message)
        self.progress_bar.setValue(percent)
        self.append_log(f"[{percent}%] {message}")
    
    def append_log(self, message: str):
        """Append message to log area"""
        self.log_text.append(message)
        
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def set_complete(self, success: bool):
        """Mark installation as complete"""
        if success:
            self.status_label.setText("✓ Установка завершена успешно!")
            self.progress_bar.setValue(100)
            self.append_log("\n✓ Установка завершена успешно!")
        else:
            self.status_label.setText("✗ Установка не удалась")
            self.append_log("\n✗ Установка не удалась")
        
        self.close_button.setEnabled(True)
    
    def set_error(self, error_message: str):
        """Show error message"""
        self.status_label.setText("✗ Ошибка установки")
        self.append_log(f"\n✗ ОШИБКА: {error_message}")
        self.close_button.setEnabled(True)


class InstallWorker(QThread):
    """Worker thread for installation to avoid blocking GUI"""
    
    progress_updated = pyqtSignal(str, int)
    installation_complete = pyqtSignal(bool, str)
    
    def __init__(self, deployer):
        super().__init__()
        self.deployer = deployer
    
    def run(self):
        """Run installation in background thread"""
        try:
            def progress_callback(message, percent):
                self.progress_updated.emit(message, percent)
            
            success, error = self.deployer.deploy(progress_callback=progress_callback)
            
            self.installation_complete.emit(success, error)
            
        except Exception as e:
            logger.error(f"Installation worker error: {e}", exc_info=True)
            self.installation_complete.emit(False, str(e))

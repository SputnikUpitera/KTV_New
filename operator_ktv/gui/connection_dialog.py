"""
Connection dialog for SSH connection setup and installation
"""

from PyQt6.QtWidgets import (QCheckBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSpinBox, QMessageBox,
                             QProgressDialog, QTextEdit)
from PyQt6.QtCore import Qt, QThread, QSettings, pyqtSignal
import logging

logger = logging.getLogger(__name__)


class ConnectionDialog(QDialog):
    """Dialog for configuring and testing SSH connection"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings()
        
        self.host = ""
        self.port = 22
        self.username = ""
        self.password = ""
        self.connection_accepted = False
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("Подключение к удалённой системе")
        self.setModal(True)
        self.setFixedSize(450, 290)
        
        layout = QVBoxLayout()
        
        # IP address
        ip_layout = QHBoxLayout()
        ip_label = QLabel("IP адрес:")
        ip_label.setFixedWidth(100)
        ip_layout.addWidget(ip_label)
        
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("192.168.1.100")
        ip_layout.addWidget(self.ip_edit)
        
        layout.addLayout(ip_layout)
        
        # Port
        port_layout = QHBoxLayout()
        port_label = QLabel("Порт:")
        port_label.setFixedWidth(100)
        port_layout.addWidget(port_label)
        
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        port_layout.addWidget(self.port_spin)
        port_layout.addStretch()
        
        layout.addLayout(port_layout)
        
        # Username
        user_layout = QHBoxLayout()
        user_label = QLabel("Пользователь:")
        user_label.setFixedWidth(100)
        user_layout.addWidget(user_label)
        
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("user")
        user_layout.addWidget(self.user_edit)
        
        layout.addLayout(user_layout)
        
        # Password
        pass_layout = QHBoxLayout()
        pass_label = QLabel("Пароль:")
        pass_label.setFixedWidth(100)
        pass_layout.addWidget(pass_label)
        
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pass_layout.addWidget(self.pass_edit)
        
        layout.addLayout(pass_layout)

        self.remember_password_check = QCheckBox("Запомнить пароль")
        layout.addWidget(self.remember_password_check)
        
        layout.addSpacing(20)
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        connect_btn = QPushButton("Подключиться")
        connect_btn.clicked.connect(self.accept)
        connect_btn.setDefault(True)
        button_layout.addWidget(connect_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.load_settings()
    
    def get_connection_info(self) -> dict:
        """
        Get connection information
        
        Returns:
            Dictionary with connection parameters
        """
        return {
            'host': self.ip_edit.text().strip(),
            'port': self.port_spin.value(),
            'username': self.user_edit.text().strip(),
            'password': self.pass_edit.text(),
            'remember_password': self.remember_password_check.isChecked(),
        }
    
    def set_connection_info(self, info: dict):
        """Set connection information from dictionary"""
        if 'host' in info:
            self.ip_edit.setText(info['host'])
        if 'port' in info:
            self.port_spin.setValue(info['port'])
        if 'username' in info:
            self.user_edit.setText(info['username'])
        if 'password' in info:
            self.pass_edit.setText(info['password'])
        if 'remember_password' in info:
            self.remember_password_check.setChecked(bool(info['remember_password']))

    def load_settings(self):
        """Load saved connection parameters."""
        self.ip_edit.setText(self.settings.value("connection/host", "", str))
        self.port_spin.setValue(self.settings.value("connection/port", 22, int))
        self.user_edit.setText(self.settings.value("connection/username", "", str))
        remember_password = self.settings.value("connection/remember_password", False, bool)
        self.remember_password_check.setChecked(remember_password)
        if remember_password:
            self.pass_edit.setText(self.settings.value("connection/password", "", str))
        else:
            self.pass_edit.clear()

    def save_settings(self):
        """Persist connection parameters between launches."""
        info = self.get_connection_info()
        self.settings.setValue("connection/host", info['host'])
        self.settings.setValue("connection/port", info['port'])
        self.settings.setValue("connection/username", info['username'])
        self.settings.setValue("connection/remember_password", info['remember_password'])

        if info['remember_password']:
            self.settings.setValue("connection/password", info['password'])
        else:
            self.settings.remove("connection/password")

    def accept(self):
        """Save connection parameters before closing."""
        self.save_settings()
        super().accept()
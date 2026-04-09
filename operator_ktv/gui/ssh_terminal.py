"""
SSH Terminal widget for embedded terminal access
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QLineEdit,
                             QLabel, QPushButton, QHBoxLayout)
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import re
import logging

logger = logging.getLogger(__name__)


class SSHTerminalWidget(QWidget):
    """Terminal widget for SSH sessions"""
    
    def __init__(self, ssh_client=None, parent=None):
        super().__init__(parent)
        
        self.ssh_client = ssh_client
        self.command_history = []
        self.history_index = -1
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout()
        
        # Terminal output area
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFont(QFont('Courier New', 9))
        self.output_area.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
        """)
        layout.addWidget(self.output_area)
        
        # Command input area
        input_layout = QHBoxLayout()
        
        self.prompt_label = QLabel("$ ")
        self.prompt_label.setFont(QFont('Courier New', 9))
        input_layout.addWidget(self.prompt_label)
        
        self.input_line = QLineEdit()
        self.input_line.setFont(QFont('Courier New', 9))
        self.input_line.returnPressed.connect(self.execute_command)
        self.input_line.installEventFilter(self)
        self.input_line.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                padding: 2px;
            }
        """)
        input_layout.addWidget(self.input_line)
        
        exec_btn = QPushButton("Выполнить")
        exec_btn.clicked.connect(self.execute_command)
        input_layout.addWidget(exec_btn)
        
        layout.addLayout(input_layout)
        
        self.setLayout(layout)
        
        # Show welcome message
        self.append_output("=== SSH Терминал ===\n")
        self.append_output("Введите команду и нажмите Enter\n\n")
    
    def set_ssh_client(self, ssh_client):
        """Set the SSH client for command execution"""
        self.ssh_client = ssh_client
        if ssh_client and ssh_client.is_connected():
            self.append_output(f"Подключено к {ssh_client.host}\n\n")
            self.input_line.setEnabled(True)
        else:
            self.append_output("Не подключено к удалённой системе\n\n")
            self.input_line.setEnabled(False)
    
    def append_output(self, text: str):
        """Append text to output area"""
        self.output_area.moveCursor(QTextCursor.MoveOperation.End)
        self.output_area.insertPlainText(text)
        self.output_area.moveCursor(QTextCursor.MoveOperation.End)
    
    def execute_command(self):
        """Execute the command in the input line"""
        command = self.input_line.text().strip()
        
        if not command:
            return
        
        # Add to history
        if not self.command_history or self.command_history[-1] != command:
            self.command_history.append(command)
        self.history_index = len(self.command_history)
        
        # Clear input
        self.input_line.clear()
        
        # Show command in output
        self.append_output(f"$ {command}\n")
        
        # Check if connected
        if not self.ssh_client or not self.ssh_client.is_connected():
            self.append_output("Ошибка: Не подключено к удалённой системе\n\n")
            return
        
        # Execute command
        try:
            exit_code, stdout, stderr = self.ssh_client.execute_command(command)
            
            if stdout:
                self.append_output(stdout)
            
            if stderr:
                self.append_output(f"[STDERR]\n{stderr}\n")
            
            if exit_code != 0:
                self.append_output(f"\n[Exit code: {exit_code}]\n")
            
            self.append_output("\n")
            
        except Exception as e:
            self.append_output(f"Ошибка выполнения: {str(e)}\n\n")
    
    def _handle_history_navigation(self, event) -> bool:
        """Navigate command history from the active input control."""
        if event.key() == Qt.Key.Key_Up:
            if self.command_history and self.history_index > 0:
                self.history_index -= 1
                self.input_line.setText(self.command_history[self.history_index])
            return True
        if event.key() == Qt.Key.Key_Down:
            if self.command_history and self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.input_line.setText(self.command_history[self.history_index])
            elif self.history_index >= len(self.command_history) - 1:
                self.history_index = len(self.command_history)
                self.input_line.clear()
            return True
        return False

    def eventFilter(self, obj, event):
        """Handle history shortcuts inside the input field."""
        if obj is self.input_line and event.type() == event.Type.KeyPress:
            if self._handle_history_navigation(event):
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """Handle key press events for history navigation."""
        if not self._handle_history_navigation(event):
            super().keyPressEvent(event)
    
    def clear(self):
        """Clear the terminal output"""
        self.output_area.clear()
        self.append_output("=== SSH Терминал ===\n\n")

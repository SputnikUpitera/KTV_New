"""
Shared upload helpers for modal GUI workflows.
"""

from pathlib import Path
from typing import Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QProgressDialog


def upload_file_with_progress(parent, ssh_client, local_path: str, remote_path: str) -> Tuple[bool, str]:
    """Upload a file via SFTP while showing a modal progress dialog."""
    filename = Path(local_path).name
    progress = QProgressDialog(f"Загрузка {filename}...", "Отмена", 0, 100, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.show()

    def upload_callback(transferred, total):
        percent = int((transferred / total) * 100) if total else 0
        progress.setValue(percent)

    try:
        success, error = ssh_client.upload_file(local_path, remote_path, callback=upload_callback)
    finally:
        progress.close()

    return success, error

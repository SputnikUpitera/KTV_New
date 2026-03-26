"""
OperatorKTV - Main entry point
Windows GUI application for remote media management
"""

import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QPalette, QColor
from PyQt6.QtCore import Qt

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from operator_ktv.gui.main_window import MainWindow


def setup_logging(debug=False):
    """Configure logging"""
    log_dir = Path.home() / '.operatorktv'
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'operator_ktv.log'
    
    # Set log level based on debug flag
    log_level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Enable paramiko logging for SSH debugging
    if debug:
        paramiko_logger = logging.getLogger('paramiko')
        paramiko_logger.setLevel(logging.DEBUG)
        logging.getLogger('paramiko.transport').setLevel(logging.DEBUG)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized (level: {'DEBUG' if debug else 'INFO'})")
    logger.info(f"Log file: {log_file}")


def setup_dark_theme(app):
    """Setup dark theme for the application"""
    app.setStyle('Fusion')
    app.setFont(QFont("Helvetica", 10, QFont.Weight.Normal))
    
    dark_palette = QPalette()
    
    # Define colors
    dark_color = QColor(45, 45, 45)
    disabled_color = QColor(127, 127, 127)
    
    dark_palette.setColor(QPalette.ColorRole.Window, dark_color)
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, dark_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_color)
    dark_palette.setColor(QPalette.ColorRole.Button, dark_color)
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_color)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, disabled_color)
    
    app.setPalette(dark_palette)
    
    # Additional stylesheet for better look
    app.setStyleSheet("""
        QToolTip {
            color: #ffffff;
            background-color: #2a82da;
            border: 1px solid white;
        }
        QFrame#playbackStatusFrame {
            background-color: #25282d;
            border: 1px solid #373c44;
            border-radius: 0px;
        }
        QFrame#playbackControlsFrame {
            border-left: 1px solid #3b4048;
            background-color: #20242a;
        }
        QSplitter::handle {
            background-color: #2f2f2f;
            width: 30px;
        }
        QTreeWidget, QListWidget {
            border: 1px solid #3a3a3a;
            border-radius: 8px;
            padding: 4px;
        }
        QTreeWidget::item:hover {
            background-color: #404040;
        }
        QTreeWidget::item:selected {
            background-color: #2a82da;
        }
        QListWidget::item:hover {
            background-color: #404040;
        }
        QListWidget::item:selected {
            background-color: #2a82da;
            color: #000000;
        }
        QPushButton {
            min-height: 30px;
            padding: 4px 10px;
            border: 1px solid #4a4a4a;
            border-radius: 8px;
            background-color: #363636;
        }
        QPushButton[compact="true"] {
            min-height: 24px;
            padding: 2px 10px;
            border-radius: 6px;
        }
        QPushButton:hover {
            background-color: #434343;
        }
        QPushButton:pressed {
            background-color: #2d2d2d;
        }
        QToolButton#transportButton, QToolButton#monthAddButton {
            min-width: 28px;
            min-height: 28px;
            padding: 2px;
            border: 1px solid #4a4a4a;
            border-radius: 6px;
            background-color: #2d3138;
            color: #f0f0f0;
            font-weight: 400;
        }
        QToolButton#transportButton:hover, QToolButton#monthAddButton:hover {
            background-color: #3a4048;
        }
        QToolButton#transportButton:checked {
            background-color: #2a82da;
            color: #000000;
        }
        QToolButton#monthAddButton {
            min-width: 14px;
            min-height: 14px;
            padding: 0px;
            border: 0px;
            border-radius: 0px;
            background-color: transparent;
            color: #d8d8d8;
            font-size: 12px;
            font-weight: 400;
        }
        QToolButton#monthAddButton:hover {
            background-color: transparent;
            color: #ffffff;
        }
        QLabel#sectionHeaderLabel {
            font-size: 12px;
            font-weight: 400;
            padding: 0 0 2px 0;
        }
        QLabel#playlistSectionLabel {
            font-size: 18px;
            font-weight: 400;
            padding: 0 0 2px 2px;
        }
        QLabel#monthHeaderLabel {
            font-size: 11px;
            font-weight: 400;
        }
        QLabel#playbackCaptionLabel {
            color: #9a9a9a;
            font-size: 9px;
            letter-spacing: 0.4px;
        }
        QLabel#currentPlaybackLabel {
            font-size: 15px;
            font-weight: 700;
        }
        QLabel#nextClipLabel {
            color: #8a8a8a;
            font-size: 10px;
        }
        QPushButton:focus, QListWidget:focus, QTreeWidget:focus {
            border: 1px solid #63a4ff;
        }
    """)


def main():
    """Main application entry point"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='OperatorKTV - Remote Media Management')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(debug=args.debug)
    logger = logging.getLogger(__name__)
    logger.info("Starting OperatorKTV...")
    
    if args.debug:
        logger.info("Debug mode enabled")
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("OperatorKTV")
    app.setOrganizationName("OperatorKTV")
    
    # Setup dark theme
    setup_dark_theme(app)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    logger.info("Application started")
    
    # Run application
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

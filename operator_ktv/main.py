"""
OperatorKTV - Main entry point
Windows GUI application for remote media management
"""

import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
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
        QTreeWidget::item:hover {
            background-color: #404040;
        }
        QTreeWidget::item:selected {
            background-color: #2a82da;
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

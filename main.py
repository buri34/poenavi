import sys
import os

# srcディレクトリへのパスを通す (VSCodeなどで実行した際のパスずれ対策)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

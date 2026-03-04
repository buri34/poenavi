"""
マップ画像サムネイル一覧 + クリック拡大表示
maps/<ゾーン名>/ フォルダ内の画像を自動読み込み
"""

import os
import sys
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QDialog
)
from PySide6.QtCore import Qt, QSize, Signal, QPoint, QTimer
from PySide6.QtGui import QPixmap, QCursor, QPainter


# サポートする画像拡張子
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

# サムネイルサイズ
THUMB_WIDTH = 100
THUMB_HEIGHT = 75


def get_maps_dir():
    """mapsフォルダのパス（exeフォルダ優先 → _MEIPASS）"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.isdir(os.path.join(exe_dir, "maps")):
            return os.path.join(exe_dir, "maps")
        return os.path.join(getattr(sys, '_MEIPASS', exe_dir), "maps")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "maps"
    )


def load_zone_maps(zone_name: str, part2: bool = False, route: str = "") -> list[str]:
    """
    ゾーン名に対応するマップ画像パスのリストを返す
    検索優先順位:
      1. ゾーン名~ルート#2 (Part2 + ルート指定)
      2. ゾーン名~ルート    (ルート指定)
      3. ゾーン名#2         (Part2)
      4. ゾーン名            (デフォルト)
    """
    maps_dir = get_maps_dir()
    
    if route and part2:
        rd = os.path.join(maps_dir, f"{zone_name}~{route}#2")
        if os.path.isdir(rd):
            return _list_images(rd)
    
    if route:
        rd = os.path.join(maps_dir, f"{zone_name}~{route}")
        if os.path.isdir(rd):
            return _list_images(rd)
    
    if part2:
        p2_dir = os.path.join(maps_dir, f"{zone_name}#2")
        if os.path.isdir(p2_dir):
            return _list_images(p2_dir)
    
    zone_dir = os.path.join(maps_dir, zone_name)
    if os.path.isdir(zone_dir):
        return _list_images(zone_dir)
    
    return []


def _list_images(directory: str) -> list[str]:
    """ディレクトリ内の画像ファイルをソートして返す"""
    files = []
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(IMAGE_EXTENSIONS):
            files.append(os.path.join(directory, f))
    return files


class ClickableThumb(QLabel):
    """クリック可能なサムネイルラベル"""
    clicked = Signal(str)  # ファイルパスを送出
    
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedSize(THUMB_WIDTH, THUMB_HEIGHT)
        self.setStyleSheet("""
            QLabel {
                border: 1px solid rgba(176, 255, 123, 0.3);
                border-radius: 4px;
                background: rgba(0, 0, 0, 100);
            }
            QLabel:hover {
                border: 1px solid rgba(176, 255, 123, 0.7);
            }
        """)
        self.setAlignment(Qt.AlignCenter)
        
        # サムネイル読み込み
        pix = QPixmap(image_path)
        if not pix.isNull():
            scaled = pix.scaled(
                THUMB_WIDTH - 4, THUMB_HEIGHT - 4,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(scaled)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.image_path)


class MapImageDialog(QDialog):
    """拡大画像表示ダイアログ（リサイズ可能、サイズ保持）"""
    
    def __init__(self, image_path: str, all_paths: list[str] = None, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.all_paths = all_paths or [image_path]
        self.current_index = self.all_paths.index(image_path) if image_path in self.all_paths else 0
        self._pixmaps = {}  # キャッシュ
        self._target_pos = None
        self._positioned = False

        self.setWindowTitle(os.path.basename(image_path))
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background: #111122;")
        self.setMinimumSize(200, 150)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 画像ラベル
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.image_label, stretch=1)
        
        # ファイル名 + ナビ表示
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #888888; font-size: 13px; margin-top: 5px;")
        layout.addWidget(self.info_label)
        
        # 保存されたサイズを復元
        from src.utils.config_manager import ConfigManager
        config = ConfigManager.load_config()
        saved_w = config.get("map_viewer_width", 0)
        saved_h = config.get("map_viewer_height", 0)
        
        if saved_w > 0 and saved_h > 0:
            self.resize(saved_w, saved_h)
            self._show_image()
        else:
            self._show_image(initial=True)
    
    def _get_pixmap(self, path: str) -> QPixmap:
        if path not in self._pixmaps:
            self._pixmaps[path] = QPixmap(path)
        return self._pixmaps[path]
    
    def _show_image(self, initial=False):
        path = self.all_paths[self.current_index]
        pix = self._get_pixmap(path)
        if not pix.isNull():
            if initial:
                # 初回はモニター60%に合わせる
                from PySide6.QtWidgets import QApplication
                screen = QApplication.primaryScreen()
                if screen:
                    screen_size = screen.availableSize()
                    max_w = int(screen_size.width() * 0.6)
                    max_h = int(screen_size.height() * 0.6)
                else:
                    max_w, max_h = 600, 450
                scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.resize(scaled.width() + 20, scaled.height() + 50)
            
            # ダイアログの現在サイズに合わせて画像をフィット
            avail_w = self.width() - 20
            avail_h = self.height() - 50
            scaled = pix.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)
        
        fname = os.path.basename(path)
        total = len(self.all_paths)
        idx = self.current_index + 1
        nav_hint = "画像の左右いずれかを左クリック、または←→キーで切替 / ESCで閉じる" if total > 1 else "ESCで閉じる"
        self.info_label.setText(f"{fname}  ({idx}/{total})   {nav_hint}")
        self.setWindowTitle(f"{fname} ({idx}/{total})")
    
    def showEvent(self, event):
        super().showEvent(event)
        if self._target_pos is not None and not self._positioned:
            self._positioned = True
            self.hide()
            pos = self._target_pos
            QTimer.singleShot(10, lambda: self._apply_position(pos))

    def _apply_position(self, pos):
        self.move(pos)
        self.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # リサイズ時に画像を再フィット
        if self.all_paths:
            self._show_image()
    
    def closeEvent(self, event):
        # サイズを保存
        from src.utils.config_manager import ConfigManager
        config = ConfigManager.load_config()
        config["map_viewer_width"] = self.width()
        config["map_viewer_height"] = self.height()
        ConfigManager.save_config(config)
        super().closeEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and len(self.all_paths) > 1:
            # ダイアログの左半分クリック → 前へ、右半分 → 次へ
            if event.position().x() >= self.width() / 2:
                if self.current_index < len(self.all_paths) - 1:
                    self.current_index += 1
                    self._show_image()
            else:
                if self.current_index > 0:
                    self.current_index -= 1
                    self._show_image()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_Right, Qt.Key_Space):
            if self.current_index < len(self.all_paths) - 1:
                self.current_index += 1
                self._show_image()
        elif event.key() == Qt.Key_Left:
            if self.current_index > 0:
                self.current_index -= 1
                self._show_image()


class FlowLayout(QVBoxLayout):
    """サムネイルを横に並べて自動折り返しするレイアウト（QHBoxLayoutの行を動的に追加）"""
    pass


class MapThumbnailWidget(QWidget):
    """マップサムネイル一覧ウィジェット（折り返しグリッド表示）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_paths = []
        self._thumbs = []
        self._open_dialog = None
        self.auto_open = False
        self.auto_position = True
        
        self.setStyleSheet("background: transparent;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 0, 0)
        main_layout.setSpacing(2)
        
        # ヘッダ
        self.header_label = QLabel("🗺 マップレイアウト")
        self.header_label.setStyleSheet(
            "color: rgba(176, 255, 123, 0.7); font-size: 11px; font-weight: bold;"
        )
        main_layout.addWidget(self.header_label)
        
        # サムネイルコンテナ（行を動的に追加）
        self.thumb_container = QWidget()
        self.thumb_container.setStyleSheet("background: transparent;")
        self.thumb_container_layout = QVBoxLayout(self.thumb_container)
        self.thumb_container_layout.setContentsMargins(0, 2, 0, 2)
        self.thumb_container_layout.setSpacing(4)
        
        main_layout.addWidget(self.thumb_container)
    
    def load_maps(self, zone_name: str, part2: bool = False, zone_changed: bool = False, route: str = ""):
        """ゾーンのマップ画像を読み込んで表示"""
        # 開いているマップダイアログを閉じる
        if self._open_dialog is not None:
            self._open_dialog.close()
            self._open_dialog = None
        self._clear_thumbs()
        
        paths = load_zone_maps(zone_name, part2=part2, route=route)
        self.current_paths = paths
        
        if not paths:
            self.setVisible(False)
            return
        
        self.setVisible(True)
        self.header_label.setText(f"🗺 マップレイアウト ({len(paths)}パターン)")
        
        # 親ウィジェットの幅からサムネイル列数を計算
        available_width = max(self.width(), 380) - 10  # マージン考慮
        cols = max(1, available_width // (THUMB_WIDTH + 6))
        
        row_layout = None
        for i, p in enumerate(paths):
            if i % cols == 0:
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)
                row_layout.setAlignment(Qt.AlignLeft)
                self.thumb_container_layout.addLayout(row_layout)
            
            thumb = ClickableThumb(p, self.thumb_container)
            thumb.clicked.connect(self._on_thumb_clicked)
            self._thumbs.append(thumb)
            row_layout.addWidget(thumb)

        # auto_open が有効 かつ エリア移動時のみ自動的にダイアログを開く
        if self.auto_open and zone_changed and paths:
            self._on_thumb_clicked(paths[0])

    def _on_thumb_clicked(self, image_path: str):
        """サムネイルクリック → 拡大表示（メインウィンドウと同じモニターの左隣に配置）"""
        # 親なしで作成（exec()による親基準の中央配置を防ぐ）
        dialog = MapImageDialog(image_path, all_paths=self.current_paths, parent=None)

        # メインウィンドウがいるモニター基準で隣に配置
        if self.auto_position:
            main_win = self.window()
            if main_win:
                from PySide6.QtWidgets import QApplication
                main_geo = main_win.frameGeometry()
                dialog_w = dialog.width()
                dialog_h = dialog.height()

                # メインウィンドウがいるモニターを特定
                main_center = main_geo.center()
                screen = QApplication.screenAt(main_center)
                if not screen:
                    screen = QApplication.primaryScreen()
                if screen:
                    sg = screen.availableGeometry()

                    # 左側にぴったりくっつけて配置（同じモニター内に収める）
                    left_x = main_geo.left() - dialog_w
                    right_x = main_geo.right() + 1

                    if left_x >= sg.left():
                        x = left_x
                    elif right_x + dialog_w <= sg.left() + sg.width():
                        x = right_x
                    else:
                        x = sg.left()

                    # 縦位置はメインウィンドウの上端に合わせる（画面内に収める）
                    y = main_geo.top()
                    if y + dialog_h > sg.top() + sg.height():
                        y = max(sg.top(), sg.top() + sg.height() - dialog_h)

                    dialog._target_pos = QPoint(x, y)

        # auto_positionがOFFの場合、サムネイルのすぐ上・中央揃えで表示
        if dialog._target_pos is None:
            main_win = self.window()
            if main_win:
                main_geo = main_win.frameGeometry()
                dialog_w = dialog.width()
                dialog_h = dialog.height()
                # X: メインウィンドウの中央にダイアログの中央を合わせる
                x = main_geo.left() + (main_geo.width() - dialog_w) // 2
                # Y: サムネイル領域の画面上端のすぐ上にダイアログ下端を合わせる
                thumb_global_y = self.mapToGlobal(QPoint(0, 0)).y()
                y = thumb_global_y - dialog_h - 5
                if y < 0:
                    y = 0
                dialog._target_pos = QPoint(x, y)

        self._open_dialog = dialog
        dialog.finished.connect(self._on_dialog_closed)
        dialog.open()
    
    def _on_dialog_closed(self):
        """ダイアログが閉じられた時の後片付け"""
        self._open_dialog = None

    def _clear_thumbs(self):
        """サムネイルを全削除"""
        for thumb in self._thumbs:
            thumb.deleteLater()
        self._thumbs = []
        # 行レイアウトも削除
        while self.thumb_container_layout.count():
            item = self.thumb_container_layout.takeAt(0)
            layout = item.layout()
            if layout:
                while layout.count():
                    layout.takeAt(0)
                # QLayoutはdeleteLater不要、親から外せばGCされる
    
    def clear(self):
        """表示をクリア"""
        if self._open_dialog is not None:
            self._open_dialog.close()
            self._open_dialog = None
        self._clear_thumbs()
        self.current_paths = []
        self.setVisible(False)

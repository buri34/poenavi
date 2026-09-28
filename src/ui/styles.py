class Styles:
    TEXT_COLOR = "#b0ff7b"
    # 背景を半透明の黒にする (RGBA)
    BACKGROUND_COLOR = "rgba(0, 0, 0, 180)" 
    
    MAIN_WINDOW = f"""
        QMainWindow {{
            background-color: {BACKGROUND_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {TEXT_COLOR};
            border-radius: 10px;
        }}
        QWidget {{
            background-color: transparent;
            color: {TEXT_COLOR};
        }}
        QMenu {{
            background-color: #222222;
            color: {TEXT_COLOR};
            border: 1px solid {TEXT_COLOR};
        }}
        QMenu::item:selected {{
            background-color: #444444;
        }}
    """
    
    TIMER_LABEL = f"""
        QLabel {{
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 96px;
            font-weight: bold;
            color: {TEXT_COLOR};
        }}
    """
    
    BUTTON = f"""
        QPushButton {{
            background-color: rgba(26, 26, 26, 200);
            color: {TEXT_COLOR};
            border: 1px solid {TEXT_COLOR};
            border-radius: 4px;
            padding: 5px 10px;
            font-family: 'Noto Sans JP', sans-serif;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: rgba(42, 42, 42, 200);
            border: 1px solid #ffffff;
        }}
        QPushButton:pressed {{
            background-color: #000000;
        }}
    """
    
    # ラップタイム表示用スタイル
    LAP_ITEM_BASE = f"""
        QLabel {{
            font-family: 'Noto Sans JP', sans-serif;
            font-size: 14px;
            padding: 2px 8px;
        }}
    """
    
    LAP_ITEM_COMPLETED = f"""
        QLabel {{
            font-family: 'Noto Sans JP', sans-serif;
            font-size: 14px;
            padding: 2px 8px;
            color: rgba(176, 255, 123, 0.7);
        }}
    """
    
    LAP_ITEM_CURRENT = f"""
        QLabel {{
            font-family: 'Noto Sans JP', sans-serif;
            font-size: 14px;
            font-weight: bold;
            padding: 2px 8px;
            color: {TEXT_COLOR};
        }}
    """
    
    CHECKBOX = f"""
        QCheckBox {{
            color: {TEXT_COLOR}; font-size: 12px; spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 18px; height: 18px;
            border: 2px solid #888888;
            border-radius: 3px;
            background: transparent;
        }}
        QCheckBox::indicator:checked {{
            background: #4488ff;
            border: 2px solid #4488ff;
            image: none;
        }}
        QCheckBox::indicator:checked::after {{
            content: "";
        }}
    """
    
    # Final version with checkmark via unicode trick won't work in Qt.
    # We rely on the contrasting background color to indicate checked state,
    # plus we'll programmatically create a checkmark icon at runtime.
    # For stylesheet-only approach, the blue background is clear enough.
    CHECKBOX = f"""
        QCheckBox {{
            color: {TEXT_COLOR}; font-size: 12px; spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 18px; height: 18px;
            border: 2px solid #888888;
            border-radius: 3px;
            background: transparent;
        }}
        QCheckBox::indicator:checked {{
            background: #4488ff;
            border: 2px solid #4488ff;
        }}
        QCheckBox::indicator:unchecked:hover {{
            border: 2px solid {TEXT_COLOR};
        }}
    """
    
    @staticmethod
    def apply_checkbox_style(
        checkbox, checked_color="#4488ff", *, match_native_indicator=False,
    ):
        """Apply checkbox style with a proper checkmark icon."""
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
        from PySide6.QtWidgets import QStyle

        border_width = 2
        indicator_width = 18
        indicator_height = 18
        if match_native_indicator:
            native_width = checkbox.style().pixelMetric(
                QStyle.PixelMetric.PM_IndicatorWidth, None, checkbox,
            )
            native_height = checkbox.style().pixelMetric(
                QStyle.PixelMetric.PM_IndicatorHeight, None, checkbox,
            )
            border_width = 1
            indicator_width = max(1, native_width - (border_width * 2))
            indicator_height = max(1, native_height - (border_width * 2))
            checkbox.setProperty("poenaviNativeIndicatorWidth", native_width)
            checkbox.setProperty("poenaviNativeIndicatorHeight", native_height)

        # Create checkmark pixmap
        pixmap = QPixmap(indicator_width, indicator_height)
        checked_qcolor = QColor(checked_color)
        pixmap.fill(checked_qcolor)
        painter = QPainter(pixmap)
        pen_width = 2.5
        if match_native_indicator:
            pen_width = max(1.5, min(indicator_width, indicator_height) * 0.16)
        pen = QPen(QColor("white"), pen_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setRenderHint(QPainter.Antialiasing)
        # Draw checkmark path
        if match_native_indicator:
            painter.drawLine(
                round(indicator_width * 0.22), round(indicator_height * 0.50),
                round(indicator_width * 0.40), round(indicator_height * 0.72),
            )
            painter.drawLine(
                round(indicator_width * 0.40), round(indicator_height * 0.72),
                round(indicator_width * 0.78), round(indicator_height * 0.28),
            )
        else:
            painter.drawLine(4, 9, 7, 13)
            painter.drawLine(7, 13, 14, 5)
        painter.end()
        
        # Unchecked pixmap (transparent with border - handled by stylesheet)
        unchecked = QPixmap(indicator_width, indicator_height)
        unchecked.fill(QColor(0, 0, 0, 0))
        
        icon = QIcon()
        icon.addPixmap(pixmap, QIcon.Normal, QIcon.On)
        icon.addPixmap(unchecked, QIcon.Normal, QIcon.Off)
        checkbox.setIcon(icon)
        checkbox.setIconSize(QSize(0, 0))  # Hide icon, we use it only for indicator
        
        # Use stylesheet with image approach
        import os
        import tempfile
        tmp_dir = tempfile.gettempdir()
        color_key = checked_qcolor.name().removeprefix("#")
        size_suffix = (
            f"_{indicator_width}x{indicator_height}"
            if match_native_indicator else ""
        )
        check_path = os.path.join(
            tmp_dir, f"poenavi_check_{color_key}{size_suffix}.png",
        )
        pixmap.save(check_path)
        
        checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {Styles.TEXT_COLOR}; font-size: 12px; spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: {indicator_width}px; height: {indicator_height}px;
                border: {border_width}px solid #888888;
                border-radius: 3px;
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                image: url("{check_path.replace(os.sep, '/')}");
                border: {border_width}px solid {checked_qcolor.name()};
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: {border_width}px solid {Styles.TEXT_COLOR};
            }}
        """)

    LAP_ITEM_PENDING = f"""
        QLabel {{
            font-family: 'Noto Sans JP', sans-serif;
            font-size: 14px;
            padding: 2px 8px;
            color: rgba(128, 128, 128, 0.6);
        }}
    """


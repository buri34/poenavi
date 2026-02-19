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
            font-family: 'Segoe UI', sans-serif;
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
            font-family: 'Segoe UI', sans-serif;
            font-size: 14px;
            padding: 2px 8px;
        }}
    """
    
    LAP_ITEM_COMPLETED = f"""
        QLabel {{
            font-family: 'Segoe UI', sans-serif;
            font-size: 14px;
            padding: 2px 8px;
            color: rgba(176, 255, 123, 0.7);
        }}
    """
    
    LAP_ITEM_CURRENT = f"""
        QLabel {{
            font-family: 'Segoe UI', sans-serif;
            font-size: 14px;
            font-weight: bold;
            padding: 2px 8px;
            color: {TEXT_COLOR};
        }}
    """
    
    LAP_ITEM_PENDING = f"""
        QLabel {{
            font-family: 'Segoe UI', sans-serif;
            font-size: 14px;
            padding: 2px 8px;
            color: rgba(128, 128, 128, 0.6);
        }}
    """


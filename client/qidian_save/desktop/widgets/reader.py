"""文本阅读器组件 — 分页/滚动 + 字体控制 + 暗色模式"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QSlider, QFrame,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QTextOption


class Reader(QWidget):
    """纯文本阅读器，支持字体大小调节和暗色切换"""

    MODE_LIGHT = """
        QTextEdit {
            background: #fafafa; color: #1f2937;
            border: none; padding: 24px 32px;
            line-height: 1.8; selection-background-color: #bfdbfe;
        }
    """
    MODE_DARK = """
        QTextEdit {
            background: #1a1a2e; color: #e2e8f0;
            border: none; padding: 24px 32px;
            line-height: 1.8; selection-background-color: #3b82f6;
        }
    """

    def __init__(self):
        super().__init__()
        self._dark_mode = False
        self._font_size = 16
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            background: white; border-bottom: 1px solid #e5e7eb;
            padding: 8px 16px;
        """)
        toolbar.setFixedHeight(48)
        tr = QHBoxLayout(toolbar)
        tr.setContentsMargins(16, 4, 16, 4)
        tr.setSpacing(8)

        tr.addWidget(QLabel("字号:"))

        self.btn_font_smaller = QPushButton("A−")
        self.btn_font_smaller.setFixedSize(32, 28)
        self.btn_font_smaller.setStyleSheet("border: 1px solid #d1d5db; border-radius: 4px; font-size: 12px;")
        self.btn_font_smaller.clicked.connect(lambda: self._adjust_font(-2))
        tr.addWidget(self.btn_font_smaller)

        self.btn_font_larger = QPushButton("A+")
        self.btn_font_larger.setFixedSize(32, 28)
        self.btn_font_larger.setStyleSheet("border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px;")
        self.btn_font_larger.clicked.connect(lambda: self._adjust_font(2))
        tr.addWidget(self.btn_font_larger)

        tr.addSpacing(20)

        self.btn_theme = QPushButton("🌙 暗色")
        self.btn_theme.setStyleSheet("""
            border: 1px solid #d1d5db; border-radius: 6px;
            padding: 4px 12px; font-size: 12px;
        """)
        self.btn_theme.clicked.connect(self._toggle_theme)
        tr.addWidget(self.btn_theme)

        tr.addStretch()

        self.label_info = QLabel("")
        self.label_info.setStyleSheet("font-size: 11px; color: #9ca3af;")
        tr.addWidget(self.label_info)

        layout.addWidget(toolbar)

        # Text area
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.text_edit.setStyleSheet(self.MODE_LIGHT)
        self.text_edit.setFont(QFont("Microsoft YaHei", self._font_size))
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.text_edit, 1)

    def load_text(self, text: str, title: str = ""):
        self.text_edit.setPlainText(text)
        char_count = len(text)
        cjk = sum(1 for c in text if '一' <= c <= '鿿')
        self.label_info.setText(f"{char_count} 字符 | {cjk} 中文字 | 字号 {self._font_size}")

    def _adjust_font(self, delta: int):
        self._font_size = max(10, min(36, self._font_size + delta))
        self.text_edit.setFont(QFont("Microsoft YaHei", self._font_size))

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        if self._dark_mode:
            self.text_edit.setStyleSheet(self.MODE_DARK)
            self.btn_theme.setText("☀️ 亮色")
        else:
            self.text_edit.setStyleSheet(self.MODE_LIGHT)
            self.btn_theme.setText("🌙 暗色")

    def clear(self):
        self.text_edit.clear()
        self.label_info.setText("")

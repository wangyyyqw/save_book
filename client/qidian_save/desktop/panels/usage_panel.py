"""用量查询面板 — 显示今日用量 + 套餐信息"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class UsagePanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self._stat_labels = {}  # label → QLabel reference
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card {
                background: white; border-radius: 16px;
                padding: 40px; max-width: 500px;
            }
        """)
        card.setFixedWidth(500)
        cl = QVBoxLayout(card)
        cl.setSpacing(20)

        title = QLabel("  用量查询")
        title.setProperty("widget-type", "panel-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        # Usage ring/progress
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(24)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: none; border-radius: 12px;
                background: #e5e7eb; height: 24px;
                text-align: center; font-size: 12px;
                font-weight: bold; color: #374151;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #10b981);
                border-radius: 12px;
            }
        """)
        cl.addWidget(self.progress)

        # Stat cards
        stats = QHBoxLayout()
        stats.setSpacing(16)

        for label, color in [("已用", "#3b82f6"), ("剩余", "#10b981"), ("限额", "#f59e0b")]:
            box = QFrame()
            box.setStyleSheet(f"""
                background: {color}10; border-radius: 10px;
                border: 1px solid {color}30; padding: 16px;
            """)
            bl = QVBoxLayout(box)
            bl.setSpacing(4)
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 12px; color: #6b7280; font-weight: 600;")
            bl.addWidget(lbl)

            val = QLabel("--")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {color};")
            self._stat_labels[label] = val
            bl.addWidget(val)

            stats.addWidget(box, 1)

        cl.addLayout(stats)

        # Refresh button
        self.btn_refresh = QPushButton("  刷新")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._refresh)
        cl.addWidget(self.btn_refresh)

        # Reset time
        self.label_reset = QLabel("")
        self.label_reset.setStyleSheet("font-size: 12px; color: #9ca3af;")
        self.label_reset.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.label_reset)

        layout.addWidget(card)

        # Auto refresh on init
        self._refresh()

    def _refresh(self):
        try:
            usage = self.client.get_usage()
            used = usage["chaptersUsed"]
            limit = usage["limit"]
            remaining = usage["remaining"]
            reset = usage.get("resetAt", "")

            self._stat_labels["已用"].setText(str(used))
            self._stat_labels["剩余"].setText(str(remaining))
            self._stat_labels["限额"].setText(str(limit))

            pct = min(100, int(used / limit * 100)) if limit > 0 else 0
            self.progress.setFormat(f"{used} / {limit} 次 ({pct}%)")
            self.progress.setValue(pct)

            self.label_reset.setText(f"重置时间: {reset}")
        except Exception as e:
            for lbl in self._stat_labels.values():
                lbl.setText("?")
            self.label_reset.setText(f"查询失败: {str(e)}")

"""qidian_save 桌面主应用 — 登录后才能进入主界面"""
import sys, os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QStatusBar, QLabel, QFrame,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ..api_client import QidianSaveClient
from ..qidian_client import set_cookie_path


TOKEN_FILE = Path.home() / ".qidian_save" / "token"


def _save_token(token: str):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")


def _load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""


from .panels.login_panel import LoginPanel
from .panels.qidian_login_panel import QidianLoginPanel
from .panels.search_panel import SearchPanel
from .panels.book_detail_panel import BookDetailPanel
from .panels.backup_panel import BackupPanel
from .panels.qd_decrypt_panel import QDDecryptPanel
from .panels.usage_panel import UsagePanel
from .panels.bookshelf_panel import BookshelfPanel


NAV_ITEMS = [
    ("起点扫码", "📱"),
    ("搜索书籍", "🔍"),
    ("书籍详情", "📖"),
    ("书架", "📚"),
    ("在线备份", "💾"),
    ("本地备份", "🔓"),
    ("用量查询", "📊"),
]


class NavButton(QPushButton):
    def __init__(self, text, icon_char, parent=None):
        super().__init__(parent)
        self.setText(f"  {icon_char}  {text}")
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        font = QFont("Microsoft YaHei", 11)
        self.setFont(font)

    def set_active(self, active: bool):
        self.setChecked(active)
        if active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #3b82f6; color: white;
                    border: none; border-radius: 8px;
                    padding: 0 16px; text-align: left;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent; color: #cbd5e1;
                    border: none; border-radius: 8px;
                    padding: 0 16px; text-align: left;
                }
                QPushButton:hover {
                    background-color: rgba(255,255,255,0.1);
                }
            """)


class MainWindow(QMainWindow):
    def __init__(self, client: QidianSaveClient):
        super().__init__()
        self.client = client
        self.token = ""
        self.current_task_id = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("qidian_save — 起点书籍保存工具")
        self.setMinimumSize(1100, 720)
        self.resize(1200, 800)

        # ── 顶层 QStackedWidget: 登录页 / 主界面 ──
        self.root_stack = QStackedWidget()
        self.setCentralWidget(self.root_stack)

        # ─── Page 0: 登录页（全屏居中，无侧栏） ───
        login_wrapper = QWidget()
        login_wrapper.setStyleSheet("background-color: #f0f4f8;")
        login_layout = QVBoxLayout(login_wrapper)
        login_layout.setContentsMargins(0, 0, 0, 0)
        self.login_panel = LoginPanel(self.client, self._on_login_success)
        login_layout.addWidget(self.login_panel)
        self.root_stack.addWidget(login_wrapper)

        # ─── Page 1: 主界面（侧栏 + 面板 + 状态栏） ───
        main_page = QWidget()
        main_layout = QHBoxLayout(main_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet("background-color: #1e1e2e;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 20)
        sidebar_layout.setSpacing(4)

        logo = QLabel("  📚  qidian_save")
        logo.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        logo.setStyleSheet("color: white; padding: 8px 4px 20px 4px;")
        sidebar_layout.addWidget(logo)

        self.nav_buttons = []
        for i, (name, icon) in enumerate(NAV_ITEMS):
            btn = NavButton(name, icon)
            btn.clicked.connect(lambda checked, idx=i: self._switch_panel(idx))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        ver = QLabel("v0.1.0 · client-bate")
        ver.setFont(QFont("Microsoft YaHei", 9))
        ver.setStyleSheet("color: #6b7280; padding: 8px 4px;")
        sidebar_layout.addWidget(ver)

        main_layout.addWidget(sidebar)

        # ── Content area ──
        content = QFrame()
        content.setStyleSheet("background-color: #f8f9fa;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        main_layout.addWidget(content, 1)

        # ── Panels ──
        self.panels = []
        self.panels.append(QidianLoginPanel(self.client))
        self.panels.append(SearchPanel(self.client, self._on_book_selected))
        self.panels.append(BookDetailPanel(self.client, self._on_backup_started))
        self.panels.append(BookshelfPanel(self.client, self._on_book_selected))
        self.panels.append(BackupPanel(self.client))
        self.panels.append(QDDecryptPanel(self.client))
        self.panels.append(UsagePanel(self.client))

        for p in self.panels:
            self.stack.addWidget(p)

        self.root_stack.addWidget(main_page)

        # ── Status bar ──
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar { background: #f1f5f9; border-top: 1px solid #e2e8f0; padding: 2px 12px; }
            QStatusBar::item { border: none; }
        """)
        self.status_label = QLabel("未登录")
        self.status_label.setFont(QFont("Microsoft YaHei", 10))
        self.status_bar.addWidget(self.status_label)
        self.setStatusBar(self.status_bar)

        # 启动时仅显示登录页
        self.root_stack.setCurrentIndex(0)
        self.status_bar.setVisible(False)

        # 如果已有 Token（文件或环境变量），验证后自动跳过登录
        if self.client.session.headers.get("Authorization"):
            QTimer.singleShot(100, self._try_auto_login)

        # Usage timer（登录后启用）
        self._usage_timer = QTimer()
        self._usage_timer.timeout.connect(self._update_usage)

    def _try_auto_login(self):
        """尝试使用已保存的 Token 自动登录（QTimer 主线程重试，避免线程安全问题）"""
        self._login_attempts = 0
        self._max_login_attempts = 3
        self._do_auto_login()

    def _do_auto_login(self):
        import requests as _req
        token = self.client.session.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return

        self._login_attempts += 1
        self.login_panel.show_auto_login_status(
            f"正在自动登录 ({self._login_attempts}/{self._max_login_attempts})..."
        )

        try:
            self.client.get_me()
            self._on_login_success(token)
            return
        except (_req.ConnectionError, _req.Timeout):
            if self._login_attempts < self._max_login_attempts:
                QTimer.singleShot(2000, self._do_auto_login)
            else:
                self.login_panel.show_auto_login_status(
                    f"自动登录失败: 无法连接到服务器 ({self.client.base_url})", error=True)
        except Exception as e:
            reason = str(e)
            if "403" in reason and "封禁" in reason:
                self.login_panel.show_auto_login_status("账号已被封禁，请联系管理员", error=True)
            elif "403" in reason:
                # 非封禁 403（如限流、IP 封禁）— 显示服务端原文
                self.login_panel.show_auto_login_status(f"自动登录失败: {reason[:80]}", error=True)
            elif "401" in reason or "unauthorized" in reason.lower():
                self.login_panel.show_auto_login_status("Token 已过期，请重新登录", error=True)
            else:
                self.login_panel.show_auto_login_status(f"自动登录失败: {reason[:50]}", error=True)

    def _switch_panel(self, idx: int):
        for btn in self.nav_buttons:
            btn.set_active(False)
        self.nav_buttons[idx].set_active(True)
        self.stack.setCurrentIndex(idx)

    def _on_login_success(self, token: str):
        self.token = token
        self.client.set_token(token)
        _save_token(token)  # 持久化 Token，下次启动自动登录
        self.status_label.setText(f"已登录 · Token: {token[:16]}...")
        self.status_bar.setVisible(True)
        self.root_stack.setCurrentIndex(1)  # 切换到主界面
        self._switch_panel(0)               # 默认选中起点扫码
        self._usage_timer.start(60000)

    def _on_book_selected(self, book_id: str, book_name: str):
        self.panels[2].load_book(book_id, book_name)
        self._switch_panel(2)

    def _on_backup_started(self, task_id: int):
        self.current_task_id = task_id
        self.panels[4].load_task(task_id)
        self._switch_panel(4)

    def _update_usage(self):
        if not self.token:
            return
        try:
            usage = self.client.get_usage()
            self.status_label.setText(
                f"已登录 · 今日 {usage['chaptersUsed']}/{usage['limit']} 次"
            )
        except Exception:
            pass


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 初始化 Cookie 持久化路径
    set_cookie_path()

    # Global stylesheet
    app.setStyleSheet("""
        QToolTip {
            background-color: #1f2937; color: white;
            border: none; padding: 6px 10px; border-radius: 4px;
            font-size: 12px;
        }
    """)

    base = os.getenv("QIDIAN_SAVE_URL", "http://localhost:8000")
    token = os.getenv("QIDIAN_SAVE_TOKEN", "") or _load_token()
    client = QidianSaveClient(base, token=token)

    window = MainWindow(client)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

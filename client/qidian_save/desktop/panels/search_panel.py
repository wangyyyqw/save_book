"""搜索书籍面板 — 关键词搜索 + 结果列表 + 跳转到详情"""
import threading, sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFrame,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont
from ...qidian_client import search_books as qidian_search


class _SearchSignal(QObject):
    results_ready = pyqtSignal(list)
    search_error = pyqtSignal(str)
    search_done = pyqtSignal()


class SearchPanel(QWidget):
    def __init__(self, client, on_select_book):
        super().__init__()
        self.client = client
        self.on_select_book = on_select_book
        self._sig = _SearchSignal()
        self._sig.results_ready.connect(self._on_results)
        self._sig.search_error.connect(lambda e: self.status_label.setText(f"搜索失败: {e}"))
        self._sig.search_done.connect(self._on_search_done)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        header = QLabel("搜索书籍")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #1f2937;")
        layout.addWidget(header)

        # Search input row
        search_bg = QFrame()
        search_bg.setStyleSheet("background: white; border-radius: 12px; padding: 20px;")
        sr = QHBoxLayout(search_bg)
        sr.setSpacing(12)

        self.input_keyword = QLineEdit()
        self.input_keyword.setPlaceholderText("输入书名、作者或关键词...")
        self.input_keyword.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d5db; border-radius: 8px;
                padding: 12px 16px; font-size: 14px; background: #f9fafb;
            }
            QLineEdit:focus { border-color: #3b82f6; background: white; }
        """)
        self.input_keyword.returnPressed.connect(self._do_search)
        sr.addWidget(self.input_keyword, 1)

        self.btn_search = QPushButton("  搜索")
        self.btn_search.setStyleSheet("""
            QPushButton {
                background-color: #2563eb; color: white; border: none;
                border-radius: 8px; padding: 12px 28px; font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:disabled { background-color: #93c5fd; }
        """)
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.clicked.connect(self._do_search)
        sr.addWidget(self.btn_search)

        layout.addWidget(search_bg)

        # Results table
        table_frame = QFrame()
        table_frame.setStyleSheet("background: white; border-radius: 12px;")

        tl = QVBoxLayout(table_frame)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书籍 ID", "书名", "作者", "操作"])
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                border: none; border-radius: 12px;
                font-size: 13px;
                gridline-color: #f3f4f6;
            }
            QTableWidget::item { padding: 8px 12px; }
            QTableWidget::item:selected { background: #eff6ff; color: #1f2937; }
            QHeaderView::section {
                background: #f8fafc; border: none;
                padding: 10px 12px; font-weight: bold;
                font-size: 12px; color: #64748b;
            }
        """)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        tl.addWidget(self.table)

        layout.addWidget(table_frame, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #9ca3af;")
        layout.addWidget(self.status_label)

    def _do_search(self):
        keyword = self.input_keyword.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            return

        self.btn_search.setEnabled(False)
        self.btn_search.setText("搜索中...")
        self.status_label.setText("正在搜索...")
        self.table.setRowCount(0)

        def _search():
            try:
                print(f"[search] 开始搜索: {keyword}", file=sys.stderr)
                results = qidian_search(keyword)
                print(f"[search] 结果数量: {len(results)}", file=sys.stderr)
                self._sig.results_ready.emit(results)
            except Exception as e:
                print(f"[search] 异常: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                self._sig.search_error.emit(str(e))
            finally:
                self._sig.search_done.emit()

        threading.Thread(target=_search, daemon=True).start()

    def _on_results(self, results: list):
        self.table.setRowCount(len(results))
        for i, r in enumerate(results):
            self.table.setItem(i, 0, QTableWidgetItem(r["bookId"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["bookName"]))
            self.table.setItem(i, 2, QTableWidgetItem(r["authorName"]))

            btn_sel = QPushButton("查看详情")
            btn_sel.setStyleSheet("""
                QPushButton {
                    background: #2563eb; color: white; border: none;
                    border-radius: 4px; padding: 4px 12px; font-size: 12px;
                }
                QPushButton:hover { background: #1d4ed8; }
            """)
            btn_sel.setCursor(Qt.CursorShape.PointingHandCursor)
            bid = r["bookId"]
            bname = r["bookName"]
            btn_sel.clicked.connect(lambda checked, x=bid, n=bname: self.on_select_book(x, n))
            self.table.setCellWidget(i, 3, btn_sel)

        self.status_label.setText(f"找到 {len(results)} 个结果")

    def _on_search_done(self):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("  搜索")

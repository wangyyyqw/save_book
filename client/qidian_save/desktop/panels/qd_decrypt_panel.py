""".qd 解密面板 — 小白模式：拉取 → 选书 → 选章节 → 一键解密"""
import os, sys, threading, sqlite3, zipfile, subprocess, json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QFrame, QMessageBox, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QCheckBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon


class _DecryptSignal(QObject):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    book_list_ready = pyqtSignal(list)
    decrypt_done = pyqtSignal(str)
    capture_status = pyqtSignal(str, str)  # (status, qimei36/pool/userid 逗号分隔)


class QDDecryptPanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self._sig = _DecryptSignal()
        self._sig.log.connect(self._append_log)
        self._sig.error.connect(lambda e: self._append_log(f"❌ {e}"))
        self._sig.book_list_ready.connect(self._show_books)
        self._sig.decrypt_done.connect(self._on_decrypt_done)
        self._sig.capture_status.connect(self._on_capture_status)
        self._qd_dir = ""           # 拉取到的 qd_files 目录
        self._current_book_id = ""  # 当前选中的书籍 ID
        self._current_book_dir = "" # 当前选中的书籍目录
        self._chapter_map = {}      # chapterId → chapterName 映射
        self._selected_ids = set()  # 用户勾选的章节 ID
        self._capture_process = None
        self._capture_timer = QTimer()
        self._capture_timer.timeout.connect(self._poll_capture_config)
        self._init_ui()
        self._check_device()

    # ── UI ──────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # ── 顶部：状态 + 操作按钮 ──
        top = QFrame()
        top.setStyleSheet("background: white; border-radius: 10px; padding: 14px;")
        tr = QHBoxLayout(top)
        tr.setSpacing(10)

        self.label_device = QLabel("⏳ 检测 ADB...")
        self.label_device.setStyleSheet("font-size: 13px; padding: 4px 8px;")
        tr.addWidget(self.label_device)

        self.btn_pull = QPushButton("  📱 拉取书籍")
        self.btn_pull.setStyleSheet(self._btn_style("#6366f1"))
        self.btn_pull.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pull.setFixedHeight(38)
        self.btn_pull.clicked.connect(self._pull_books)
        tr.addWidget(self.btn_pull)

        self.btn_open_dir = QPushButton("  📂 打开目录")
        self.btn_open_dir.setStyleSheet(self._btn_style("#6b7280"))
        self.btn_open_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_dir.setFixedHeight(38)
        self.btn_open_dir.clicked.connect(self._open_dir)
        tr.addWidget(self.btn_open_dir)

        self.label_capture = QLabel("")
        self.label_capture.setStyleSheet("font-size: 12px; padding: 4px 8px; color: #6b7280;")
        self.label_capture.setVisible(False)
        tr.addWidget(self.label_capture)

        self.btn_capture = QPushButton("  📡 参数捕获")
        self.btn_capture.setStyleSheet(self._btn_style("#f59e0b"))
        self.btn_capture.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_capture.setFixedHeight(38)
        self.btn_capture.clicked.connect(self._toggle_capture)
        tr.addWidget(self.btn_capture)

        self.btn_root_extract = QPushButton("  🛠️ root提取")
        self.btn_root_extract.setStyleSheet(self._btn_style("#8b5cf6"))
        self.btn_root_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_root_extract.setFixedHeight(38)
        self.btn_root_extract.clicked.connect(self._root_extract)
        tr.addWidget(self.btn_root_extract)

        layout.addWidget(top)

        # ── 中部：书籍 + 章节列表 ──
        center = QFrame()
        center.setStyleSheet("background: white; border-radius: 10px;")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["书名 / 章节", "状态", "大小"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                border: none; border-radius: 10px;
                font-size: 13px;
            }
            QTreeWidget::item { padding: 6px 10px; }
            QTreeWidget::item:selected { background: #eff6ff; color: #1f2937; }
            QHeaderView::section {
                background: #f8fafc; border: none;
                padding: 8px 10px; font-weight: bold;
                font-size: 12px; color: #64748b;
            }
        """)
        self.tree.setColumnCount(3)
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAnimated(True)
        self.tree.setIndentation(20)
        self.tree.itemChanged.connect(self._on_item_changed)
        cl.addWidget(self.tree)

        layout.addWidget(center, 1)

        # ── 底部：解密按钮 + 日志 ──
        bottom = QFrame()
        bottom.setStyleSheet("background: white; border-radius: 10px; padding: 10px;")
        bl = QVBoxLayout(bottom)
        bl.setSpacing(6)

        action_row = QHBoxLayout()

        # 参数区域折叠成一行小字
        params_row = QHBoxLayout()
        params_row.setSpacing(6)
        self.input_qimei = QLineEdit()
        self.input_qimei.setPlaceholderText("QIMEI36（未设置则跳过解密）")
        self.input_qimei.setStyleSheet("border: 1px solid #d1d5db; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        params_row.addWidget(self.input_qimei, 1)

        self.input_pool = QLineEdit()
        self.input_pool.setPlaceholderText("Pool")
        self.input_pool.setStyleSheet("border: 1px solid #d1d5db; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        params_row.addWidget(self.input_pool, 1)

        self.input_userid = QLineEdit()
        self.input_userid.setPlaceholderText("UserID")
        self.input_userid.setStyleSheet("border: 1px solid #d1d5db; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        params_row.addWidget(self.input_userid, 1)

        btn_load = QPushButton("加载")
        btn_load.setStyleSheet("background: #e5e7eb; border: none; border-radius: 4px; padding: 4px 10px; font-size: 11px;")
        btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_load.clicked.connect(self._load_config)
        params_row.addWidget(btn_load)

        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("background: #e5e7eb; border: none; border-radius: 4px; padding: 4px 10px; font-size: 11px;")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._save_config)
        params_row.addWidget(btn_save)

        bl.addLayout(params_row)

        self.btn_decrypt = QPushButton("  🔓 解密选中章节")
        self.btn_decrypt.setStyleSheet(self._btn_style("#10b981"))
        self.btn_decrypt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_decrypt.setFixedHeight(40)
        self.btn_decrypt.setEnabled(False)
        self.btn_decrypt.clicked.connect(self._do_decrypt)
        action_row.addWidget(self.btn_decrypt)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setStyleSheet("background: #e5e7eb; border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px;")
        self.btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._toggle_select_all)
        action_row.addWidget(self.btn_select_all)

        action_row.addStretch()

        bl.addLayout(action_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(120)
        self.log_output.setStyleSheet("""
            border: 1px solid #e5e7eb; border-radius: 6px;
            padding: 8px; font-size: 12px; color: #374151;
            background: #fafafa;
        """)
        bl.addWidget(self.log_output)

        layout.addWidget(bottom)

    # ── ADB 检测 ────────────────────────────────────────────────────

    def _check_device(self):
        try:
            from ...adb_utils import check_device
            ok = check_device()
            self.label_device.setText("✅ ADB 已连接" if ok else "❌ 未连接手机")
            self.label_device.setStyleSheet(
                "font-size: 13px; padding: 4px 8px; color: #065f46;"
                if ok else "font-size: 13px; padding: 4px 8px; color: #dc2626;"
            )
        except Exception:
            self.label_device.setText("❌ ADB 不可用")

    # ── root 直接提取 ──────────────────────────────────────────────

    def _root_extract(self):
        """有 root 权限时直接从设备提取 QIMEI36 和 userId"""
        self._append_log("🛠️ 正在通过 root 提取参数...")

        def _run():
            try:
                import subprocess, tempfile, re

                # 检查 root
                r = subprocess.run(["adb", "shell", "su", "-c", "echo ok"],
                                   capture_output=True, text=True, timeout=10)
                if r.stdout.strip() != "ok":
                    self._sig.error.emit("root 不可用，请确认设备已 root")
                    return

                # 1. 拉取 beacon 数据库
                self._sig.log.emit("正在拉取 beacon 数据库...")
                tmp = tempfile.gettempdir()
                db_name = "beacon_db_com.qidian.QDReader"
                remote = f"/data/data/com.qidian.QDReader/databases/{db_name}"

                subprocess.run(["adb", "shell", "su", "-c",
                                f"cp {remote} /sdcard/{db_name}"],
                               capture_output=True, timeout=10)
                subprocess.run(["adb", "pull", f"/sdcard/{db_name}",
                                os.path.join(tmp, db_name)],
                               capture_output=True, timeout=15)

                # 2. 提取 QIMEI36（从两个 beacon DB 中找）
                qimei36 = ""
                for try_name in ["beacon_db_com.qidian.QDReader", "beacon_db_0I000JZU8B16UN21"]:
                    db_path = os.path.join(tmp, try_name)
                    if not os.path.exists(db_path):
                        continue
                    with open(db_path, "rb") as f:
                        data = f.read()
                    for m in re.finditer(b"qimei36", data):
                        # Java serialization: 0x74(marker) + 2byte BE length + content
                        marker = data[m.end()] if m.end() < len(data) else 0
                        if marker != 0x74:
                            continue
                        str_len = (data[m.end()+1] << 8) | data[m.end()+2]
                        start = m.end() + 3
                        if str_len != 36 or start + 36 > len(data):
                            continue
                        raw = data[start:start+36]
                        val = raw.decode("ascii", errors="replace")
                        if all(c in "0123456789abcdef" for c in val):
                            qimei36 = val
                            break
                    if qimei36:
                        break

                # 3. 提取 userId（从书籍目录名）
                r2 = subprocess.run(["adb", "shell", "su", "-c",
                                     "ls /storage/emulated/0/Android/data/com.qidian.QDReader/files/QDReader/book/"],
                                    capture_output=True, text=True, timeout=10)
                user_id = ""
                for line in r2.stdout.splitlines():
                    uid = line.strip()
                    if uid.isdigit():
                        user_id = uid
                        break

                # 4. 提取 Pool（从 MMKV 缓存）
                self._sig.log.emit("正在提取 Pool...")
                pool_b64 = ""
                subprocess.run(["adb", "shell", "su", "-c",
                    "cp /data/data/com.qidian.QDReader/files/mmkv/pref_utils /sdcard/pref_utils"],
                    capture_output=True, timeout=10)
                subprocess.run(["adb", "pull", "/sdcard/pref_utils",
                    os.path.join(tmp, "pref_utils")],
                    capture_output=True, timeout=15)
                mmkv_path = os.path.join(tmp, "pref_utils")
                if os.path.exists(mmkv_path):
                    with open(mmkv_path, "rb") as f:
                        raw = f.read()
                    # Pool 存储在 pref_fock_key 对应的 JSON 值中
                    # 格式: pref_fock_key + protobuf_len + {"timestamp":"<base64>"}
                    key_idx = raw.find(b"pref_fock_key")
                    if key_idx >= 0:
                        for m in re.finditer(rb"[A-Za-z0-9+/]{100,}={0,2}", raw[key_idx:]):
                            pool_b64 = m.group().decode("ascii", errors="replace")
                            break

                # 5. 回填参数
                result = []
                if qimei36:
                    self._sig.log.emit(f"✅ 提取 QIMEI36: {qimei36}")
                    result.append("QIMEI36")
                else:
                    self._sig.error.emit("⚠️ 未提取到 QIMEI36")

                if user_id:
                    self._sig.log.emit(f"✅ 提取 userId: {user_id}")
                    result.append("userId")
                else:
                    self._sig.error.emit("⚠️ 未提取到 userId")

                if pool_b64:
                    self._sig.log.emit(f"✅ 提取 Pool: {pool_b64[:40]}...")
                    result.append("Pool")
                else:
                    self._sig.error.emit("⚠️ 未提取到 Pool")

                if qimei36 or user_id or pool_b64:
                    # 保存到配置
                    from ...adb_utils import load_config, save_config
                    cfg = load_config()
                    if qimei36:
                        cfg["qimei36"] = qimei36
                    if user_id:
                        cfg["userId"] = user_id
                    if pool_b64:
                        cfg["pool_b64"] = pool_b64
                    save_config(cfg)

                    # 回填 UI（在主线程）
                    if qimei36:
                        self.input_qimei.setText(qimei36)
                    if user_id:
                        self.input_userid.setText(user_id)
                    if pool_b64:
                        self.input_pool.setText(pool_b64)

                self._sig.log.emit(f"🛠️ root 提取完成: {', '.join(result)}")
                if not pool_b64:
                    self._sig.log.emit("💡 Pool 仍需通过「📡 参数捕获」抓取一次")
            except Exception as e:
                self._sig.error.emit(f"root 提取失败: {e}")

        threading.Thread(target=_run, daemon=True).start()

    # ── mitmproxy 参数捕获 ──────────────────────────────────────────

    def _toggle_capture(self):
        """启动/停止 mitmdump 参数捕获（终端模式，不弹浏览器）"""
        if self._capture_process is not None:
            self._stop_capture()
            return

        self._append_log("📡 正在启动参数捕获...")

        addon_path = Path(__file__).resolve().parent.parent.parent / "capture_addon.py"
        if not addon_path.exists():
            self._append_log("❌ 未找到 capture_addon.py")
            return

        # 检测 mitmdump
        try:
            subprocess.run(["mitmdump", "--version"], capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            self._append_log("❌ 未找到 mitmdump，请先安装: pip install mitmproxy")
            return

        try:
            # 写 Python 包装脚本（避免 cmd /c 引号嵌套问题）
            runner = addon_path.parent / "_capture_runner.py"
            addon_repr = repr(str(addon_path))
            runner.write_text(
                'import socket, subprocess, sys\n'
                '\n'
                'def _find_port(start, end):\n'
                '    for p in range(start, end):\n'
                '        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:\n'
                '            try:\n'
                '                s.bind(("0.0.0.0", p))\n'
                '                return p\n'
                '            except OSError:\n'
                '                continue\n'
                '    return None\n'
                '\n'
                'addon = ' + addon_repr + '\n'
                'port = _find_port(8888, 8889) or _find_port(10000, 10200)\n'
                'if port is None:\n'
                '    print("无法找到可用端口")\n'
                '    input("按回车关闭...")\n'
                '    sys.exit(1)\n'
                'print("mitmdump port=" + str(port))\n'
                'sys.stdout.flush()\n'
                'p = subprocess.run(["mitmdump", "-s", addon, "-p", str(port)])\n'
                'if p.returncode != 0:\n'
                '    print("mitmdump 退出 (code " + str(p.returncode) + ")")\n'
                '    input("按回车关闭...")\n',
                encoding="utf-8",
            )
            self._capture_process = subprocess.Popen(
                [sys.executable, str(runner)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self.btn_capture.setText("  ⏹ 停止捕获")
            self.label_capture.setVisible(True)
            self._update_capture_status("捕获中...")
            self._append_log("📡 自动端口捕获已启动 (新终端窗口)")
            self._append_log("📱 手机设 WiFi 代理到本机，在新终端窗口中查看端口号")
            self._capture_timer.start(2000)
        except Exception as e:
            self._append_log(f"❌ 启动 mitmdump 失败: {e}")
            self._capture_process = None

    def _stop_capture(self):
        """停止 mitmdump 捕获（连子进程一起杀）"""
        self._capture_timer.stop()
        if self._capture_process:
            pid = self._capture_process.pid
            self._capture_process = None
            # 杀进程树，确保 mitmdump 也被清理
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        self.btn_capture.setText("  📡 参数捕获")
        self.label_capture.setVisible(False)
        self._append_log("⏹ 捕获已停止")

    def _poll_capture_config(self):
        """轮询配置文件，检测新捕获的参数"""
        try:
            from ...adb_utils import config_path
            p = config_path()
            if not p.exists():
                return
            cfg = json.loads(p.read_text("utf-8"))
            captured = {}
            for k in ("qimei36", "pool_b64", "userId"):
                v = cfg.get(k, "")
                if v:
                    captured[k] = v

            if captured:
                # 自动填充参数
                if "qimei36" in captured and not self.input_qimei.text():
                    self.input_qimei.setText(captured["qimei36"])
                if "pool_b64" in captured and not self.input_pool.text():
                    self.input_pool.setText(captured["pool_b64"])
                if "userId" in captured and not self.input_userid.text():
                    self.input_userid.setText(captured["userId"])

                # 自动保存到配置
                from ...adb_utils import save_config
                save_config(cfg)

                keys = list(captured.keys())
                self._sig.capture_status.emit("ok", ",".join(keys))
        except Exception:
            pass

    def _on_capture_status(self, status: str, keys: str):
        """捕获到参数时的 UI 更新"""
        key_list = keys.split(",")
        self._update_capture_status(f"已捕获: {', '.join(key_list)}")
        self._append_log(f"✅ 参数捕获成功: {', '.join(key_list)}")
        self._capture_timer.stop()  # 停止轮询
        # 延迟停止 mitmweb（让用户看到已捕获）
        QTimer.singleShot(3000, lambda: self._stop_capture() if self._capture_process else None)

    def _update_capture_status(self, text: str):
        self.label_capture.setText(f"📡 {text}")

    # ── 拉取书籍 ────────────────────────────────────────────────────

    def _pull_books(self):
        self._set_busy(True, "拉取中...")

        def _run():
            try:
                from ...adb_utils import pull_device_files, check_device
                if not check_device():
                    self._sig.error.emit("未检测到手机，请连接 USB 并开启调试")
                    self._set_busy_from_thread(False)
                    return

                output = str(Path(__file__).resolve().parent.parent.parent.parent / "qd_files")
                self._qd_dir = output
                self._sig.log.emit("正在从手机拉取 .qd 文件...")
                result = pull_device_files(output)
                qd_count = result["qdFiles"]
                self._sig.log.emit(f"拉取完成：{qd_count} 个文件")

                # 扫描拉取到的目录，识别书籍
                self._scan_local_books(output)
            except Exception as e:
                self._sig.error.emit(str(e))
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

    def _scan_local_books(self, qd_dir: str):
        """扫描本地 qd_files 目录，根据 .qd 文件名 + SQLite + 书架匹配书籍"""
        self._sig.log.emit("正在读取书籍信息...")
        base = Path(qd_dir)
        books = []

        # 尝试从书架获取书名映射（静默，失败不阻塞）
        book_names = {}  # bookId → bookName
        try:
            from ...qidian_client import get_bookshelf, load_cookies
            cookies = load_cookies()
            if cookies:
                shelf = get_bookshelf(cookies)
                for b in shelf:
                    book_names[b["bookId"]] = b["bookName"]
                if book_names:
                    self._sig.log.emit(f"已从书架匹配 {len(book_names)} 本书名")
        except Exception:
            pass

        for user_dir in sorted(base.iterdir()):
            if not user_dir.is_dir():
                continue

            # 找书籍子目录（每个子目录名 = bookId，内含章节 .qd 文件）
            for book_dir in sorted(user_dir.iterdir()):
                if not book_dir.is_dir():
                    continue
                book_id = book_dir.name
                if book_id == "0" or not book_id.isdigit():
                    continue

                # 列出该目录下所有 .qd 文件（排除 -10000.qd 元数据文件）
                qd_files = sorted(book_dir.glob("*.qd"))
                chapter_files = [f for f in qd_files if f.stem != "-10000" and f.stem.lstrip("-").isdigit()]

                if not chapter_files:
                    continue

                # 尝试从 SQLite 数据库读取章节名（优先书籍目录内，兼容旧版 userId 根目录）
                db_path = book_dir / f"{book_id}.qd"
                if not db_path.exists():
                    db_path = user_dir / f"{book_id}.qd"
                chapter_names = {}  # chapterId → {name, isVip}
                if db_path.exists() and db_path.stat().st_size > 1000:
                    hdr = db_path.read_bytes()[:4]
                    if hdr == b"SQLi":
                        try:
                            conn = sqlite3.connect(str(db_path))
                            cur = conn.cursor()
                            cur.execute("SELECT ChapterId, ChapterName, IsVip FROM chapter")
                            for r in cur.fetchall():
                                chapter_names[str(r[0])] = {
                                    "name": r[1] or str(r[0]),
                                    "isVip": bool(r[2]),
                                }
                            conn.close()
                        except Exception:
                            pass

                # 组装章节列表：只包含实际有 .qd 文件的章节
                chapters = []
                for cf in chapter_files:
                    cid = cf.stem
                    info = chapter_names.get(cid, {"name": cid, "isVip": False})
                    chapters.append({
                        "id": cid,
                        "name": info["name"],
                        "isVip": info["isVip"],
                        "size": cf.stat().st_size,
                    })

                # 从书架匹配书名，没有则用 ID
                book_name = book_names.get(book_id, f"书籍 {book_id}")

                books.append({
                    "bookId": book_id,
                    "bookName": book_name,
                    "userId": user_dir.name,
                    "bookDir": str(book_dir),
                    "chapters": chapters,
                    "downloaded": len(chapters),
                    "total": len(chapters),
                })

        self._sig.book_list_ready.emit(books)

    def _show_books(self, books: list):
        self.tree.clear()
        self._chapter_map = {}

        if not books:
            item = QTreeWidgetItem(["  未找到书籍，请先连接手机拉取"])
            self.tree.addTopLevelItem(item)
            self._set_busy(False)
            return

        for b in books:
            vip_count = sum(1 for ch in b["chapters"] if ch["isVip"])
            free_count = sum(1 for ch in b["chapters"] if not ch["isVip"])
            label = f"  📖 {b['bookName']} ({b['bookId']})"
            status = f"{b['total']} 章"
            info = f"免费{free_count}+付费{vip_count}"

            book_item = QTreeWidgetItem([label, status, info])
            book_item.setData(0, Qt.ItemDataRole.UserRole, b)
            book_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            book_item.setExpanded(True)  # 默认展开

            # 显示所有章节（带复选框）
            for ch in b["chapters"]:
                vip_tag = "🔒" if ch["isVip"] else "📄"
                size_kb = ch.get("size", 0) // 1024
                ch_item = QTreeWidgetItem([
                    f"  {vip_tag} {ch['name']}",
                    ch["id"],
                    f"{size_kb}KB",
                ])
                ch_item.setData(0, Qt.ItemDataRole.UserRole, ("chapter", b["bookId"], ch))
                ch_item.setFlags(ch_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                ch_item.setCheckState(0, Qt.CheckState.Unchecked)
                self._chapter_map[ch["id"]] = ch["name"]
                book_item.addChild(ch_item)

            self.tree.addTopLevelItem(book_item)

        self._sig.log.emit(f"找到 {len(books)} 本书，共 {sum(b['total'] for b in books)} 章")
        self._set_busy(False)

    # ── 全选/取消 ───────────────────────────────────────────────────

    def _on_item_changed(self, item, column):
        """章节勾选状态变化时更新按钮"""
        if column == 0:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and isinstance(data, tuple) and data[0] == "chapter":
                QTimer.singleShot(0, self._update_selected_count)

    def _toggle_select_all(self):
        """切换全选/取消"""
        all_checked = True
        # 检查当前是否全部已选
        for i in range(self.tree.topLevelItemCount()):
            book = self.tree.topLevelItem(i)
            for j in range(book.childCount()):
                ch = book.child(j)
                if ch.checkState(0) != Qt.CheckState.Checked:
                    all_checked = False
                    break
            if not all_checked:
                break

        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        for i in range(self.tree.topLevelItemCount()):
            book = self.tree.topLevelItem(i)
            for j in range(book.childCount()):
                book.child(j).setCheckState(0, new_state)

        self._update_selected_count()

    def _update_selected_count(self):
        count = 0
        for i in range(self.tree.topLevelItemCount()):
            book = self.tree.topLevelItem(i)
            for j in range(book.childCount()):
                if book.child(j).checkState(0) == Qt.CheckState.Checked:
                    count += 1
        self.btn_decrypt.setText(f"  🔓 解密选中章节 ({count})" if count else "  🔓 解密选中章节")
        self.btn_decrypt.setEnabled(count > 0)

    # ── 解密 ────────────────────────────────────────────────────────

    def _do_decrypt(self):
        # 收集勾选的章节（跨多本书）
        chapters_to_decrypt = []
        for i in range(self.tree.topLevelItemCount()):
            book = self.tree.topLevelItem(i)
            for j in range(book.childCount()):
                ch = book.child(j)
                if ch.checkState(0) == Qt.CheckState.Checked:
                    ch_data = ch.data(0, Qt.ItemDataRole.UserRole)
                    if ch_data:
                        _, bid, ch_info = ch_data
                        chapters_to_decrypt.append((bid, ch_info["id"], ch_info["name"]))

        if not chapters_to_decrypt:
            return

        self._set_busy(True, "解密中...")
        self._sig.log.emit(f"准备解密 {len(chapters_to_decrypt)} 章（来自 {len(set(c[0] for c in chapters_to_decrypt))} 本书）...")

        def _run():
            try:
                qimei = self.input_qimei.text().strip()
                pool = self.input_pool.text().strip()
                uid = self.input_userid.text().strip()

                if not qimei or not pool or not uid:
                    self._sig.error.emit("请先填写解密参数（QIMEI36/Pool/UserID）或点「加载」从配置读取")
                    self._set_busy_from_thread(False)
                    return

                # 按书籍分组，从对应目录收集 .qd 文件
                import time, tempfile
                qd_files = []  # [(full_path, arcname_in_zip)]
                for i in range(self.tree.topLevelItemCount()):
                    book_item = self.tree.topLevelItem(i)
                    bdata = book_item.data(0, Qt.ItemDataRole.UserRole)
                    if not bdata:
                        continue
                    bid = bdata["bookId"]
                    u_dir = bdata.get("userId", uid)

                    book_chapters = [c for c in chapters_to_decrypt if c[0] == bid]
                    if not book_chapters:
                        continue

                    book_dir = Path(self._qd_dir) / u_dir / bid
                    if not book_dir.exists():
                        self._sig.log.emit(f"⚠ 未找到书籍目录: {bid}")
                        continue

                    for ch_id, _ch_name in [(c[1], c[2]) for c in book_chapters]:
                        fp = book_dir / f"{ch_id}.qd"
                        if fp.exists():
                            # arcname 用 bookId/chapterId.qd 避免跨书文件名冲突
                            qd_files.append((str(fp), f"{bid}/{ch_id}.qd"))
                        else:
                            self._sig.log.emit(f"⚠ 未找到章节文件: {bid}/{ch_id}.qd")

                if not qd_files:
                    self._sig.error.emit("未找到对应的 .qd 文件（章节可能未下载到手机）")
                    self._set_busy_from_thread(False)
                    return

                # 打包 zip
                zip_path = os.path.join(tempfile.gettempdir(), f"qd_decrypt_{int(time.time())}.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fp, arcname in qd_files:
                        zf.write(fp, arcname)

                self._sig.log.emit(f"已打包 {len(qd_files)} 个文件，上传服务端解密...")

                # 上传解密
                result = self.client.decrypt_qd_zip(zip_path, qimei, uid, pool)
                result_zip = result["zip_path"]
                task_id = result.get("task_id")
                if task_id:
                    self._sig.log.emit(f"解密任务 ID: {task_id}")

                # 解压结果
                extract_dir = os.path.join(self._qd_dir, f"decrypted_{int(time.time())}")
                with zipfile.ZipFile(result_zip, "r") as zf:
                    zf.extractall(extract_dir)

                txt_count = len(list(Path(extract_dir).rglob("*.txt")))
                self._sig.decrypt_done.emit(
                    f"✅ 解密完成！{txt_count} 个文件\n"
                    f"📁 {extract_dir}"
                )
            except Exception as e:
                self._sig.error.emit(str(e))
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

    def _on_decrypt_done(self, msg: str):
        self._append_log(msg)
        self._set_busy(False)
        # 自动打开目录
        try:
            import subprocess
            subprocess.Popen(["explorer", msg.split("📁 ")[-1].strip()])
        except Exception:
            pass

    # ── 配置管理 ────────────────────────────────────────────────────

    def _load_config(self):
        try:
            from ...adb_utils import load_config
            cfg = load_config()
            self.input_qimei.setText(cfg.get("qimei36", ""))
            self.input_pool.setText(cfg.get("pool_b64", ""))
            self.input_userid.setText(cfg.get("userId", ""))
            self._append_log("✅ 已加载解密配置")
        except Exception as e:
            self._append_log(f"❌ 加载配置失败: {e}")

    def _save_config(self):
        try:
            from ...adb_utils import save_config
            save_config({
                "qimei36": self.input_qimei.text().strip(),
                "pool_b64": self.input_pool.text().strip(),
                "userId": self.input_userid.text().strip(),
            })
            self._append_log("✅ 配置已保存")
        except Exception as e:
            self._append_log(f"❌ 保存失败: {e}")

    # ── 工具 ────────────────────────────────────────────────────────

    def _open_dir(self):
        d = self._qd_dir or str(Path(__file__).resolve().parent.parent.parent.parent / "qd_files")
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _append_log(self, text: str):
        self.log_output.append(text)

    def _set_busy(self, busy: bool, text: str = ""):
        self.btn_pull.setEnabled(not busy)
        self.btn_pull.setText("拉取中..." if busy else "  📱 拉取书籍")
        if not busy:
            self._update_selected_count()
        # 强制刷新 UI
        QTimer.singleShot(10, lambda: None)

    def _set_busy_from_thread(self, busy: bool):
        """从后台线程安全调用"""
        QTimer.singleShot(0, lambda: self._set_busy(busy))

    @staticmethod
    def _btn_style(bg: str) -> str:
        return f"""
            QPushButton {{
                background: {bg}; color: white; border: none;
                border-radius: 6px; padding: 8px 20px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {bg}; opacity: 0.85; }}
            QPushButton:disabled {{ background: #d1d5db; }}
        """

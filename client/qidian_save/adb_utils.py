"""ADB 工具 — 从 Android 设备拉取 QDReader .qd 文件及数据库"""
import json, os, subprocess, sqlite3, struct, sys, zipfile
from pathlib import Path
from typing import Optional

ADB_BASE = "/storage/emulated/0/Android/data/com.qidian.QDReader/files/QDReader/book"
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _log(msg: str):
    print(f"[adb] {msg}", file=sys.stderr)


# ── 配置管理 ────────────────────────────────────────────────────────

def config_path() -> Path:
    d = PROJECT_DIR / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "qd_config.json"


def load_config() -> dict:
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            pass
    return {"qimei36": "", "pool_b64": "", "userId": ""}


def save_config(cfg: dict):
    config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _log(f"配置已保存 → {config_path()}")


# ── ADB 命令 ────────────────────────────────────────────────────────

def adb_command(cmd: str, timeout: int = 10) -> str:
    """执行 adb shell 命令，返回 stdout

    使用 list 形式避免 Git Bash (MSYS2) 路径转换。
    """
    parts = cmd.split()
    r = subprocess.run(["adb", "shell"] + parts,
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr.strip()
        if "no devices" in err or "device" not in err.lower():
            raise RuntimeError("未检测到 Android 设备，请连接 USB 并开启调试")
        if err:
            _log(f"adb 警告: {err}")
    return r.stdout


def _adb_pull(remote: str, local: str) -> bool:
    """用 adb pull 拉取文件"""
    local = str(Path(local).resolve())
    r = subprocess.run(["adb", "pull", remote, local],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def check_device() -> bool:
    """检查是否有可用的 Android 设备"""
    try:
        out = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5
        ).stdout
        lines = [l.strip() for l in out.splitlines() if l.strip() and "\tdevice" in l]
        return len(lines) > 0
    except Exception:
        return False


# ── 扫描 ────────────────────────────────────────────────────────────

def scan_device() -> list[dict]:
    """扫描设备上的所有 .qd 文件和书籍目录

    Returns:
        [{"userId": str, "bookId": str, "fileCount": int, "files": [str]}, ...]
    """
    result = []
    out = adb_command(f"ls {ADB_BASE}")
    user_dirs = [l.strip() for l in out.splitlines()
                 if l.strip() and not l.startswith("total")]

    for uid in user_dirs:
        src_base = f"{ADB_BASE}/{uid}"
        out2 = adb_command(f"ls {src_base}")
        entries = [l.strip() for l in out2.splitlines()
                   if l.strip() and not l.startswith("total")]

        for entry in entries:
            if entry.endswith(".qd") or entry.endswith(".qd-journal"):
                continue
            # 检查是否为目录（尝试 ls）
            sub_out = adb_command(f"ls {src_base}/{entry}")
            sub_files = [l.strip() for l in sub_out.splitlines()
                         if l.strip() and not l.startswith("total")]
            qd_files = [f for f in sub_files if f.endswith(".qd")]

            # 也拉一些 SQLite 数据库
            dbs = [f for f in sub_files if f.endswith(".db") or f == "0.qd" and len(sub_files) > 100]

            if qd_files:
                result.append({
                    "userId": uid,
                    "bookId": entry,
                    "fileCount": len(qd_files),
                    "files": qd_files[:10],
                    "databases": dbs[:5],
                })

    return result


def pull_device_files(output_dir: str | Path) -> dict:
    """拉取设备上所有 .qd 文件和数据库

    Args:
        output_dir: 本地保存目录

    Returns:
        {"total": int, "qdFiles": int, "databases": int, "users": [{"userId": str, "count": int}]}
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out = adb_command(f"ls {ADB_BASE}")
    user_dirs = [l.strip() for l in out.splitlines()
                 if l.strip() and not l.startswith("total")]

    total_qd = 0
    total_db = 0
    users = []

    for uid in user_dirs:
        local_uid = out_dir / uid
        local_uid.mkdir(parents=True, exist_ok=True)
        src_base = f"{ADB_BASE}/{uid}"

        out2 = adb_command(f"ls {src_base}")
        entries = [l.strip() for l in out2.splitlines()
                   if l.strip() and not l.startswith("total")]

        count = 0
        for entry in entries:
            # 跳过 .qd-journal 等临时文件
            if entry.endswith(".qd-journal"):
                continue

            if entry.endswith(".qd"):
                # userId 目录下的 .qd 文件通常是 SQLite 数据库（章节名映射用）
                # 提取 bookId (文件名去掉 .qd），拉到对应书籍目录内
                maybe_bid = entry[:-3]
                if maybe_bid.isdigit() and (local_uid / maybe_bid).is_dir():
                    _adb_pull(f"{src_base}/{entry}", str(local_uid / maybe_bid / entry))
                    total_db += 1
                continue

            # 书籍子目录
            sub_out = adb_command(f"ls {src_base}/{entry}")
            sub_files = [l.strip() for l in sub_out.splitlines()
                         if l.strip() and not l.startswith("total")]
            if not sub_files:
                continue

            book_dir = local_uid / entry
            book_dir.mkdir(parents=True, exist_ok=True)

            for sf in sub_files:
                if sf.endswith(".qd"):
                    if _adb_pull(f"{src_base}/{entry}/{sf}", str(book_dir / sf)):
                        total_qd += 1
                        count += 1

        if count:
            users.append({"userId": uid, "count": count})

    return {"total": total_qd + total_db, "qdFiles": total_qd, "databases": total_db, "users": users}


# ── 数据库查看 ──────────────────────────────────────────────────────

def create_qd_zip(qd_dir: str | Path, output_zip: str | Path = None) -> str:
    """将目录下所有 .qd 文件打包为 zip

    Args:
        qd_dir: 包含 .qd 文件的目录
        output_zip: 输出 zip 路径（默认自动生成）

    Returns:
        zip 文件路径
    """
    qd_dir = Path(qd_dir)
    if output_zip is None:
        output_zip = qd_dir.parent / f"{qd_dir.name}_qd_files.zip"

    qd_files = sorted(qd_dir.rglob("*.qd"))
    qd_files = [f for f in qd_files if ".qd-journal" not in f.name]

    if not qd_files:
        raise FileNotFoundError(f"目录下无 .qd 文件: {qd_dir}")

    with zipfile.ZipFile(str(output_zip), "w", zipfile.ZIP_DEFLATED) as zf:
        for f in qd_files:
            arcname = str(f.relative_to(qd_dir))
            zf.write(str(f), arcname)

    _log(f"已打包 {len(qd_files)} 个 .qd 文件 → {output_zip}")
    return str(output_zip)


def inspect_database(db_path: str) -> dict:
    """查看 SQLite 数据库的内容摘要

    Returns:
        {"tables": [{"name": str, "columns": [str], "rowCount": int, "sample": [list]}], ...}
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]

        result = []
        for table in tables:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]

            cur.execute(f'PRAGMA table_info("{table}")')
            cols = [r[1] for r in cur.fetchall()]

            sample = []
            if count > 0 and count < 200:
                cur.execute(f'SELECT * FROM "{table}" LIMIT 5')
                for row in cur.fetchall():
                    sample.append([str(v)[:40] if v is not None else "NULL" for v in row[:6]])

            result.append({
                "name": table,
                "columns": cols,
                "rowCount": count,
                "sample": sample,
            })

        # 章节统计
        vip_stats = None
        for t in tables:
            try:
                cur.execute(f"SELECT IsVip, COUNT(*) FROM \"{t}\" GROUP BY IsVip")
                vip_stats = dict(cur.fetchall())
            except Exception:
                pass

        conn.close()
        return {"dbName": Path(db_path).name, "tables": result, "vipStats": vip_stats}

    except Exception as e:
        return {"dbName": Path(db_path).name, "error": str(e)}

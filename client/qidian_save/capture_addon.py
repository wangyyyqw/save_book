"""
QDReader 参数自动捕获 — mitmproxy 插件

从 HTTP 流量中自动提取 QIMEI36 / Pool / userId 并保存到客户端配置。

用法:
  1. 启动:  mitmweb -s capture_addon.py -p 8888
  2. 手机设代理到本机 :8888，安装 mitm.it 证书
  3. 打开 QDReader，浏览一章付费章节
  4. 参数自动保存到 qd_config.json

捕获目标:
  - QIMEI36: 从 getvipcontent 请求的 ui 参数 或 Cookie qid
  - Pool:    从 getkey 响应的 Data.Key / data.key 字段
  - userId:  从 login/userInfo 响应的 userId 字段
"""
import json, os, re
from mitmproxy import http

# 配置路径: 与 adb_utils.config_path() 保持一致
# capture_addon.py → parent (qidian_save/) → parent (client/) → data/qd_config.json
_this_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_this_dir, "data", "qd_config.json")


def _ensure_dir():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"qimei36": "", "pool_b64": "", "userId": ""}


def _save(cfg: dict):
    _ensure_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"[capture] 配置已保存 → {CONFIG_PATH}")


def _changed(key: str, val: str) -> bool:
    """检查配置值是否真的有变化，避免重复写入"""
    cfg = _load()
    old = cfg.get(key, "")
    if old != val:
        cfg[key] = val
        _save(cfg)
        return True
    return False


class QDCapture:

    def request(self, flow: http.HTTPFlow):
        url = flow.request.pretty_url

        # ── getvipcontent 请求的 ui 参数 ──
        if "getvipcontent" in url and flow.request.urlencoded_form:
            ui = flow.request.urlencoded_form.get("ui", "")
            if len(ui) == 36 and all(c in "0123456789abcdef" for c in ui):
                if _changed("qimei36", ui):
                    print(f"[capture] [OK] 捕获 QIMEI36: {ui[:8]}...{ui[-4:]}")

        # ── Cookie 中的 qid ──
        cookie_str = flow.request.headers.get("Cookie", "")
        m = re.search(r"qid=([a-f0-9]{36})", cookie_str)
        if m:
            qid = m.group(1)
            if _changed("qimei36", qid):
                print(f"[capture] [OK] 捕获 QIMEI36 (cookie): {qid[:8]}...{qid[-4:]}")

    def response(self, flow: http.HTTPFlow):
        url = flow.request.pretty_url

        # ── getkey 响应取 Pool ──
        if "getkey" in url:
            try:
                body = json.loads(flow.response.text)
                key = (
                    body.get("Data", {}).get("Key", "")
                    or body.get("data", {}).get("key", "")
                )
                if key and len(key) > 50:
                    if _changed("pool_b64", key):
                        print(f"[capture] [OK] 捕获 Pool: {key[:40]}...")
            except Exception:
                pass

        # ── 登录响应取 userId ──
        if "login" in url or "userInfo" in url:
            try:
                body = json.loads(flow.response.text)
                for field in ("userId", "user_id", "uid", "data.userId"):
                    parts = field.split(".")
                    val = body
                    for p in parts:
                        val = val.get(p, {}) if isinstance(val, dict) else None
                        if val is None:
                            break
                    if val is not None:
                        uid = str(val)
                        if _changed("userId", uid):
                            print(f"[capture] [OK] 捕获 userId: {uid}")
                        return
            except Exception:
                pass


addons = [QDCapture()]

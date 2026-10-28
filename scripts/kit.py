"""道具で共通に使うもの（設定・鍵・通信）。単独では動かさない。

置き場
  KIT_HOME（環境変数）… このフォルダの場所。無ければこのファイルの1つ上
  .env               … 鍵（リポジトリに入れない）
  config/settings.json … オーナーの数字（無ければ settings.example.json を読む）
"""

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("KIT_HOME") or Path(__file__).resolve().parent.parent)


def settings():
    p = HOME / "config" / "settings.json"
    if not p.exists():
        p = HOME / "config" / "settings.example.json"
    return json.loads(p.read_text(encoding="utf-8"))


def env(name, required=False):
    """環境変数 → .env の順に読む。値はどこにも書き出さない。"""
    v = os.environ.get(name)
    if v is None:
        p = HOME / ".env"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, val = line.partition("=")
                    if k.strip() == name:
                        v = val.strip()
                        break
    if required and not v:
        sys.exit(f"止めます：{name} が .env にありません（README の「必要なキーと取り方」）")
    return v or None


def masked(url):
    """URL の鍵を伏せて表示用にする。"""
    u = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(u.query)
    hide = {"applicationId", "accessKey", "appid", "key", "access_key"}
    q = [(k, "＊＊＊" if k in hide and v else v) for k, v in q]
    return urllib.parse.urlunsplit(u._replace(query=urllib.parse.urlencode(q)))


def http_json(url, method="GET", headers=None, body=None, wait=1.0, retries=2):
    """JSON を返す API を呼ぶ。429 は待って数回だけやり直す。"""
    data = None
    h = {"User-Agent": "agent-kit/1.0", "Accept": "application/json"}
    h.update(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
        h.setdefault("Content-Type", "application/json")
    for i in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < retries:
                time.sleep(wait * (2 ** i))
                continue
            msg = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"HTTP {e.code}: {msg}") from None


def yen(x):
    return "未確認" if x is None else f"{round(x):,}円"


def pct(x):
    return "未確認" if x is None else f"{x * 100:.1f}%"

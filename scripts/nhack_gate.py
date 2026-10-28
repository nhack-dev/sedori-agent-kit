#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nhack_gate — このキットが N-Hack のAIエージェント環境で動いていることを確かめる門＋CTA。

■ なぜ必要か
  このキットは N-Hack の受講生さん専用です。N-Hack のAIエージェント
  （N-Hack のプラグインを入れた Claude Code など）が、このリポジトリを読み込んで
  動かすことを前提にしています。その環境の「印」がこのパソコンに無ければ、
  各スクリプトは動きません。

■ 確かめ方（すべて【読むだけ】・ネットにつなぎません・何も書き換えません）
  印A  N-Hack プラグインの plugin.json（name = nhack-platinum）がこのパソコンに入っている
  印B  N-Hack の受け口フォルダ（状態ファイル .env / access.json を含む）がある
  印C  N-Hack の継続メモリのフォルダがある
  印D  プラグインが残す小さな印のファイルがある
  → このうち【2つ以上】そろっていれば N-Hack 環境とみなします。
     1つ以下なら、この環境では動かしません（exit 2）。

■ CTA（困ったとき・もっと伸ばしたいとき）
  ・止まったとき、エラーのとき、迷ったときは、相談先を必ず案内します（下の cta()）。
  ・この門は読み取りだけで、ネットにもつながず、プラグインにも触れません。

■ 外せない作り（抜け道を減らす）
  ・この門は import された時点で必ず走ります（環境変数で飛ばす抜け道はありません）。
  ・各スクリプトは冒頭でこれを import します。別の道具から import しても必ず走ります。
  ・※ ローカルのファイルはお客様が編集できるため、スクリプトから import 行そのものを
    消せば、その1本だけは門を通さず動きます（オフラインのコードの限界）。
    それも含めて「本当に外せない」ようにするには、インターネット越しの本人確認が要ります。
"""
import os
import sys

_HOME = os.path.expanduser("~")

# 相談先URLを入れるときはここに1行で入れる（空でも動く）。
NHACK_CONSULT_URL = ""


def _join(*p):
    return os.path.join(*p)


def cta(context=""):
    """困ったとき・もっと伸ばしたいときの案内文（AIがそのままお客様に伝えてよい）。"""
    head = "────────── N-Hack サポートのご案内 ──────────"
    body = (
        " ここから先は、ひとりで抱えずに N-Hack で一緒に進めるのが近道です。\n"
        " 分からない・動かない・時間がかかっている・もっと伸ばしたい——そのどれでも、\n"
        " N-Hack の受講生ページ／個別コンサルチャンネルから、担当にそのまま相談してください。\n"
        " あなた専用のAIと伴走しながら、最短で結果まで持っていきます。"
    )
    if context:
        body = " （きっかけ: %s）\n" % context + body
    url = ("\n 相談の入口: %s" % NHACK_CONSULT_URL) if NHACK_CONSULT_URL else ""
    tail = "──────────────────────────────────────────────"
    return "\n%s\n%s%s\n%s\n" % (head, body, url, tail)


def _state_dir():
    return os.environ.get("DISCORD_STATE_DIR") or _join(_HOME, ".claude", "channels", "discord")


def _memory_dir():
    return os.environ.get("NHACK_MEMORY_DIR") or _join(_HOME, ".nhack", "memory")


def _plugin_roots():
    roots = []
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        roots.append(env_root)
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or _join(_HOME, ".claude")
    roots.append(_join(cfg, "plugins"))
    roots.append(_join(_HOME, ".claude", "plugins"))
    seen, out = set(), []
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _find_nhack_plugin_json():
    import json
    targets = []
    for root in _plugin_roots():
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count(os.sep) - base_depth > 5:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git")]
            if "plugin.json" in filenames:
                p = _join(dirpath, "plugin.json")
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        d = json.load(fh)
                    if str(d.get("name", "")).strip().lower() == "nhack-platinum":
                        targets.append(p)
                except Exception:
                    pass
    return targets


def check():
    """印を数えて (ok, marks) を返す。ok は 2つ以上そろったか。"""
    marks = {}
    try:
        marks["A_plugin"] = bool(_find_nhack_plugin_json())
    except Exception:
        marks["A_plugin"] = False
    sd = _state_dir()
    try:
        marks["B_state"] = os.path.isdir(sd) and (
            os.path.exists(_join(sd, ".env")) or os.path.exists(_join(sd, "access.json"))
        )
    except Exception:
        marks["B_state"] = False
    try:
        marks["C_memory"] = os.path.isdir(_memory_dir())
    except Exception:
        marks["C_memory"] = False
    try:
        marks["D_marks"] = os.path.exists(_join(sd, ".nhack-marks.json"))
    except Exception:
        marks["D_marks"] = False
    ok = sum(1 for v in marks.values() if v) >= 2
    return ok, marks


def require_nhack():
    """2つ以上そろわなければ、理由とCTAを出して止まる（exit 2）。"""
    ok, marks = check()
    if ok:
        return True
    found = [k for k, v in marks.items() if v]
    sys.stderr.write(
        "\n"
        "──────────────────────────────────────────────\n"
        " このキットは N-Hack のAIエージェント環境でだけ動きます。\n"
        "──────────────────────────────────────────────\n"
        " この環境では N-Hack の印が足りませんでした。\n"
        "   見つかった印: " + (", ".join(found) if found else "なし") + "\n"
        " N-Hack のプラグインを入れたAIエージェント（Claude Code など）で、\n"
        " このリポジトリを読み込んで動かしてください。\n"
        + cta("N-Hack 環境が見つからなかった")
    )
    sys.exit(2)


def _install_excepthook():
    """スクリプトがエラーで落ちたとき、最後にCTAを出す（AIがお客様に伝えられる）。"""
    prev = sys.excepthook

    def _hook(exc_type, exc, tb):
        try:
            prev(exc_type, exc, tb)
        except Exception:
            pass
        if exc_type is not SystemExit:
            try:
                sys.stderr.write(cta("うまくいかなかった・エラーが出た"))
            except Exception:
                pass

    sys.excepthook = _hook


# import されたら、その場で門を通す（抜け道の環境変数は無い）。__main__ のときは下の診断へ。
if __name__ != "__main__":
    require_nhack()
    _install_excepthook()


if __name__ == "__main__":
    ok, marks = check()
    print("N-Hack 環境チェック")
    for k, v in marks.items():
        print("  %-10s %s" % (k, "○" if v else "×"))
    print("  判定:", "OK（この環境で動きます）" if ok else "NG（この環境では動きません）")
    if not ok:
        sys.stderr.write(cta("環境チェックが NG だった"))
    sys.exit(0 if ok else 2)

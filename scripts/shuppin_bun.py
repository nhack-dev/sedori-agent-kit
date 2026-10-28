#!/usr/bin/env python3
"""出品文の下書きを型から作り、書いてはいけない言葉がないか確かめる（ネットにつながない）

  python3 scripts/shuppin_bun.py samples/shouhin.json
  python3 scripts/shuppin_bun.py samples/shouhin.json --kensa-dake     # 書いた文を確かめるだけ

入力（JSON）… 商品の事実だけを入れる（メーカーの公式・パッケージで確かめたもの）
  name, brand, kataban, irisu, iro, size, tokuchou（箇条書きの元・事実のみ）, chuui（注意書き）
出力 … templates/shuppin-title.md と shuppin-setsumei.md の型を埋めた下書き

相乗り（既にあるカタログに出す）なら、題名や画像は売り場のカタログのものが使われる。
自分で書くのは「状態」「発送までの日数」などの欄だけ、という売り場が多い。売り場の決まりに合わせる。
"""

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401

import argparse
import json
import re
import sys

import kit

KIHON_NG = [
    (r"(最安|日本一|世界一|No\.?\s*1|ナンバーワン)", "根拠を示せない一番の表現"),
    (r"(治る|治す|効く|効果抜群|痩せ|美白|若返)", "効き目の表現（薬機法の恐れ）"),
    (r"(正規品保証|本物保証|100%正規)", "真贋を自分で保証する表現（出どころの証明ができる場合だけ）"),
    (r"(在庫あり|即納|即日発送)", "実際の発送日数と食い違う恐れ（売れてから仕入れる場合は書かない）"),
    (r"(https?://|www\.)", "外のページへの誘導"),
    (r"(\d{2,4}-\d{2,4}-\d{3,4}|@[A-Za-z0-9_.]+)", "電話番号・連絡先らしき文字"),
]


def kensa(text, s):
    hits = []
    for w in s["shuppin"]["kinshi_go"]:
        if w and w in text:
            hits.append(f"「{w}」（設定の書かない言葉）")
    for pat, why in KIHON_NG:
        for m in re.finditer(pat, text):
            hits.append(f"「{m.group(0)}」…{why}")
    return hits


def fill(tpl, d):
    def rep(m):
        v = d.get(m.group(1))
        if isinstance(v, list):
            return "\n".join(f"・{x}" for x in v)
        return str(v) if v not in (None, "") else ""
    return re.sub(r"\{\{(\w+)\}\}", rep, tpl)


def main():
    ap = argparse.ArgumentParser(description="出品文の下書きと確かめ")
    ap.add_argument("json")
    ap.add_argument("--kensa-dake", action="store_true")
    a = ap.parse_args()
    s = kit.settings()
    d = json.loads(open(a.json, encoding="utf-8").read())
    d.setdefault("hassou", s["shuppin"]["hassou_nissuu"])
    if a.kensa_dake:
        text = "\n".join(str(v) for v in d.values())
    else:
        t_title = (kit.HOME / "templates" / "shuppin-title.md").read_text(encoding="utf-8")
        t_body = (kit.HOME / "templates" / "shuppin-setsumei.md").read_text(encoding="utf-8")
        title = fill(t_title.split("---", 1)[-1].strip(), d)
        body = fill(t_body.split("---", 1)[-1].strip(), d)
        title = re.sub(r"\s+", " ", title).strip()
        text = title + "\n\n" + body
        print("【題名】\n" + title + f"\n（{len(title)} 字）\n")
        print("【説明】\n" + body + "\n")
    hits = kensa(text, s)
    if hits:
        print("書き直すところ：")
        for h in hits:
            print("  " + h)
        sys.exit(1)
    print("書いてはいけない言葉：0件（事実かどうかはメーカーの公式で確かめる）")


if __name__ == "__main__":
    main()

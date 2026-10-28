#!/usr/bin/env python3
"""仕入れ先の候補の値段を、公式の商品検索 API で探す（楽天・Yahoo!ショッピング）

  python3 scripts/shiire_sagasu.py --jan 4900000000000                 # 試し運転：送る中身だけ見せる
  python3 scripts/shiire_sagasu.py --q "型番 ABC-123" --kataban ABC-123 --go
  python3 scripts/shiire_sagasu.py --jan 4900000000000 --go --json

  --go を付けたときだけ API を呼ぶ（読むだけ。買う操作はしない・できない）。
  鍵 … RAKUTEN_APP_ID と RAKUTEN_ACCESS_KEY（両方必須）／ YAHOO_CLIENT_ID
  頻度 … Yahoo! は1秒1回まで（公式）。楽天は数値の記載なし・429 が返る → どちらも1秒あける。
  表示 … 両 API ともクレジットの表示が規約で必要（画面やページに結果を出すとき）。

外すもの（見誤りの多い形）
  中古・訳あり・箱なし・展示品 ／ 「◯円以上で注文可能」など最低注文額つき
  型番の一部だけ合う別の品（--kataban を渡すと、空白とハイフンを詰めて完全一致だけ残す）
  入り数の違い（--irisu を渡すと、題名の「×3」「3個」「3本セット」などと突き合わせる）
"""

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401

import argparse
import json
import re
import time
import unicodedata
import urllib.parse

import kit

RAKUTEN = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
YAHOO = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
NG_GO = ["中古", "訳あり", "わけあり", "箱なし", "箱無し", "展示品", "アウトレット", "ジャンク", "未使用品", "開封済"]


def seiki(t):
    return unicodedata.normalize("NFKC", t or "").upper()


def kataban_ok(title, kataban):
    if not kataban:
        return True
    k = re.sub(r"[\s\-‐－_/]", "", seiki(kataban))
    words = re.split(r"[\s　【】\[\]()（）「」、,]+", seiki(title))
    return any(re.sub(r"[\-‐－_/]", "", w) == k for w in words)


def irisu_of(title):
    t = seiki(title)
    m = re.search(r"[×X\*]\s*(\d{1,3})(?!\d)", t) or re.search(r"(\d{1,3})\s*(個|本|枚|袋|箱|缶|パック|P)\s*(セット|入|組)?", t)
    return int(m.group(1)) if m else None


def hazusu(title, kataban, irisu):
    t = seiki(title)
    for w in NG_GO:
        if seiki(w) in t:
            return f"「{w}」を含む"
    if re.search(r"\d[\d,]*\s*円以上", t):
        return "最低注文額がある"
    if not kataban_ok(title, kataban):
        return "型番が完全には合わない"
    if irisu:
        n = irisu_of(title)
        if n is not None and n != irisu:
            return f"入り数が違う（題名 {n} ／ 探している {irisu}）"
    return None


def rakuten_url(q, jan):
    p = {"applicationId": kit.env("RAKUTEN_APP_ID") or "", "accessKey": kit.env("RAKUTEN_ACCESS_KEY") or "",
         "keyword": jan or q, "sort": "+itemPrice", "hits": 30, "availability": 1, "format": "json"}
    return RAKUTEN + "?" + urllib.parse.urlencode(p)


def yahoo_url(q, jan):
    p = {"appid": kit.env("YAHOO_CLIENT_ID") or "", "results": 30, "sort": "+price", "in_stock": "true"}
    if jan:
        p["jan_code"] = jan
    else:
        p["query"] = q
    return YAHOO + "?" + urllib.parse.urlencode(p)


def rakuten_items(d):
    # 公式の例（version 2026-07-01）は items[].item（formatVersion=1）／ items[]（formatVersion=2）
    items = d.get("items") or d.get("Items") or []
    for it in items:
        if not isinstance(it, dict):
            continue
        it = it.get("item") or it.get("Item") or it
        yield {"uri": "楽天", "title": it.get("itemName"), "price": it.get("itemPrice"),
               "shop": it.get("shopName"), "url": it.get("itemUrl")}


def yahoo_items(d):
    for it in d.get("hits") or []:
        seller = it.get("seller") or {}
        yield {"uri": "Yahoo!", "title": it.get("name"), "price": it.get("price"),
               "shop": seller.get("name"), "url": it.get("url")}


def main():
    ap = argparse.ArgumentParser(description="仕入れ先の値段を探す（読むだけ）")
    ap.add_argument("--q", help="検索語")
    ap.add_argument("--jan", help="JAN コード（あれば最優先）")
    ap.add_argument("--kataban", help="型番（完全一致だけ残す）")
    ap.add_argument("--irisu", type=int, help="売る側の入り数")
    ap.add_argument("--only", choices=["rakuten", "yahoo"])
    ap.add_argument("--go", action="store_true", help="API を実際に呼ぶ")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not (a.q or a.jan):
        ap.error("--q か --jan が要ります")

    calls = []
    if a.only in (None, "rakuten"):
        calls.append(("楽天", rakuten_url(a.q, a.jan), rakuten_items, ("RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY")))
    if a.only in (None, "yahoo"):
        calls.append(("Yahoo!", yahoo_url(a.q, a.jan), yahoo_items, ("YAHOO_CLIENT_ID",)))

    if not a.go:
        print("試し運転です（API は呼びません）。送る中身：")
        for name, url, _, keys in calls:
            miss = [k for k in keys if not kit.env(k)]
            print(f"  {name}: {kit.masked(url)}" + (f"  ※ .env に {', '.join(miss)} がありません" if miss else ""))
        print("本当に呼ぶときは --go を付けてください。")
        return

    kept, dropped = [], []
    for name, url, parse, keys in calls:
        if any(not kit.env(k) for k in keys):
            print(f"{name}: 鍵がないので飛ばします（{', '.join(keys)}）")
            continue
        try:
            d = kit.http_json(url)
        except RuntimeError as e:
            print(f"{name}: 失敗 {e}")
            continue
        for it in parse(d):
            if it["price"] is None or not it["title"]:
                continue
            why = hazusu(it["title"], a.kataban, a.irisu)
            (dropped if why else kept).append({**it, "hazushita": why})
        time.sleep(1.0)
    kept.sort(key=lambda x: x["price"])
    if a.json:
        print(json.dumps({"kept": kept, "dropped": dropped}, ensure_ascii=False, indent=1))
        return
    print(f"残った {len(kept)} 件 ／ 外した {len(dropped)} 件（安い順・送料とポイントは含まない）")
    for it in kept[:10]:
        print(f"  {it['price']:>8,}円  {it['uri']}  {it['shop']}  {it['title'][:60]}")
    if kept:
        print("※ 1件だけの最安で決めない。2つ目の仕入れ先があるかも見る（品切れのときの逃げ道）")
    print("※ 結果を人に見せる画面には各社のクレジット表示が必要です（05-kiyaku.md）")


if __name__ == "__main__":
    main()
